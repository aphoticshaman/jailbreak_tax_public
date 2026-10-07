# Product contract

This is an offline research reference for people working with AI assistants. The person supplies questions, source material, corrections, and judgment. Their assistant maintains the research records. The browser is for understanding and review; it is not a form-based journal or a model service.

## Separation

The public repository contains reviewed educational concepts, primary-source references, code, and explicitly fictional examples. Working transcripts and personal research live in a separate local directory, outside this repository. Public builds use only the public catalog and fictional example. They never discover or import private workspaces.

## Data interfaces

`data/catalog.json` has `schema_version: 1`, `title`, `updated`, `summary`, `categories`, `entries`, `sources`, `evaluation_dimensions`, and `learning_paths`.

- Category: `id`, `name`, `summary`.
- Entry: `id`, `category_id`, `name`, `summary`, `boundary`, `evidence_to_check` (strings), `alternative_explanations` (strings), `defensive_questions` (strings), `source_ids` (strings), `epistemic_status` (plain-language limits), and `related_ids` (strings).
- Source: `id`, `title`, `url` (HTTPS), `year`, `reviewed_on`, `review_depth`, and `scope_note`. Review depth must describe what was actually checked.
- Evaluation dimension: `id`, `name`, `question`, and `why_it_matters`.
- Learning path: `id`, `title`, `summary`, `entry_ids` (strings), and `questions` (strings). These are reading paths, not operational sequences.

All text is inert data. Entries explain concepts, observable evidence, rival explanations, and defensive evaluation. They contain no working attack prompts, payloads, step-by-step attack recipes, private cases, or efficacy rankings.

`workspace.json` has `schema_version: 1`, `visibility` (`private` or `demo`), `title`, `selection_note`, `limitations` (strings), `summary` (counts), `records`, and `cards`.

- Summary keys: `submission_count`, `chat_count`, `accepted_submissions`, `accepted_cells`, `source_count`, `messages_snapshot`, `messages_distinct`.
- Record: `id`, `challenge`, `scenario`, `model`, `submitted_at`, `platform_status`, `chat_id`, `message_count`, `tool_call_count`, `evidence_level`, `source_sha256`, and `criteria` (name/score objects). These are measurements at export, not independent findings of success. The browser must not display source paths or raw transcripts.
- Research card: `id`, `title`, `kind` (`observation`, `hypothesis`, or `question`), `statement`, `evidence_refs` (record IDs), `taxonomy_ids`, `alternative_explanations` (strings), `next_check`, `source_urls` (HTTPS URLs), `status` (`proposed`, `supported`, `contested`, or `unresolved`), and `novelty` (`not-assessed` or `prior-art-required`). A supported observation does not prove a novel mechanism.

Missing evidence remains unknown. Source paths and snapshot ancestry may be retained in separate private index files. They must not be embedded in public builds.

## Entry points

- `START.html`: standalone offline public reference with fictional demonstration workspace.
- `python jt.py init --workspace PATH --name NAME`: create a private workspace outside the public repo.
- `python jt.py ingest SOURCE --workspace PATH`: import supported submission-export metadata, hashes, and snapshot relationships without copying transcript bodies.
- `python jt.py add --workspace PATH --file CARD_JSON`: validate and save a card prepared by an assistant.
- `python jt.py add --workspace PATH --file CARD_JSON --replace`: revise an existing card while retaining its prior version in the private history. Without this flag, a conflicting ID is rejected.
- `python jt.py check --workspace PATH`: validate references and evidence structure.
- `python jt.py brief --workspace PATH`: print a bounded, transcript-free assistant handoff.
- `python jt.py build --workspace PATH`: generate `RESEARCH.html` in the private workspace.
- `python scripts/build.py`: rebuild public `START.html` using public inputs only.

The renderer reads `web/index.html`, `web/style.css`, and `web/app.js`; template placeholders are `/* APP_STYLES */`, `/* APP_SCRIPT */`, `CATALOG_JSON`, and `WORKSPACE_JSON`. JSON script elements use IDs `catalog-data` and `workspace-data`. Escape HTML delimiters before embedding JSON. Insert data with DOM text APIs and validate external links as HTTPS. The page has no remote scripts, model calls, telemetry, or runtime network requests.

## User experience

Offer three clear starts: learn the concepts, examine evidence, and work with an assistant. Search and readable detail panels serve beginners and experts. Research cards show claim, evidence, alternatives, missing checks, and novelty status. The assistant handoff tells the assistant how to do the bookkeeping; no multi-field logging flow is required. Any local browser selections are conveniences, never the authoritative research record.

## Verification

Validate catalog references, workspace isolation, imported-record identity, no-overwrite behavior, safe URL handling, HTML escaping, public-build input isolation, and the browser's offline operation. Review the actual release file list and generated artifact before publishing. Automated checks complement editorial review; they do not certify the absence of every possible secret or unsafe passage.
