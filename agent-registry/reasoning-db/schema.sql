PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS worlds (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'cad',
    title TEXT NOT NULL,
    source_system TEXT,
    source_path TEXT,
    revision TEXT,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id),
    kind TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    source_ref TEXT,
    parent_entity_id TEXT REFERENCES entities(id),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(world_id, canonical_name)
);

CREATE TABLE IF NOT EXISTS intervals (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id),
    kind TEXT NOT NULL DEFAULT 'valid_time',
    start_value TEXT,
    end_value TEXT,
    units TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id),
    source_class TEXT NOT NULL,
    source_ref TEXT,
    observed_at TEXT NOT NULL,
    valid_interval_id TEXT REFERENCES intervals(id),
    payload_json TEXT NOT NULL,
    mapped INTEGER NOT NULL DEFAULT 0 CHECK(mapped IN (0,1))
);

CREATE TABLE IF NOT EXISTS assertions (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id),
    subject_entity_id TEXT NOT NULL REFERENCES entities(id),
    predicate TEXT NOT NULL,
    object_entity_id TEXT REFERENCES entities(id),
    literal_json TEXT,

    supports_true INTEGER NOT NULL DEFAULT 0 CHECK(supports_true IN (0,1)),
    supports_false INTEGER NOT NULL DEFAULT 0 CHECK(supports_false IN (0,1)),

    evidence_class TEXT NOT NULL DEFAULT 'unknown' CHECK(evidence_class IN (
        'unknown','inferred','approximate_getbox',
        'verified_solidworks_api','human_mechanical_review'
    )),
    evidence_rank INTEGER NOT NULL DEFAULT 0 CHECK(evidence_rank BETWEEN 0 AND 4),

    source_observation_id TEXT REFERENCES observations(id),
    valid_interval_id TEXT REFERENCES intervals(id),
    recorded_at TEXT NOT NULL,
    supersedes_assertion_id TEXT REFERENCES assertions(id),
    metadata_json TEXT NOT NULL DEFAULT '{}',

    CHECK(object_entity_id IS NOT NULL OR literal_json IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_assertions_spo
ON assertions(world_id, subject_entity_id, predicate, object_entity_id);

CREATE INDEX IF NOT EXISTS idx_assertions_predicate
ON assertions(world_id, predicate);

CREATE TABLE IF NOT EXISTS qualitative_relations (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id),
    algebra TEXT NOT NULL CHECK(algebra IN ('allen','rcc8')),
    axis TEXT CHECK(axis IN ('x','y','z','time') OR axis IS NULL),
    subject_entity_id TEXT NOT NULL REFERENCES entities(id),
    object_entity_id TEXT NOT NULL REFERENCES entities(id),
    relation TEXT NOT NULL,
    evidence_class TEXT NOT NULL DEFAULT 'unknown',
    evidence_rank INTEGER NOT NULL DEFAULT 0 CHECK(evidence_rank BETWEEN 0 AND 4),
    source_observation_id TEXT REFERENCES observations(id),
    recorded_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_relation_lookup
ON qualitative_relations(world_id, algebra, subject_entity_id, object_entity_id, axis);

CREATE TABLE IF NOT EXISTS constraints (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id),
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'hard'
        CHECK(severity IN ('soft','hard','critical')),
    expression_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS derivations (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id),
    rule_name TEXT NOT NULL,
    conclusion_assertion_id TEXT REFERENCES assertions(id),
    conclusion_relation_id TEXT REFERENCES qualitative_relations(id),
    premises_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK(conclusion_assertion_id IS NOT NULL OR conclusion_relation_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id),
    action_type TEXT NOT NULL,
    authority TEXT NOT NULL
        CHECK(authority IN ('none','read','write_proposed','write_authorized')),
    state TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS discovery_signals (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id),
    kind TEXT NOT NULL,
    severity TEXT NOT NULL
        CHECK(severity IN ('info','low','medium','high','critical')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK(status IN ('open','promoted','resolved','dismissed')),
    source_observation_id TEXT REFERENCES observations(id),
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_discovery_open
ON discovery_signals(world_id, status, severity);

CREATE VIEW IF NOT EXISTS proposition_support AS
SELECT
    world_id,
    subject_entity_id,
    predicate,
    COALESCE(object_entity_id, '') AS object_entity_id,
    MAX(supports_true) AS supports_true,
    MAX(supports_false) AS supports_false,
    MAX(evidence_rank) AS max_evidence_rank
FROM assertions
GROUP BY world_id, subject_entity_id, predicate, COALESCE(object_entity_id, '');

CREATE VIEW IF NOT EXISTS proposition_epistemic_state AS
SELECT
    *,
    CASE
        WHEN supports_true = 1 AND supports_false = 0 THEN 'true_only'
        WHEN supports_true = 0 AND supports_false = 1 THEN 'false_only'
        WHEN supports_true = 1 AND supports_false = 1 THEN 'both'
        ELSE 'neither'
    END AS truth_state
FROM proposition_support;
