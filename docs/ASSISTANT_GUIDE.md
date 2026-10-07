# Let the assistant maintain the research

The person's job is to supply intent, material, corrections, and judgment. Your job is to read, extract, organize, compare, and preserve an auditable record. Do not turn this into a questionnaire or ask the person to transcribe facts already in a file.

## Start from the question

Read the repository instructions and the relevant catalog entries. Determine what the user is trying to learn: a concept, an explanation for an observation, an evaluation method, a literature comparison, or a draft paper. A request to explore a theory is not evidence that the theory is correct.

Find or create a private workspace outside the public checkout. The workspace is the durable record; your chat is a convenient interface. Use the local command help rather than guessing an API.

## Import before asking

Use `jt.py ingest` for supported submission exports. It extracts source identifiers, recorded judgments, counts, hashes, and snapshot relationships. Read the resulting limitations. Imported metadata does not identify the mechanism or establish that the judge was correct.

When other formats are supplied, inspect them as data and explain the format gap. Preserve originals. Never fabricate a successful import or silently skip malformed records. Do not infer absent information from a filename, writing style, or an assistant's confidence. Ask for a missing fact only when it changes the work you can do.

## Turn observations into cards

Create a small number of substantive cards. Each should express one observation, hypothesis, or open question; cite the relevant record IDs; name alternative explanations; and specify the next check. Use `python jt.py add --workspace PATH --file CARD_JSON` to validate and save a card. This file is produced by you, not by asking the person to fill a form. Use `jt.py check` and `jt.py build` after changes.

When the person corrects an interpretation or new evidence changes it, revise the card using the same command with `--replace`. The tool retains the prior version in private history. A conflicting same-ID add without that flag is rejected, and adding an identical card is a no-op. Explain the change in the card's wording and your response; do not leave contradictory active cards merely to avoid updating one.

The schema is documented in [the product contract](PRODUCT_CONTRACT.md). Missing evidence references are appropriate for a new hypothesis, provided the wording and status do not imply supporting observations. A `supported` card must be an evidence-backed observation; it does not mean a novel mechanism has been established. Never upgrade a hypothesis merely because the same interpretation was repeated in several chats.

## Investigate novelty adversarially

Write the narrow candidate claim first. Search for its mechanism, equivalent terminology, and adjacent fields. Read the closest primary works, follow their references, and check newer work. Keep a query log and a claim-to-prior-art comparison with dates and reading depth. Prefer a disconfirming source over a broad statement that nothing similar exists.

Separate these questions: Is the observation real? Does the proposed explanation fit better than rivals? Is the result useful? Is the specific contribution new? A contribution can be a careful replication, a negative result, or a measurement correction. Do not inflate it into a new attack family.

## Return useful work

Give the person a short account of what changed, what the evidence supports, what remains unresolved, and where to review it. Rebuild the dashboard rather than making them maintain another interface. Use `jt.py brief` for a transcript-free handoff to another assistant. The brief is still private research data; keep it in the workspace unless the person deliberately chooses to share it.

When drafting a paper, separate operator testimony from recorded observations, describe the selection process and unit of analysis, cite nearest work beside each contribution claim, and keep limitation statements proportional to their consequences. The software does not certify novelty or publication readiness.
