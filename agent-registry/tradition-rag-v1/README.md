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

## Corpus ingestion v1

`ingestion.py` adds a bounded network-ingestion layer in front of retrieval.

The control path is:

    registered source identity
      -> storage / copyright policy
      -> exact-URL fetch
      -> redirect-domain check
      -> content-type / access-challenge gate
      -> raw response SHA-256
      -> normalized text SHA-256
      -> immutable source-record revision
      -> exact-content duplicate annotation
      -> freshness state
      -> bounded chunk projection
      -> tradition/lane index rebuild

Network ingestion is reference capture only. A successful fetch does not create an engineering EvidenceRecord and cannot change mechanical acceptance.

### Network restrictions

The v1 fetcher:
- requests only explicitly registered URLs;
- never crawls links recursively;
- permits HTTPS only;
- enforces a hard response-size bound;
- preserves TLS certificate verification;
- rejects redirects outside the registered domain family;
- rejects access/challenge/captcha pages even when they return HTTP 200;
- records HTTP failures and rate-limit metadata without bypassing them;
- pauses between automatic requests;
- does not fetch bodies for `METADATA_ONLY_UNLESS_USER_LICENSED` sources.

Public Atom/RSS feeds may be used where the publisher exposes them. They remain in the source's existing authority lane.

### Runtime revision store

Runtime source observations remain outside Git:

    C:\CADGrounded\tradition-rag-data\
      checks\
      latest\
      source-records\
      texts\
      active_chunks.jsonl
      projection-status.json
      collections\

Raw response bytes are hashed but not retained by network ingestion. Bounded normalized text is content-addressed by SHA-256.

Every network chunk returned by retrieval includes:
- source record ID;
- observation timestamp;
- raw response SHA-256;
- normalized document SHA-256;
- content-group SHA-256;
- duplicate-group metadata;
- storage mode;
- chunk ordinal and chunk hash.

### Commands

Show planned source policy:

    python ingestion.py plan

Inspect freshness and last-attempt state:

    python ingestion.py status

Fetch one exact registered source:

    python ingestion.py ingest --source AUTH.REDSEAL.MILLWRIGHT

Refresh only sources whose lane freshness window has expired:

    python ingestion.py ingest --all-safe

Force a reviewed full refresh of body-eligible sources:

    python ingestion.py ingest --all-safe --force

Build the current retrieval projection from the latest immutable source revisions:

    python ingestion.py project

Then rebuild the deterministic retrieval indices:

    python tradition_rag.py bootstrap

### Seed/live interaction

A source keeps its curated seed card until a successful live source record exists.

Once a source has active live chunks, its seed card is omitted from rebuilt indices. This prevents the same source from gaining artificial retrieval weight through both its seed summary and live corpus.

If a live source later becomes temporarily unavailable, the last successfully captured immutable revision remains the active retrieval source until explicitly superseded or removed.

### Duplicate handling

Exact normalized-document duplicates are grouped by hash.

Duplicate copies do not gain authority through repetition. The canonical duplicate record is chosen deterministically by lane priority and source identity, while every source keeps its own provenance record. Retrieval suppresses repeated identical chunk groups so copied material does not act like independent corroboration.

### Freshness

Default lane refresh windows are:
- AUTHORITATIVE: 30 days;
- PROFESSIONAL_PRACTICE: 30 days;
- FIELD_CHATTER: 7 days.

Automatic `--all-safe` refreshes respect the most recent check, including blocked/failed observations, so inaccessible sources are not hammered repeatedly. An explicit single-source fetch remains an operator-directed probe.

### Source recovery notes

The NUC uses Python's verified default TLS context augmented with the Windows ROOT/CA certificate stores when available. This preserves certificate verification while aligning Python with the host trust store; it does **not** disable TLS validation.

That recovered:
- Sandvik Coromant Metal Cutting Technology as PROFESSIONAL_PRACTICE;
- SMRP Exchange recent discussions as FIELD_CHATTER.

For browser-protected forums:
- Eng-Tips remains challenge-blocked;
- PLCtalk and Control.com remain direct-fetch blocked;
- their registered identities and seed cards remain available, but the fetcher does not impersonate a browser or bypass challenges.

Additional live chatter is supplied through official machine-readable interfaces:
- Stack Exchange API mechanical-engineering questions;
- Stack Exchange API PLC questions.

Stack Exchange captures preserve question author, link, tags, last-activity time, and the per-item content license in normalized text.
