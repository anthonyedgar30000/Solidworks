#!/usr/bin/env python3
"""Normalize captured connector responses for point-in-time source monitoring.

The input bundle contains already collected read responses. This code verifies
their internal consistency and content hashes, but cannot authenticate the
caller or prove the responses originated at the named services.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from source_freshness import SourceFreshnessError, compare

CANONICAL_TITLE = "CADGrounded Remote Queue v1 — Canonical Identity"
FRESHNESS_SENTENCE = re.compile(
    r"The latest live verification observed "
    r"(IXOR_Benchmark_v[0-9]+_[A-Za-z0-9_]+) as the active document\."
)
SHA40 = re.compile(r"[0-9a-f]{40}")


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SourceFreshnessError(f"{name} must be an object")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceFreshnessError(f"{name} must be nonempty text")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode("utf-8")).hexdigest()


def normalize(bundle: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 1:
        raise SourceFreshnessError("expected source-response bundle schema_version 1")

    sw = _object(bundle.get("solidworks"), "solidworks")
    sw_response = _object(sw.get("response"), "solidworks.response")
    sw_result = _object(sw_response.get("result"), "solidworks.response.result")
    sw_document = _object(sw_result.get("active_document"), "active_document")
    if (sw.get("tool") != "cadgrounded_solidworks_sw_status" or
            sw_response.get("ok") is not True or
            sw_result.get("source_classification") != "verified_from_solidworks_api" or
            sw_document.get("document_type") != "assembly"):
        raise SourceFreshnessError("SOLIDWORKS status response is not an assembly read")
    title = _text(sw_document.get("title"), "active_document.title")
    path = _text(sw_document.get("path"), "active_document.path")
    if not path.casefold().endswith(title.casefold() + ".sldasm"):
        raise SourceFreshnessError("SOLIDWORKS title and path do not bind to one assembly")

    gh = _object(bundle.get("github"), "github")
    gh_response = _object(gh.get("response"), "github.response")
    commit = _text(gh.get("commit_sha"), "github.commit_sha")
    if not SHA40.fullmatch(commit):
        raise SourceFreshnessError("github.commit_sha must be a full commit SHA")
    repository = _text(gh.get("repository_full_name"), "github.repository_full_name")
    record_path = _text(gh.get("path"), "github.path")
    if not (record_path.startswith("agent-registry/reasoning/runtime/") and
            record_path.endswith(".json")):
        raise SourceFreshnessError("GitHub source must be a runtime EvidenceRecord path")
    content = _text(gh_response.get("content"), "github.response.content")
    raw = content.encode("utf-8")
    blob_sha = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if gh_response.get("sha") != blob_sha:
        raise SourceFreshnessError("GitHub blob SHA does not match returned content")
    try:
        record = _object(json.loads(content.lstrip("\ufeff")), "GitHub EvidenceRecord")
    except json.JSONDecodeError as exc:
        raise SourceFreshnessError("GitHub EvidenceRecord is invalid JSON") from exc
    if (record.get("schema_version") != 1 or
            record.get("record_type") != "evidence" or
            record.get("evidence_type") != "solidworks_observation" or
            record.get("evidence_state") != "VERIFIED" or
            record.get("source_authority") != "SOLIDWORKS_LIVE_STATE" or
            record.get("source_classification") != "verified_from_solidworks_api" or
            record.get("mechanical_acceptance_granted") is not False):
        raise SourceFreshnessError("GitHub file is not a bounded verified SolidWorksObservation")
    subject = _object(record.get("subject"), "GitHub EvidenceRecord.subject")
    gh_title = _text(subject.get("document_title_exact"), "EvidenceRecord document title")
    gh_path = _text(subject.get("document_path_exact"), "EvidenceRecord document path")
    payload = _object(record.get("payload"), "GitHub EvidenceRecord.payload")
    payload_doc = _object(payload.get("document"), "GitHub EvidenceRecord.payload.document")
    if payload_doc and (payload_doc.get("title") != gh_title or payload_doc.get("path") != gh_path):
        raise SourceFreshnessError("EvidenceRecord subject and payload document disagree")

    drive = _object(bundle.get("google_drive"), "google_drive")
    drive_response = _object(drive.get("response"), "google_drive.response")
    doc_id = _text(drive.get("document_id"), "google_drive.document_id")
    revision = _text(drive_response.get("revisionId"), "google_drive revisionId")
    if drive_response.get("documentId") != doc_id or drive_response.get("title") != CANONICAL_TITLE:
        raise SourceFreshnessError("Drive document identity does not match canonical identity")
    paragraphs = drive_response.get("paragraphs")
    if not isinstance(paragraphs, list):
        raise SourceFreshnessError("Drive response has no paragraph inventory")
    names = []
    for index, item in enumerate(paragraphs[:-1]):
        if isinstance(item, dict) and item.get("text") == "Freshness rule":
            following = paragraphs[index + 1]
            if isinstance(following, dict) and isinstance(following.get("text"), str):
                names += FRESHNESS_SENTENCE.findall(following["text"])
    if len(names) != 1:
        raise SourceFreshnessError("canonical Drive freshness statement is missing or ambiguous")

    return {
        "schema_version": 1,
        "solidworks": {
            "retrieval_state": "OK", "observed_at": sw.get("observed_at"),
            "source_ref": f"{sw['tool']}#response_sha256={_digest(sw_response)}",
            "document_title_exact": title, "document_path_exact": path,
        },
        "github": {
            "retrieval_state": "OK", "reference_kind": "admitted_evidence",
            "observed_at": gh.get("observed_at"),
            "source_ref": f"{repository}/{record_path}@{commit}#blob={blob_sha};evidence_id={_text(record.get('evidence_id'), 'evidence_id')}",
            "document_title_exact": gh_title, "document_path_exact": gh_path,
        },
        "google_drive": {
            "retrieval_state": "OK", "reference_kind": "canonical_identity",
            "observed_at": drive.get("observed_at"),
            "source_ref": f"{doc_id}@{revision}#response_sha256={_digest(drive_response)}",
            "document_title_exact": names[0],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="captured read-only connector responses")
    args = parser.parse_args()
    try:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8-sig"))
        report = compare(normalize(bundle))
    except (OSError, json.JSONDecodeError, SourceFreshnessError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
