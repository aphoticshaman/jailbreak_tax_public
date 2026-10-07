# Jailbreak Taxonomy

Understand AI failure patterns, check the evidence, and develop research with your AI partner.

**[Open the research workbench](https://aphoticshaman.github.io/jailbreak_tax_public/)** · [Download the offline page](https://github.com/aphoticshaman/jailbreak_tax_public/releases/latest/download/START.html) · [Assistant guide](docs/ASSISTANT_GUIDE.md)

This is a sourced, open reference for people studying AI safety. New to the subject? Start with the reading paths and plain-language explanations. Working on a paper? Examine the evidence questions, competing explanations, and source limits. Working with an assistant? Give it this repository and describe what you want to understand; it maintains the records for you.

The workbench contains explanatory concepts and defensive evaluation questions. It does not distribute attack prompts or payloads. Catalog labels are ways to organize questions, not claims that a method will work against a particular model.

## Use it with your assistant

Tell an assistant with local file access:

> Read AGENTS.md and docs/ASSISTANT_GUIDE.md. Help me investigate my research question using this taxonomy. Maintain a separate private workspace, link claims to evidence, check prior work, and bring me conclusions and consequential questions. Do the record keeping for me.

You do not need to fill in taxonomy or journal forms. The assistant can import supported logs, prepare research cards, and rebuild a readable local dashboard. You review the claims and correct the interpretation. The offline page does not contain a model; use your preferred assistant alongside it. A chat-only assistant can work from the copyable handoff in the page.

## Keep your work private

The public repository contains code, a curated catalog, and fictional examples. Create a working directory **outside this checkout** for actual research. The tool refuses an overlapping private workspace.

These commands are for your assistant to run; normal use does not require learning them:

```sh
python jt.py init --workspace ../my-research --name "My research"
python jt.py ingest /path/to/submission-exports --workspace ../my-research
python jt.py build --workspace ../my-research
```

Open `../my-research/RESEARCH.html` to review the result. Python 3.10 or later is required for the local tools; no Python packages, model account, or API key are needed. The public page itself requires only a browser.

The importer reads supported submission-export metadata and records source hashes. It preserves originals and does not copy transcript bodies into the dashboard. Metadata can still be sensitive, so the generated research page remains private. No upload or automatic publication is part of the local workflow.

## What the evidence can establish

The tool keeps platform judgments separate from independently supported findings. It preserves repeated submission snapshots and source references. It leaves execution, authorship, feedback timing, and novelty unknown when the records do not establish them. Automated bookkeeping cannot replace source interpretation or controlled evaluation.

Sources carry review-depth notes: an abstract check is not a full-paper review. A paper linked to a concept does not validate every formulation of that concept. See [catalog standards](docs/CATALOG.md), [research method](docs/RESEARCH_METHOD.md), and [the assistant workflow](docs/ASSISTANT_GUIDE.md).

## Contribute

Useful contributions include clearer explanations, missing prior art, evidence that contradicts a claim, accessibility fixes, and benign test cases. Read [CONTRIBUTING.md](CONTRIBUTING.md). Keep actual working research in your private workspace; propose only the public material needed to assess a change.

```sh
python -m unittest discover -s tests -v
python scripts/build.py
python scripts/release_check.py
node scripts/check_browser.mjs
```

The browser check uses an isolated headless Chromium installation. The generated `START.html` works offline; `index.html` serves the same page on GitHub Pages. All rendering and search happen locally, with no telemetry or runtime model connection. External sources open only when you choose a link.

Code and original catalog text are [MIT licensed](LICENSE). Linked papers retain their own licenses. The project is independent of model vendors and competition platforms.
