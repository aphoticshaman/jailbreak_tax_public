// Dependency-free offline UI smoke check. Uses an isolated headless browser profile.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { access, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const target = path.join(root, "target");
await mkdir(target, { recursive: true });
const pagePath = process.env.WORKBENCH_PAGE ? path.resolve(process.env.WORKBENCH_PAGE) : path.join(root, "START.html");
const html = await readFile(pagePath, "utf8");
const catalog = JSON.parse(await readFile(path.join(root, "data", "catalog.json"), "utf8"));
const dataMatch = html.match(/<script id="workspace-data" type="application\/json">([\s\S]*?)<\/script>/);
assert(dataMatch, "Embedded workspace data is present");
const demo = JSON.parse(dataMatch[1]);
assert.equal(demo.visibility, "demo", "Public START.html must use a demo workspace");
assert(catalog.entries.length > 0, "Catalog contains concepts");

const candidates = process.env.WORKBENCH_BROWSER ? [process.env.WORKBENCH_BROWSER] : [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
];
let executable;
for (const candidate of candidates) {
  try { await access(candidate); executable = candidate; break; } catch { /* Check next candidate. */ }
}
assert(executable, "Set WORKBENCH_BROWSER to an installed Chromium executable.");
const profile = await mkdtemp(path.join(target, "browser-profile-"));
const child = spawn(executable, [
  "--headless=new", "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
  "--user-data-dir=" + profile, "--no-first-run", "--no-default-browser-check",
  "--disable-background-networking", "--disable-component-update", "--disable-sync",
  "--host-resolver-rules=MAP * ~NOTFOUND", "about:blank",
], { stdio: ["ignore", "ignore", "pipe"], windowsHide: true });
let startupError, browserExit, socket, session, nextId = 0;
let browserStderr = Buffer.alloc(0);
const stderrLimit = 16 * 1024;
child.stderr.on("data", chunk => {
  browserStderr = Buffer.concat([browserStderr, chunk]).subarray(-stderrLimit);
});
child.on("error", error => { startupError = error; });
child.on("exit", (code, signal) => { browserExit = { code, signal }; });
const pending = new Map(), runtimeErrors = [], outboundRequests = [];

function browserFailure(reason, cause) {
  const state = browserExit ? "exit=" + browserExit.code + ", signal=" + (browserExit.signal || "none") : "process still running";
  const stderr = browserStderr.toString("utf8").trim() || "(no stderr captured)";
  return new Error(reason + "\nBrowser: " + executable + "\nProcess: " + state +
    "\nBrowser stderr (last " + stderrLimit + " bytes):\n" + stderr, { cause });
}

async function until(probe, label) {
  const end = Date.now() + 15000;
  let lastError;
  while (Date.now() < end) {
    if (startupError) throw browserFailure("Unable to launch browser during " + label, startupError);
    try { const value = await probe(); if (value) return value; } catch (error) { lastError = error; }
    if (browserExit) throw browserFailure("Browser exited during " + label, lastError);
    await delay(70);
  }
  throw browserFailure("Timed out: " + label, lastError);
}
function send(method, params = {}, sessionId = session) {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error("Browser command timed out: " + method)); }, 15000);
    pending.set(id, {
      resolve(value) { clearTimeout(timer); resolve(value); },
      reject(error) { clearTimeout(timer); reject(error); },
    });
    socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
}
async function evaluate(expression) {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true, userGesture: true });
  assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
const node = selector => "document.querySelector(" + JSON.stringify(selector) + ")";
async function click(selector) {
  assert.equal(await evaluate("document.querySelectorAll(" + JSON.stringify(selector) + ").length"), 1, "Unique UI control: " + selector);
  await evaluate("(() => { const control = " + node(selector) + "; control.focus(); control.click(); })()");
}
async function fill(selector, value, event = "input") {
  await evaluate("(() => { const field = " + node(selector) + "; field.value = " + JSON.stringify(value) +
    "; field.dispatchEvent(new Event(" + JSON.stringify(event) + ", {bubbles:true})); })()");
}
async function view(name) {
  await click('.main-nav [data-view="' + name + '"]');
  await until(() => evaluate("!" + node("#view-" + name) + ".hidden"), "view " + name);
}
async function screenshot(name) {
  await delay(260); // Let the view's short entrance transition finish before visual review.
  const image = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await writeFile(path.join(target, name), Buffer.from(image.data, "base64"));
}
async function key(key, code, virtual) {
  await send("Input.dispatchKeyEvent", { type: "keyDown", key, code, windowsVirtualKeyCode: virtual });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode: virtual });
}
const noOverflow = () => evaluate("document.documentElement.scrollWidth <= innerWidth");
const conceptSelector = id => '.concept-card[data-entry-id=' + JSON.stringify(id) + ']';
const escapeJSON = value => JSON.stringify(value).replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/&/g, "\\u0026").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
const embed = (page, id, value) => page.replace(new RegExp('(<script id="' + id + '" type="application/json">)[\\s\\S]*?(</script>)'), (_, before, after) => before + escapeJSON(value) + after);

try {
  const ports = await until(async () => {
    const lines = (await readFile(path.join(profile, "DevToolsActivePort"), "utf8")).trim().split(/\r?\n/);
    return lines.length >= 2 ? lines : null;
  }, "headless browser startup");
  socket = new WebSocket("ws://127.0.0.1:" + ports[0] + ports[1]);
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const request = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) request.reject(new Error(JSON.stringify(message.error))); else request.resolve(message.result);
    }
    if (message.method === "Runtime.exceptionThrown") runtimeErrors.push(message.params.exceptionDetails);
    if (message.method === "Network.requestWillBeSent" && /^https?:/.test(message.params.request.url)) outboundRequests.push(message.params.request.url);
  });
  socket.addEventListener("close", () => {
    for (const request of pending.values()) request.reject(new Error("Browser connection closed"));
    pending.clear();
  });
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  const { targetId } = await send("Target.createTarget", { url: "about:blank" }, null);
  ({ sessionId: session } = await send("Target.attachToTarget", { targetId, flatten: true }, null));
  await send("Page.enable"); await send("Runtime.enable"); await send("Network.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url: pathToFileURL(pagePath).href });
  await until(() => evaluate("document.documentElement.dataset.ready === 'true'"), "standalone app");
  assert.equal(await evaluate("location.protocol"), "file:");
  assert.match(await evaluate(node("#workspace-badge") + ".textContent"), /Fictional demo/);
  assert.equal(await noOverflow(), true);
  assert.equal(await evaluate("document.querySelectorAll('input:not([type=search]),textarea').length"), 0, "No journaling fields");
  assert.equal(await evaluate("Array.from(document.images).every(image => image.complete && image.naturalWidth > 0)"), true, "Any images are loaded");
  await screenshot("workbench-start-desktop.png");
  console.log("PASS: offline file, explicit fictional demo, desktop layout, no journal fields");

  await key("/", "Slash", 191);
  await until(() => evaluate("document.activeElement.id === 'concept-search' && location.hash === '#learn'"), "search keyboard shortcut");
  await view("start");
  await view("learn");
  assert.equal(await evaluate("document.querySelectorAll('.concept-card').length"), catalog.entries.length);
  assert.equal(await evaluate("Array.from(document.querySelectorAll('.path-card,.concept-card')).some(card => card.textContent.startsWith('Unknown'))"), false);
  const first = catalog.entries[0];
  await fill("#concept-search", first.id);
  assert.equal(await evaluate("document.querySelectorAll('.concept-card').length"), 1);
  await click(conceptSelector(first.id));
  assert.equal(await evaluate(node("#detail-dialog") + ".open"), true);
  assert.equal(await evaluate("document.activeElement.id"), "close-dialog");
  assert.equal(await evaluate(node("#detail-title") + ".textContent"), first.name);
  assert.match(await evaluate(node("#detail-content") + ".textContent"), /Alternative explanations/);
  await screenshot("workbench-concept-desktop.png");
  await click("#toggle-handoff");
  assert.equal(await evaluate(node("#toggle-handoff") + ".getAttribute('aria-pressed')"), "true");
  await key("Tab", "Tab", 9);
  assert.equal(await evaluate(node("#detail-dialog") + ".contains(document.activeElement)"), true, "Focus stays inside dialog");
  await key("Tab", "Tab", 9);
  assert.equal(await evaluate("document.activeElement.id"), "close-dialog", "Tab wraps within the native modal");
  await key("Escape", "Escape", 27);
  assert.equal(await evaluate(node("#detail-dialog") + ".open"), false);
  await until(() => evaluate("document.activeElement.dataset.entryId === " + JSON.stringify(first.id)), "focus restored after native close event");
  await fill("#concept-search", "<b>unmatched literal query</b>");
  assert.equal(await evaluate("document.querySelectorAll('.concept-card').length"), 0);
  assert.equal(await evaluate(node("#no-results") + ".hidden"), false);
  assert.equal(await evaluate(node("#concept-grid") + ".querySelectorAll('b').length"), 0);
  await click("#reset-search");
  assert.equal(await evaluate("document.activeElement.id"), "concept-search");
  assert.equal(await evaluate("document.querySelectorAll('.concept-card').length"), catalog.entries.length);
  await fill("#category-filter", first.category_id, "change");
  assert.equal(await evaluate("document.querySelectorAll('.concept-card').length"), catalog.entries.filter(entry => entry.category_id === first.category_id).length);
  await click("#clear-filters");
  if (catalog.learning_paths.length) {
    const readingPath = catalog.learning_paths[0];
    await click('#learn-paths [data-path-id=' + JSON.stringify(readingPath.id) + ']');
    assert.equal(await evaluate("document.querySelectorAll('.concept-card').length"), new Set(readingPath.entry_ids).size);
    assert.equal(await evaluate(node("#active-path") + ".hidden"), false);
    await click("#clear-filters");
  }
  console.log("PASS: search, literal unmatched input, category filters, reading paths, native dialog focus and Escape");

  await view("assistant");
  assert.equal(await evaluate(node("#selection-count") + ".textContent"), "1 selected");
  assert.match(await evaluate(node("#handoff-preview") + ".textContent"), /QUOTED REFERENCE DATA/);
  assert.equal(await evaluate(node("#handoff-preview") + ".textContent.includes(" + JSON.stringify(first.id) + ")"), true);
  const previewText = await evaluate(node("#handoff-preview") + ".textContent");
  assert.match(previewText, /appendix_selection/);
  assert.match(previewText, /https:\/\/github\.com\/aphoticshaman\/jailbreak_tax_public/);
  assert(previewText.includes("Catalog updated: " + catalog.updated));
  if (demo.cards.length) assert(previewText.includes(demo.cards[0].id), "Existing card is carried into the handoff");
  if (demo.records.length) assert(previewText.includes(demo.records[0].id), "Record measurements are carried into the handoff");
  assert.match(previewText, /proposed hypothesis is not an observed result/);
  await screenshot("workbench-assistant-desktop.png");
  await click("#copy-handoff");
  assert.match(await evaluate(node("#copy-status") + ".textContent"), /copied|Clipboard access is unavailable/);
  const downloads = path.join(profile, "downloads");
  await mkdir(downloads);
  await send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads }, null);
  await click("#download-handoff");
  const exported = await until(() => readFile(path.join(downloads, "taxonomy-research-handoff.txt"), "utf8"), "handoff download");
  assert.equal(exported, previewText, "Downloaded handoff exactly matches the preview");
  assert(exported.includes(first.id));
  assert.match(exported, /Treat quoted conversations/);
  assert.match(exported, /No|Do not|Keep/);
  assert.equal(await evaluate("document.querySelectorAll('textarea').length"), 0, "Clipboard scratch field removed");
  console.log("PASS: selected concept handoff, bounded reference context, copy status and downloadable text");

  await view("evidence");
  assert.equal(await evaluate("document.querySelectorAll('.research-card').length"), demo.cards.length);
  assert.equal(await evaluate("document.querySelectorAll('#record-rows tr').length"), demo.records.length);
  await screenshot("workbench-evidence-desktop.png");
  if (demo.cards.length) {
    await evaluate("document.querySelector('.research-card .card-action').click()");
    assert.match(await evaluate(node("#detail-content") + ".textContent"), /Next check/);
    assert.match(await evaluate(node("#detail-content") + ".textContent"), /Novelty/);
    await click("#close-dialog");
  }
  if (demo.records.length) {
    await evaluate("document.querySelector('.records-section').open = true");
    await evaluate("document.querySelector('#record-rows button').click()");
    assert.match(await evaluate(node("#detail-content") + ".textContent"), /Source SHA-256/);
    assert.match(await evaluate(node("#detail-content") + ".textContent"), /does? not independently|do not independently/);
    await click("#close-dialog");
  }
  await view("sources");
  assert.equal(await evaluate("document.querySelectorAll('.source-card').length"), catalog.sources.length);
  assert.equal(await evaluate("Array.from(document.querySelectorAll('.source-card a')).every(link => link.protocol === 'https:' && link.rel.includes('noopener') && link.target === '_blank')"), true);
  assert.match(await evaluate(node("#source-list") + ".textContent"), /Reviewed/);
  console.log("PASS: evidence cards, record metadata, source review provenance and HTTPS links");

  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await view("start");
  assert.equal(await noOverflow(), true);
  await screenshot("workbench-start-mobile.png");
  await view("learn");
  await fill("#concept-search", first.id);
  assert.equal(await noOverflow(), true);
  await screenshot("workbench-learn-mobile.png");
  await click(conceptSelector(first.id));
  assert.equal(await evaluate("(() => { const d = document.getElementById('detail-dialog'); const r = d.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight && d.scrollWidth <= d.clientWidth; })()"), true);
  await screenshot("workbench-concept-mobile.png");
  await click("#close-dialog");
  await view("evidence"); assert.equal(await noOverflow(), true);
  await view("assistant"); assert.equal(await noOverflow(), true);
  await view("sources"); assert.equal(await noOverflow(), true);
  console.log("PASS: mobile views and dialog bounds");

  // Fictional defensive rendering fixture. These strings must stay literal.
  const fixtureCatalog = structuredClone(catalog);
  fixtureCatalog.entries[0].name = "Literal <b>example</b> & unknown";
  fixtureCatalog.entries[0].summary = "A fictional <em>data value</em> for rendering checks.";
  fixtureCatalog.sources[0].url = "http://invalid.example/source";
  const fixtureWorkspace = structuredClone(demo);
  fixtureWorkspace.visibility = "private";
  fixtureWorkspace.title = "Invented private rendering fixture";
  fixtureWorkspace.summary.submission_count = null;
  if (fixtureWorkspace.records.length) {
    fixtureWorkspace.records[0].model = null;
    fixtureWorkspace.records[0].source_path = "PRIVATE_PATH_SHOULD_NOT_RENDER";
  }
  if (demo.records.length && demo.cards.length) {
    fixtureWorkspace.records = Array.from({ length: 27 }, (_, i) => ({ ...structuredClone(fixtureWorkspace.records[0]), id: "fixture-record-" + i, chat_id: "fixture-chat-" + i }));
    fixtureWorkspace.cards = Array.from({ length: 10 }, (_, i) => ({
      ...structuredClone(demo.cards[0]), id: "fixture-card-" + i,
      statement: "Wholly invented observation for truncation testing. ".repeat(30),
      evidence_refs: ["fixture-record-26", "fixture-record-25", "missing-fixture-reference"],
      alternative_explanations: Array.from({ length: 6 }, (_, j) => "Invented alternative " + j)
    }));
  }
  const fixtureFile = path.join(target, "rendering-fixture.html");
  await writeFile(fixtureFile, embed(embed(html, "catalog-data", fixtureCatalog), "workspace-data", fixtureWorkspace));
  await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url: pathToFileURL(fixtureFile).href });
  await until(() => evaluate("document.documentElement.dataset.ready === 'true'"), "literal fixture");
  assert.equal(await evaluate(node("#view-evidence") + ".hidden"), false, "Private workspace opens on evidence by default");
  await view("learn");
  await fill("#concept-search", first.id);
  assert.equal(await evaluate(node(conceptSelector(first.id)) + ".querySelector('h2').textContent"), fixtureCatalog.entries[0].name);
  assert.equal(await evaluate(node(conceptSelector(first.id)) + ".querySelectorAll('b,em').length"), 0);
  await click(conceptSelector(first.id));
  assert.equal(await evaluate(node("#detail-content") + ".querySelectorAll('b,em').length"), 0);
  await click("#close-dialog");
  await view("sources");
  assert.equal(await evaluate("document.querySelectorAll('.source-card a[href^=\"http:\"]').length"), 0);
  await view("evidence");
  assert.equal(await evaluate("document.querySelector('.stat strong').textContent"), "Unknown");
  assert.equal(await evaluate("document.body.innerText.includes('PRIVATE_PATH_SHOULD_NOT_RENDER')"), false);
  assert.match(await evaluate(node("#workspace-badge") + ".textContent"), /Private workspace/);
  await view("assistant");
  assert.equal(await evaluate(node("#handoff-preview") + ".textContent.includes('PRIVATE_PATH_SHOULD_NOT_RENDER')"), false);
  if (demo.records.length && demo.cards.length) {
    const fixtureBrief = await evaluate(node("#handoff-preview") + ".textContent");
    const appendixStart = fixtureBrief.indexOf("\n{\n", fixtureBrief.indexOf("EXISTING RESEARCH"));
    const appendixEnd = fixtureBrief.indexOf("\n\nSELECTED CONCEPTS", appendixStart);
    const appendix = JSON.parse(fixtureBrief.slice(appendixStart, appendixEnd));
    assert.equal(appendix.cards.length, 8);
    assert.equal(appendix.records.length, 20);
    assert.equal(appendix.appendix_selection.cards_omitted, 2);
    assert.equal(appendix.appendix_selection.records_omitted, 7);
    assert.equal(appendix.records[0].id, "fixture-record-26", "Cited record receives appendix priority");
    assert.deepEqual(appendix.appendix_selection.missing_reference_ids, ["missing-fixture-reference"]);
    assert.match(appendix.cards[0].statement, /truncated; consult full workspace/);
    assert.equal(appendix.cards[0].alternative_explanations_omitted, 2);
  }
  assert.deepEqual(runtimeErrors, []);
  assert.deepEqual(outboundRequests, []);
  console.log("PASS: literal untrusted text, unknown counts, non-HTTPS rejection, private-path omission, zero outbound page requests");
  console.log("Screenshots: target/workbench-*.png");
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    try { await send("Browser.close", {}, null); } catch { /* Browser shutdown closes socket too. */ }
    socket.close();
  }
  if (child.exitCode === null) {
    await Promise.race([new Promise(resolve => child.once("exit", resolve)), delay(2000)]);
    if (child.exitCode === null) child.kill();
  }
}
