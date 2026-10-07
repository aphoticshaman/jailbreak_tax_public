# How to read and maintain the catalog

The public catalog contains 65 explanatory entries in 16 categories, eight
evaluation dimensions, and six reading paths. Its purpose is to help a person
and an assistant understand a concept, identify relevant evidence, and assess
competing explanations. It contains no working prompts, payloads, operational
sequences, or actual research cases.

## What an entry means

Each entry states a concept, a relevant boundary, observations to check, plausible
alternative explanations, and questions for defensive evaluation. The final
epistemic-status field states a material limit on interpretation. Read it alongside
the description, not as a general disclaimer detached from the claim.

These entries are not 65 independent mechanisms. Some describe input context,
some describe system interfaces, and others concern evaluation procedures or
measurement validity. Several labels can fit one observation without establishing
several causes. A similarity in wording does not establish that a published method
was used, and a familiar label does not forecast effectiveness.

Stable identifiers preserve continuity between versions. Display names use plain,
descriptive language; some historical identifiers are more dramatic than the
current interpretation. Identifiers are references, not endorsements of the
claims implied by their original names. Related-entry links identify conceptual
relationships. Reading paths group questions for study; neither is an operational
sequence.

## Sources and review depth

The source registry links 31 primary sources: original papers, official research
summaries, and a NIST publication record. Each source has a review date, the depth
actually inspected, and a scope note. An abstract or publication-page check is
explicitly distinguished from a selected full-text methods review. Team reviews
name the inspected sections; none is described as an independent replication or
a complete code audit.

A source link supports the relationship described in its scope note. It does not
mean the source uses this catalog's label, validates every sentence in the entry,
or establishes behavior on a current deployment. Preprints are identified where
relevant. Publication years describe the cited work, while later versions may
exist at the same canonical link. Refresh the source before relying on a
version-sensitive claim.

Most boundary definitions and rival explanations are editorial synthesis. Where
the reviewed sources provide only broad background, the entry says so. Numerical
efficacy results, provider rankings, composition recommendations, and unverified
legacy bibliography claims are intentionally outside this public reference.

## Evidence dimensions

The eight dimensions describe sampling units, actor control, trajectory ancestry,
outcome evidence, artifact provenance, judging feedback, human-AI division of work,
and configuration. They sit alongside concept labels. They help an assistant
extract supported facts while preserving unknowns; they are not a mandatory
questionnaire for the person doing research.

Keep source observation, operator recollection, platform judgment, and analytical
interpretation distinct. Preserve both supporting and contrary evidence. A
proposed explanation belongs in a private research card until its evidence and
nearest prior work support a stronger claim. The catalog does not certify novelty.

## Curation and validation

Public text is authored for this reference. There is no automatic importer from
a working research catalog, transcript directory, or personal workspace. New
material must satisfy the [contribution standards](../CONTRIBUTING.md) and the
[product contract](PRODUCT_CONTRACT.md). Do not copy attack examples or appendices
from linked papers into the catalog.

Run:

```sh
python scripts/check_catalog.py
python -m unittest discover -s tests -p test_catalog.py -v
```

The validator checks exact allowed fields, required text, identifiers, category
membership, dates, public HTTPS link structure, and internal references. Tests
exercise missing references, malformed records, unsafe link forms, and rejection
of extra fields. These checks do not verify that a URL's contents are authoritative
or that prose contains no sensitive material. Editorial review and the repository's
separate release checks remain necessary. Rebuild generated pages after approved
catalog changes using the documented build workflow.
