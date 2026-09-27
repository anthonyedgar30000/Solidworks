#!/usr/bin/env python3
"""Compare point-in-time source references without promoting engineering claims.

Input is a manually collected, provenance-bound three-source snapshot. This
module makes no network, SOLIDWORKS, Drive, database, or ledger calls.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCES = ("solidworks", "github", "google_drive")
TITLE = re.compile(r"^IXOR_Benchmark_v([0-9]+)_[A-Za-z0-9_]+$")


class SourceFreshnessError(ValueError):
    pass


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SourceFreshnessError(f"{label} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceFreshnessError(f"{label} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise SourceFreshnessError(f"{label} must include a timezone")
    return value


def _title(value: Any, label: str) -> tuple[str, int]:
    if not isinstance(value, str):
        raise SourceFreshnessError(f"{label} must be an exact assembly title")
    match = TITLE.fullmatch(value)
    if not match:
        raise SourceFreshnessError(f"{label} must be an IXOR_Benchmark_vN_* title")
    return value, int(match.group(1))


def _source(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    item = snapshot.get(name)
    if not isinstance(item, dict):
        raise SourceFreshnessError(f"{name} must be an object")
    if item.get("retrieval_state") not in {"OK", "UNAVAILABLE"}:
        raise SourceFreshnessError(f"{name}.retrieval_state must be OK or UNAVAILABLE")
    if item["retrieval_state"] == "OK":
        _timestamp(item.get("observed_at"), f"{name}.observed_at")
        if not isinstance(item.get("source_ref"), str) or not item["source_ref"].strip():
            raise SourceFreshnessError(f"{name}.source_ref is required")
        _title(item.get("document_title_exact"), f"{name}.document_title_exact")
        if name == "solidworks" and (not isinstance(item.get("document_path_exact"), str)
                                      or not item["document_path_exact"].strip()):
            raise SourceFreshnessError("solidworks.document_path_exact is required")
        if name == "github" and item.get("reference_kind") != "admitted_evidence":
            raise SourceFreshnessError("github.reference_kind must be admitted_evidence")
        if name == "google_drive" and item.get("reference_kind") != "canonical_identity":
            raise SourceFreshnessError("google_drive.reference_kind must be canonical_identity")
    return item


def compare(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return an observability event; never change EvidenceRecord validity."""
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
        raise SourceFreshnessError("expected schema_version 1 object")
    sources = {name: _source(snapshot, name) for name in SOURCES}
    live = sources["solidworks"]
    if live["retrieval_state"] != "OK":
        raise SourceFreshnessError("a fresh SOLIDWORKS anchor is required")
    live_title, live_version = _title(live["document_title_exact"], "solidworks title")

    comparisons: dict[str, dict[str, Any]] = {}
    for name in ("github", "google_drive"):
        ref = sources[name]
        state = "UNKNOWN"
        reason = "SOURCE_UNAVAILABLE"
        if ref["retrieval_state"] == "OK":
            title, version = _title(ref["document_title_exact"], f"{name} title")
            if version < live_version:
                state, reason = "STALE_REFERENCE", "OLDER_CHECKPOINT_GENERATION"
            elif title != live_title:
                state, reason = "SOURCE_CONFLICT", "DIFFERENT_CHECKPOINT_IDENTITY"
            elif (ref.get("document_path_exact") and
                  ref["document_path_exact"] != live["document_path_exact"]):
                state, reason = "SOURCE_CONFLICT", "DIFFERENT_DOCUMENT_PATH"
            elif (ref.get("configuration_exact") and live.get("configuration_exact") and
                  ref["configuration_exact"] != live["configuration_exact"]):
                state, reason = "SOURCE_CONFLICT", "DIFFERENT_CONFIGURATION"
            else:
                state, reason = "ALIGNED_AT_CHECKPOINT_LEVEL", "SAME_CHECKPOINT_IDENTITY"
        comparisons[name] = {
            "state": state,
            "reason": reason,
            "source_ref": ref.get("source_ref") if ref["retrieval_state"] == "OK" else None,
            "observed_at": ref.get("observed_at") if ref["retrieval_state"] == "OK" else None,
            "document_title_exact": ref.get("document_title_exact") if ref["retrieval_state"] == "OK" else None,
        }

    states = {item["state"] for item in comparisons.values()}
    overall = ("SOURCE_CONFLICT" if "SOURCE_CONFLICT" in states else
               "STALE_REFERENCE" if "STALE_REFERENCE" in states else
               "UNKNOWN" if "UNKNOWN" in states else "ALIGNED_AT_CHECKPOINT_LEVEL")
    return {
        "schema_version": 1,
        "record_type": "source_freshness_observation",
        "event_name": "cadgrounded.source_freshness.checked",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "input_verification": "CALLER_SUPPLIED_UNVERIFIED",
        "freshness_claim_scope": "POINT_IN_TIME",
        "overall_state": overall,
        "live_anchor": {
            "document_title_exact": live_title,
            "document_path_exact": live["document_path_exact"],
            "configuration_exact": live.get("configuration_exact"),
            "source_ref": live["source_ref"],
            "observed_at": live["observed_at"],
        },
        "comparisons": comparisons,
        "ambiguity_bucket": "SOURCE_CONFLICT" if overall == "SOURCE_CONFLICT" else
                            "STALE_STATE" if overall == "STALE_REFERENCE" else
                            "INSUFFICIENT_EVIDENCE" if overall == "UNKNOWN" else None,
        "write_authority": "NONE",
        "mechanical_acceptance_granted": False,
        "evidence_admission_performed": False,
        "source_mutation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="provenance-bound three-source JSON snapshot")
    args = parser.parse_args()
    try:
        report = compare(json.loads(args.snapshot.read_text(encoding="utf-8-sig")))
    except (OSError, json.JSONDecodeError, SourceFreshnessError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
