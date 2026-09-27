#!/usr/bin/env python3
"""Serialize a source-freshness observation as a bounded OTLP/JSON log event.

No collector connection, network I/O, EvidenceRecord admission, or CAD write is
performed. The payload contains status metadata only; provenance stays in the
separate source-freshness observation.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from source_freshness import SourceFreshnessError, compare
from source_freshness_bundle import normalize

EVENT_NAME = "cadgrounded.source_freshness.checked"
STATES = {"ALIGNED_AT_CHECKPOINT_LEVEL", "STALE_REFERENCE", "SOURCE_CONFLICT", "UNKNOWN"}
TITLE_VERSION = re.compile(r"^IXOR_Benchmark_v([0-9]+)_[A-Za-z0-9_]+$")


def _generation(title: Any, label: str) -> int:
    match = TITLE_VERSION.fullmatch(title) if isinstance(title, str) else None
    if match is None:
        raise SourceFreshnessError(f"{label} must be an exact checkpoint title")
    return int(match.group(1))


def _timestamp_ns(value: Any) -> str:
    if not isinstance(value, str):
        raise SourceFreshnessError("evaluated_at must be a timezone-aware timestamp")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceFreshnessError("evaluated_at is not an ISO 8601 timestamp") from exc
    if moment.tzinfo is None:
        raise SourceFreshnessError("evaluated_at requires a timezone")
    utc = moment.astimezone(timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = utc - epoch
    return str(((delta.days * 86400 + delta.seconds) * 1_000_000 +
                 delta.microseconds) * 1000)


def _attr(name: str, value: str | int | bool) -> dict[str, Any]:
    if isinstance(value, bool):
        encoded = {"boolValue": value}
    elif isinstance(value, int):
        encoded = {"intValue": str(value)}
    else:
        encoded = {"stringValue": value}
    return {"key": name, "value": encoded}


def to_otlp_json(report: dict[str, Any]) -> dict[str, Any]:
    """Build one OTLP ExportLogsServiceRequest-compatible JSON object."""
    if not isinstance(report, dict) or report.get("schema_version") != 1 or \
            report.get("record_type") != "source_freshness_observation" or \
            report.get("event_name") != EVENT_NAME:
        raise SourceFreshnessError("expected one source-freshness observation")
    if (report.get("write_authority") != "NONE" or
            report.get("mechanical_acceptance_granted") is not False or
            report.get("evidence_admission_performed") is not False or
            report.get("source_mutation_performed") is not False):
        raise SourceFreshnessError("telemetry input cannot carry engineering promotion or mutation")
    if report.get("input_verification") != "CALLER_SUPPLIED_UNVERIFIED" or \
            report.get("freshness_claim_scope") != "POINT_IN_TIME":
        raise SourceFreshnessError("telemetry input exceeds its provenance or temporal scope")
    comparisons = report.get("comparisons")
    if not isinstance(comparisons, dict) or set(comparisons) != {"github", "google_drive"}:
        raise SourceFreshnessError("expected GitHub and Drive comparisons")
    states = {}
    for name in ("github", "google_drive"):
        comparison = comparisons[name]
        if not isinstance(comparison, dict) or comparison.get("state") not in STATES:
            raise SourceFreshnessError(f"invalid {name} comparison state")
        states[name] = comparison["state"]
    found = set(states.values())
    expected = ("SOURCE_CONFLICT" if "SOURCE_CONFLICT" in found else
                "STALE_REFERENCE" if "STALE_REFERENCE" in found else
                "UNKNOWN" if "UNKNOWN" in found else "ALIGNED_AT_CHECKPOINT_LEVEL")
    if report.get("overall_state") != expected:
        raise SourceFreshnessError("overall state does not match source comparisons")
    anchor = report.get("live_anchor")
    if not isinstance(anchor, dict):
        raise SourceFreshnessError("live anchor is missing")
    attributes = [
        _attr("cadgrounded.freshness.overall_state", expected),
        _attr("cadgrounded.freshness.github.state", states["github"]),
        _attr("cadgrounded.freshness.google_drive.state", states["google_drive"]),
        _attr("cadgrounded.freshness.claim_scope", "POINT_IN_TIME"),
        _attr("cadgrounded.freshness.input_verification", "CALLER_SUPPLIED_UNVERIFIED"),
        _attr("cadgrounded.freshness.write_authority", "NONE"),
        _attr("cadgrounded.freshness.mechanical_acceptance_granted", False),
        _attr("cadgrounded.freshness.live.generation",
              _generation(anchor.get("document_title_exact"), "live checkpoint")),
    ]
    for source in ("github", "google_drive"):
        title = comparisons[source].get("document_title_exact")
        if title is not None:
            attributes.append(_attr(f"cadgrounded.freshness.{source}.generation",
                                    _generation(title, f"{source} checkpoint")))

    warn = expected != "ALIGNED_AT_CHECKPOINT_LEVEL"
    return {
        "resourceLogs": [{
            "resource": {"attributes": [_attr("service.name", "cadgrounded-freshness-monitor")]},
            "scopeLogs": [{
                "scope": {"name": "cadgrounded.source_freshness", "version": "1"},
                "logRecords": [{
                    "timeUnixNano": _timestamp_ns(report.get("evaluated_at")),
                    "severityNumber": 13 if warn else 9,
                    "severityText": "WARN" if warn else "INFO",
                    "eventName": EVENT_NAME,
                    "body": {"stringValue": "Cross-source checkpoint freshness checked."},
                    "attributes": attributes,
                }],
            }],
        }],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="freshness report, or captured connector bundle")
    parser.add_argument("--bundle", action="store_true", help="normalize captured responses first")
    args = parser.parse_args()
    try:
        value = json.loads(args.input.read_text(encoding="utf-8-sig"))
        report = compare(normalize(value)) if args.bundle else value
        output = to_otlp_json(report)
    except (OSError, json.JSONDecodeError, SourceFreshnessError) as exc:
        parser.error(str(exc))
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
