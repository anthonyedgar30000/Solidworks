# CADGrounded Tradition RAG v1

Local, lane-aware retrieval for engineering and skilled-trades traditions.

## Purpose

Tradition RAG v1 gives CADGrounded a bounded way to consult different engineering/trades traditions while preserving provenance and authority.

It is **not** an engineering-evidence admission path.

Retrieval can:
- expose standards/trade obligations and terminology;
- surface professional heuristics;
- generate field-practice hypotheses and diagnostic tests;
- help detect omitted concerns during Proof-of-Principle review.

Retrieval cannot:
- verify SOLIDWORKS geometry or dimensions;
- establish OEM intent;
- convert UNKNOWN/UNRESOLVED to VERIFIED;
- grant mechanical acceptance;
- authorize CAD writes.

## Source lanes

1. **AUTHORITATIVE**
   - standards bodies, regulators, trade standards and formal professional bodies;
   - usable only within the source's actual scope.

2. **PROFESSIONAL_PRACTICE**
   - OEM/vendor training and professional application material;
   - useful for heuristics and candidate tests, not project-specific truth.

3. **FIELD_CHATTER**
   - practitioner forums and communities;
   - hard effect ceiling: **HYPOTHESIS_ONLY**.

The lane is stored on every retrievable chunk and is returned with every hit.

## Traditions

- machine design
- millwright
- machining/toolmaking
- fabrication/welding/sheet metal
- industrial electrical
- controls/automation
- instrumentation/mechatronics
- fluid power
- conveyor/material handling
- packaging/machine building
- industrial/manufacturing engineering
- machine safety
- reliability/maintenance

These are separate logical collections under one local service.

## Current retrieval

v1 uses SQLite FTS5 as the deterministic baseline retriever.

This is intentional:
- ranking is inspectable;
- no embedding model can blur lane provenance;
- no external service is required;
- regression tests are cheap.

A later hybrid revision may add local Ollama embeddings as a second signal while preserving this exact lane policy.

## Data layout

Runtime data is intentionally outside the Git repository:

    C:\CADGrounded\tradition-rag-data\
      manifest.json
      collections\
        MACHINE_DESIGN\index.sqlite3
        MILLWRIGHT\index.sqlite3
        ...

The repository stores code, policy, source registry and bounded seed cards only.

## Bootstrap

From this directory:

    python tradition_rag.py bootstrap

Then inspect:

    python tradition_rag.py status

Example retrieval:

    python tradition_rag.py ask \
      --tradition PACKAGING_MACHINE_BUILDING \
      --question "How should a bottle capture mechanism be reviewed for motion, restraint and release?"

Optional local synthesis through Ollama:

    python tradition_rag.py ask \
      --tradition PACKAGING_MACHINE_BUILDING \
      --question "How should a bottle capture mechanism be reviewed?" \
      --generate

The default generation model is `qwen2.5:3b`.

## Copyright / storage boundary

Paid or licensed standards are not bulk copied into this repository.

Registry entries specify storage policy such as:
- metadata/public summary only;
- user-licensed content only;
- bounded discovery/excerpts for community sources.

If the user lawfully supplies a purchased standard, manual or book excerpt, it may be indexed locally subject to that material's license. The retrieval record must preserve its source identity and lane.

## CADGrounded integration boundary

Tradition RAG output may feed:
- investigation planning;
- hypothesis generation;
- next-test proposals;
- adversarial POP review.

It does not directly feed:
- SolidWorksObservation verification;
- mechanical acceptance;
- write authority.

For PLAN-0011, a useful role is reviewing the mechanism-independent POP acceptance envelope from multiple traditions before candidate geometry is promoted.
