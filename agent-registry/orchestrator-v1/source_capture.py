"""Capture allowlisted OEM source bytes as unadmitted PLAN-0010 references."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.request import Request, urlopen


REGISTRY = Path(__file__).with_name("source_registry.v1.json")
ALLOWED = {
    "CAB.IXORPLUS.ASSEMBLY_INSTRUCTIONS.202604": (
        "https://www.cab.de/media/pushfile.cfm?file=4444", "application/pdf", "SUBJECT_OEM_DOCUMENT"),
    "HERMA.152C.PRODUCT_PAGE": (
        "https://www.herma.com/machines/products/labeling-machines/wrap-around-labeler-152c/",
        "text/html", "COMPARATIVE_MECHANISM_OEM"),
    "HERMA.WRAP_TECHNOLOGY.PAGE": (
        "https://www.herma.com/machines/types-of-labeling/wrap-around-labeling/",
        "text/html", "COMPARATIVE_MECHANISM_OEM"),
}
MAX_BYTES = 9_000_000


class CaptureBlocked(ValueError):
    pass


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.fragments = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.fragments.append(data)


def validate_registry(registry: dict) -> list[dict]:
    if (registry.get("schema_version") != 1 or registry.get("plan_id") != "PLAN-0010"
            or registry.get("registry_id") != "CADGROUNDED.PLAN-0010.SOURCE_CANDIDATES.V1"):
        raise CaptureBlocked("REGISTRY_PLAN_MISMATCH")
    entries = registry.get("sources")
    if not isinstance(entries, list) or len(entries) != len(ALLOWED):
        raise CaptureBlocked("REGISTRY_SOURCE_SET_CHANGED")
    if {row.get("source_id") for row in entries} != set(ALLOWED):
        raise CaptureBlocked("REGISTRY_SOURCE_SET_CHANGED")
    for row in entries:
        url, media, role = ALLOWED[row["source_id"]]
        if (row.get("url"), row.get("expected_media_type"), row.get("source_role")) != (url, media, role):
            raise CaptureBlocked("SOURCE_AUTHORITY_CHANGED")
        size = row.get("max_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or not (1 <= size <= MAX_BYTES):
            raise CaptureBlocked("SOURCE_SIZE_BOUNDARY_CHANGED")
        markers = row.get("markers")
        if not isinstance(markers, list) or len(markers) > 5 or any(
            not isinstance(m, str) or not (3 <= len(m) <= 80) for m in markers
        ):
            raise CaptureBlocked("INVALID_MARKERS")
    return entries


def fetch_source(row: dict) -> bytes:
    url = row["url"]
    request = Request(url, headers={"User-Agent": "CADGrounded-source-capture-v1"})
    with urlopen(request, timeout=25) as response:
        if response.geturl() != url:
            raise CaptureBlocked("SOURCE_REDIRECT_REJECTED")
        media = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media != row["expected_media_type"]:
            raise CaptureBlocked("SOURCE_MEDIA_CHANGED")
        raw = response.read(row["max_bytes"] + 1)
    if len(raw) > row["max_bytes"]:
        raise CaptureBlocked("SOURCE_TOO_LARGE")
    if media == "application/pdf" and not raw.startswith(b"%PDF-"):
        raise CaptureBlocked("INVALID_PDF")
    if media == "text/html" and b"<html" not in raw[:5000].lower():
        raise CaptureBlocked("INVALID_HTML")
    return raw


def visible_text(raw: bytes) -> str:
    parser = _VisibleText()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return re.sub(r"\s+", " ", " ".join(parser.fragments)).strip()


def candidate_snippets(raw: bytes, markers: list[str]) -> list[dict[str, str]]:
    visible = visible_text(raw)
    lower = visible.casefold()
    matches = []
    for marker in markers:
        at = lower.find(marker.casefold())
        if at >= 0:
            matches.append({"marker": marker, "source_text_window": visible[max(0, at - 80):at + len(marker) + 120]})
    return matches


def _create_immutable(path: Path, raw: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".pending-", delete=False) as stream:
            temp = stream.name
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp, path)
            return True
        except FileExistsError:
            if path.read_bytes() != raw:
                raise CaptureBlocked("IMMUTABLE_RECORD_DRIFT")
            return False
    finally:
        if temp is not None:
            os.unlink(temp)


def capture_one(row: dict, state_dir: Path, fetch=fetch_source) -> dict:
    raw = fetch(row)
    if len(raw) > row["max_bytes"]:
        raise CaptureBlocked("SOURCE_TOO_LARGE")
    digest = hashlib.sha256(raw).hexdigest()
    is_html = row["expected_media_type"] == "text/html"
    text = visible_text(raw) if is_html else ""
    content_digest = hashlib.sha256(text.encode("utf-8")).hexdigest() if is_html else digest
    destination = state_dir / "source_candidates" / row["source_id"] / f"{content_digest}.json"
    if destination.exists():
        prior = json.loads(destination.read_text(encoding="utf-8"))
        # A PDF captured by the initial raw-byte keyed version has the same
        # filename but predates the explicit content_sha256 field.
        prior_content_matches = prior.get("content_sha256") == content_digest or (
            not is_html and "content_sha256" not in prior and prior.get("raw_sha256") == digest
        )
        if (prior.get("source_id") != row["source_id"] or prior.get("source_url") != row["url"]
                or not prior_content_matches or prior.get("source_role") != row["source_role"]
                or prior.get("evidence_state") != "UNADMITTED"
                or prior.get("claim_verification_authority") != "NONE"
                or prior.get("mechanical_acceptance_granted") is not False):
            raise CaptureBlocked("IMMUTABLE_RECORD_DRIFT")
        first_blob = state_dir / "source_blobs" / prior["raw_sha256"]
        if hashlib.sha256(first_blob.read_bytes()).hexdigest() != prior["raw_sha256"]:
            raise CaptureBlocked("IMMUTABLE_RECORD_DRIFT")
        return {"source_id": row["source_id"], "retrieved_raw_sha256": digest,
                "content_sha256": content_digest, "record": str(destination),
                "new": False, "candidate_snippet_count": len(prior.get("candidate_snippets", []))}
    blob = state_dir / "source_blobs" / digest
    _create_immutable(blob, raw)
    record = {
        "schema_version": 1,
        "record_type": "unadmitted_source_candidate",
        "source_id": row["source_id"],
        "source_url": row["url"],
        "publisher": row["publisher"],
        "source_role": row["source_role"],
        "relation_to_v43": row["relation_to_v43"],
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_sha256": digest,
        "content_sha256": content_digest,
        "content_fingerprint_kind": "NORMALIZED_VISIBLE_HTML_TEXT" if is_html else "EXACT_PDF_BYTES",
        "raw_byte_count": len(raw),
        "expected_media_type": row["expected_media_type"],
        "candidate_snippets": candidate_snippets(raw, row["markers"]) if is_html else [],
        "text_extraction_state": "MARKER_WINDOWS_ONLY" if is_html else "NOT_PERFORMED",
        "evidence_state": "UNADMITTED",
        "claim_verification_authority": "NONE",
        "mechanical_acceptance_granted": False,
        "cad_write_authority": "NONE",
    }
    new = _create_immutable(destination, (json.dumps(record, indent=2, sort_keys=True) + "\n").encode())
    return {"source_id": row["source_id"], "retrieved_raw_sha256": digest,
            "content_sha256": content_digest, "record": str(destination), "new": new,
            "candidate_snippet_count": len(record["candidate_snippets"])}


def capture_all(state_dir: Path, fetch=fetch_source, registry_path: Path = REGISTRY) -> dict:
    status = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "execution_authority": "NONE", "results": []}
    try:
        entries = validate_registry(json.loads(registry_path.read_text(encoding="utf-8-sig")))
        for row in entries:
            try:
                status["results"].append(capture_one(row, state_dir, fetch))
            except (CaptureBlocked, OSError, TimeoutError, UnicodeError,
                    json.JSONDecodeError, KeyError, TypeError) as exc:
                status["results"].append({"source_id": row["source_id"], "status": "BLOCKED",
                                          "reason": f"{type(exc).__name__}: {exc}"})
        status["status"] = "CAPTURED" if all("record" in row for row in status["results"]) else "PARTIAL_BLOCKED"
    except (CaptureBlocked, OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
        status.update(status="BLOCKED", reason=f"{type(exc).__name__}: {exc}")
    state_dir.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=state_dir,
                                         prefix=".capture-status-", delete=False) as stream:
            temp = stream.name
            json.dump(status, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temp, state_dir / "last_capture_status.json")
    finally:
        if temp is not None and os.path.exists(temp):
            os.unlink(temp)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True, type=Path)
    args = parser.parse_args()
    result = capture_all(args.state_dir)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "CAPTURED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
