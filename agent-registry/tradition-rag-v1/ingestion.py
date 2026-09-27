from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

LANE_PRIORITY = {
    "AUTHORITATIVE": 0,
    "PROFESSIONAL_PRACTICE": 1,
    "FIELD_CHATTER": 2,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def append_jsonl(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_source_id(source_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", source_id)


def domain_family(host: str | None) -> str:
    if not host:
        return ""
    host = host.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


class VisibleTextParser(HTMLParser):
    BLOCK_TAGS = {
        "p", "div", "section", "article", "main", "li", "tr", "td", "th",
        "h1", "h2", "h3", "h4", "h5", "h6", "br",
    }
    IGNORE_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignore_depth = 0
        self._parts: list[str] = []
        self.title = ""
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self.IGNORE_TAGS:
            self._ignore_depth += 1
        if tag == "title":
            self._in_title = True
        if self._ignore_depth == 0 and tag in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
            self.title = " ".join(self._title_parts).strip()
        if self._ignore_depth == 0 and tag in self.BLOCK_TAGS:
            self._parts.append("\n")
        if tag in self.IGNORE_TAGS and self._ignore_depth:
            self._ignore_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data.strip())
        if self._ignore_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def normalize_text(value: str) -> str:
    lines = []
    for raw in value.replace("\r", "\n").split("\n"):
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def looks_like_access_challenge(final_url: str, title: str, text: str) -> bool:
    url_lower = final_url.lower()
    if any(marker in url_lower for marker in ("/challenge", "captcha", "verify-human")):
        return True
    sample = (title + "\n" + text[:3000]).lower()
    markers = (
        "verify you are human",
        "checking your browser",
        "enable javascript and cookies",
        "access denied",
        "security challenge",
        "captcha",
        "cloudflare ray id",
    )
    return any(marker in sample for marker in markers)


def source_action(source: dict, policy: dict) -> dict:
    mode = source["storage_mode"]
    if mode not in policy["storage_modes"]:
        raise ValueError(f"Unknown storage mode {mode} for {source['source_id']}")
    mode_policy = policy["storage_modes"][mode]
    return {
        "source_id": source["source_id"],
        "storage_mode": mode,
        "network_body_ingestion": bool(mode_policy["network_body_ingestion"]),
        "lane": source["lane"],
        "url": source["url"],
    }


def latest_pointer_path(data_root: Path, source_id: str) -> Path:
    return data_root / "latest" / f"{safe_source_id(source_id)}.json"


def source_record_dir(data_root: Path, source_id: str) -> Path:
    return data_root / "source-records" / safe_source_id(source_id)


def checks_path(data_root: Path, source_id: str) -> Path:
    return data_root / "checks" / f"{safe_source_id(source_id)}.jsonl"


def text_path(data_root: Path, normalized_sha256: str) -> Path:
    return data_root / "texts" / f"{normalized_sha256}.txt"


def load_latest(data_root: Path, source_id: str) -> dict | None:
    path = latest_pointer_path(data_root, source_id)
    return read_json(path) if path.exists() else None


def load_last_check(data_root: Path, source_id: str) -> dict | None:
    path = checks_path(data_root, source_id)
    if not path.exists():
        return None
    last = None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            last = json.loads(line)
    return last


def check_event(source: dict, state: str, **extra) -> dict:
    event = {
        "source_id": source["source_id"],
        "checked_at_utc": iso_z(utcnow()),
        "state": state,
        "lane": source["lane"],
        "storage_mode": source["storage_mode"],
        "url": source["url"],
        "mechanical_acceptance_granted": False,
        "cad_write_authority": "NONE",
    }
    event.update(extra)
    return event


def content_type_base(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def decode_body(raw: bytes, headers) -> str:
    charset = None
    try:
        charset = headers.get_content_charset()
    except AttributeError:
        pass
    return raw.decode(charset or "utf-8", errors="replace")


def html_fragment_text(value: str) -> str:
    parser = VisibleTextParser()
    parser.feed(value)
    parser.close()
    return normalize_text(parser.text())


def extract_feed_text(decoded: str) -> tuple[str, str]:
    root = ET.fromstring(decoded)
    ns = "{http://www.w3.org/2005/Atom}"
    feed_title = normalize_text(root.findtext(ns + "title") or "")
    parts = []
    for entry in root.findall(ns + "entry"):
        title = normalize_text(entry.findtext(ns + "title") or "")
        updated = normalize_text(entry.findtext(ns + "updated") or "")
        content = entry.findtext(ns + "content") or entry.findtext(ns + "summary") or ""
        content = html_fragment_text(content)
        link = ""
        for link_node in entry.findall(ns + "link"):
            href = link_node.attrib.get("href", "")
            rel = link_node.attrib.get("rel", "alternate")
            if href and rel == "alternate":
                link = href
                break
            if href and not link:
                link = href
        entry_parts = [value for value in (title, content, f"Entry: {link}" if link else "", f"Updated: {updated}" if updated else "") if value]
        if entry_parts:
            parts.append("\n".join(entry_parts))
    return feed_title, normalize_text("\n\n".join(parts))


def extract_json_text(decoded: str) -> tuple[str, str]:
    payload = json.loads(decoded)
    items = payload.get("items")
    if not isinstance(items, list):
        return "JSON source", normalize_text(decoded)

    parts = []
    for item in items:
        title = html_fragment_text(str(item.get("title") or ""))
        body = html_fragment_text(str(item.get("body") or ""))
        link = str(item.get("link") or "")
        owner = item.get("owner") or {}
        author = str(owner.get("display_name") or "")
        tags = ", ".join(str(tag) for tag in (item.get("tags") or []))
        license_name = str(item.get("content_license") or "")
        activity = item.get("last_activity_date")
        if isinstance(activity, (int, float)):
            activity_text = iso_z(datetime.fromtimestamp(activity, timezone.utc))
        else:
            activity_text = ""

        entry_parts = [
            f"Question: {title}" if title else "",
            body,
            f"Author: {author}" if author else "",
            f"Tags: {tags}" if tags else "",
            f"Link: {link}" if link else "",
            f"License: {license_name}" if license_name else "",
            f"Updated: {activity_text}" if activity_text else "",
        ]
        entry_text = "\n".join(value for value in entry_parts if value)
        if entry_text:
            parts.append(entry_text)

    quota_remaining = payload.get("quota_remaining")
    quota_line = (
        f"API quota remaining at capture: {quota_remaining}"
        if quota_remaining is not None
        else ""
    )
    text = normalize_text("\n\n".join(parts))
    if quota_line:
        text = normalize_text(text + "\n" + quota_line)
    return "Stack Exchange API", text


def extract_visible_text(raw: bytes, content_type: str, headers) -> tuple[str, str]:
    decoded = decode_body(raw, headers)
    if content_type == "text/plain":
        return "", normalize_text(decoded)
    if content_type == "application/json":
        return extract_json_text(decoded)
    if content_type in {"application/atom+xml", "application/rss+xml", "application/xml", "text/xml"}:
        return extract_feed_text(decoded)
    parser = VisibleTextParser()
    parser.feed(decoded)
    parser.close()
    return normalize_text(parser.title), normalize_text(parser.text())


_TLS_CONTEXT = None


def verified_tls_context() -> ssl.SSLContext:
    global _TLS_CONTEXT
    if _TLS_CONTEXT is not None:
        return _TLS_CONTEXT

    context = ssl.create_default_context()
    if sys.platform == "win32" and hasattr(ssl, "enum_certificates"):
        for store_name in ("ROOT", "CA"):
            try:
                certificates = ssl.enum_certificates(store_name)
            except OSError:
                continue
            for certificate, encoding, trust in certificates:
                if encoding != "x509_asn":
                    continue
                try:
                    context.load_verify_locations(cadata=certificate)
                except (ssl.SSLError, ValueError):
                    continue

    _TLS_CONTEXT = context
    return context


def read_bounded(response, limit: int) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Response exceeds max_response_bytes={limit}")
    return data


def validate_network_identity(source: dict, final_url: str, policy: dict) -> None:
    registered = urlparse(source["url"])
    observed = urlparse(final_url)
    if registered.scheme not in policy["network"]["allowed_schemes"]:
        raise ValueError(f"Registered source scheme not allowed: {registered.scheme}")
    if observed.scheme not in policy["network"]["allowed_schemes"]:
        raise ValueError(f"Observed redirect scheme not allowed: {observed.scheme}")
    if policy["network"]["redirect_policy"] == "SAME_DOMAIN_FAMILY":
        if domain_family(registered.hostname) != domain_family(observed.hostname):
            raise ValueError(
                f"Redirect left source domain family: {registered.hostname} -> {observed.hostname}"
            )


def fetch_source(source: dict, policy: dict, data_root: Path) -> dict:
    action = source_action(source, policy)
    if not action["network_body_ingestion"]:
        event = check_event(source, "SKIPPED_POLICY_METADATA_ONLY")
        append_jsonl(checks_path(data_root, source["source_id"]), event)
        return event

    registered = urlparse(source["url"])
    if registered.scheme not in policy["network"]["allowed_schemes"]:
        raise ValueError(f"Source URL scheme not allowed: {registered.scheme}")

    latest = load_latest(data_root, source["source_id"])
    headers = {"User-Agent": policy["network"]["user_agent"], "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1"}
    if latest:
        if latest.get("etag"):
            headers["If-None-Match"] = latest["etag"]
        if latest.get("last_modified"):
            headers["If-Modified-Since"] = latest["last_modified"]

    request = urllib.request.Request(source["url"], headers=headers, method="GET")
    try:
        response = urllib.request.urlopen(
            request,
            timeout=int(policy["network"]["timeout_seconds"]),
            context=verified_tls_context(),
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 304 and latest:
            event = check_event(
                source,
                "UNCHANGED_NOT_MODIFIED",
                source_record_id=latest["source_record_id"],
                normalized_sha256=latest.get("normalized_sha256"),
            )
            append_jsonl(checks_path(data_root, source["source_id"]), event)
            latest["last_checked_at_utc"] = event["checked_at_utc"]
            write_json_atomic(latest_pointer_path(data_root, source["source_id"]), latest)
            return event
        event = check_event(
            source,
            "FETCH_FAILED_HTTP",
            http_status=exc.code,
            error=str(exc),
            retry_after=exc.headers.get("Retry-After") if exc.headers else None,
            rate_limit_reset=exc.headers.get("X-RateLimit-Reset") if exc.headers else None,
        )
        append_jsonl(checks_path(data_root, source["source_id"]), event)
        return event
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        event = check_event(source, "FETCH_FAILED", error=str(exc))
        append_jsonl(checks_path(data_root, source["source_id"]), event)
        return event

    with response:
        final_url = response.geturl()
        try:
            validate_network_identity(source, final_url, policy)
        except ValueError as exc:
            event = check_event(source, "SOURCE_IDENTITY_MISMATCH", observed_url=final_url, error=str(exc))
            append_jsonl(checks_path(data_root, source["source_id"]), event)
            return event

        content_type = content_type_base(response.headers.get("Content-Type"))
        if content_type not in policy["network"]["allowed_content_types"]:
            event = check_event(
                source,
                "CONTENT_TYPE_BLOCKED",
                content_type=content_type,
                observed_url=final_url,
            )
            append_jsonl(checks_path(data_root, source["source_id"]), event)
            return event

        try:
            raw = read_bounded(response, int(policy["network"]["max_response_bytes"]))
        except ValueError as exc:
            event = check_event(source, "RESPONSE_TOO_LARGE", observed_url=final_url, error=str(exc))
            append_jsonl(checks_path(data_root, source["source_id"]), event)
            return event

        page_title, normalized = extract_visible_text(raw, content_type, response.headers)
        if looks_like_access_challenge(final_url, page_title, normalized):
            event = check_event(
                source,
                "ACCESS_CHALLENGE_BLOCKED",
                observed_url=final_url,
                page_title=page_title,
            )
            append_jsonl(checks_path(data_root, source["source_id"]), event)
            return event

        mode_policy = policy["storage_modes"][source["storage_mode"]]
        normalized = normalized[: int(mode_policy["normalized_char_limit"])].strip()
        if not normalized:
            event = check_event(source, "NO_NORMALIZED_TEXT", observed_url=final_url)
            append_jsonl(checks_path(data_root, source["source_id"]), event)
            return event

        raw_sha = sha256_bytes(raw)
        normalized_sha = sha256_text(normalized)
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        observed_at = iso_z(utcnow())


        existing_same = latest and latest.get("raw_sha256") == raw_sha
        if existing_same:
            state = "UNCHANGED_HASH"
            latest["last_checked_at_utc"] = observed_at
            latest["etag"] = etag or latest.get("etag")
            latest["last_modified"] = last_modified or latest.get("last_modified")
            write_json_atomic(latest_pointer_path(data_root, source["source_id"]), latest)
            event = check_event(
                source,
                state,
                source_record_id=latest["source_record_id"],
                raw_sha256=raw_sha,
                normalized_sha256=normalized_sha,
                observed_url=final_url,
            )
            append_jsonl(checks_path(data_root, source["source_id"]), event)
            return event

        prior_hash = latest.get("raw_sha256") if latest else None
        change_state = "NEW" if not latest else "CHANGED"
        record_id = (
            f"SRCREC.{safe_source_id(source['source_id'])}."
            f"{observed_at.replace(':', '').replace('-', '')}.{raw_sha[:12]}"
        )
        txt_path = text_path(data_root, normalized_sha)
        if not txt_path.exists():
            txt_path.parent.mkdir(parents=True, exist_ok=True)
            txt_path.write_text(normalized, encoding="utf-8")

        record = {
            "schema_version": 1,
            "record_type": "tradition_rag_source_observation",
            "source_record_id": record_id,
            "source_id": source["source_id"],
            "source_lane": source["lane"],
            "authority_class": source["authority_class"],
            "traditions": source["traditions"],
            "storage_mode": source["storage_mode"],
            "registered_url": source["url"],
            "observed_url": final_url,
            "observed_at_utc": observed_at,
            "page_title": page_title or source["title"],
            "http_status": getattr(response, "status", 200),
            "content_type": content_type,
            "etag": etag,
            "last_modified": last_modified,
            "raw_sha256": raw_sha,
            "normalized_sha256": normalized_sha,
            "normalized_chars": len(normalized),
            "text_path": str(txt_path),
            "raw_storage": "HASH_ONLY",
            "state": change_state,
            "previous_raw_sha256": prior_hash,
            "retrieval_authority": "REFERENCE_ONLY",
            "mechanical_acceptance_granted": False,
            "cad_write_authority": "NONE",
        }

        record_dir = source_record_dir(data_root, source["source_id"])
        record_dir.mkdir(parents=True, exist_ok=True)
        record_file = record_dir / f"{record_id}.json"
        if record_file.exists():
            raise RuntimeError(f"Immutable source record already exists: {record_file}")
        write_json_atomic(record_file, record)

        pointer = {
            "source_id": source["source_id"],
            "source_record_id": record_id,
            "record_path": str(record_file),
            "raw_sha256": raw_sha,
            "normalized_sha256": normalized_sha,
            "observed_at_utc": observed_at,
            "last_checked_at_utc": observed_at,
            "etag": etag,
            "last_modified": last_modified,
            "page_title": record["page_title"],
            "observed_url": final_url,
            "state": change_state,
        }
        write_json_atomic(latest_pointer_path(data_root, source["source_id"]), pointer)
        event = check_event(
            source,
            change_state,
            source_record_id=record_id,
            raw_sha256=raw_sha,
            normalized_sha256=normalized_sha,
            observed_url=final_url,
        )
        append_jsonl(checks_path(data_root, source["source_id"]), event)
        return event


def paragraph_chunks(text: str, size: int, overlap: int) -> list[str]:
    if size <= 0:
        return []
    if overlap < 0 or overlap >= size:
        raise ValueError("chunk overlap must be >= 0 and < chunk size")
    normalized = normalize_text(text)
    if not normalized:
        return []

    chunks = []
    start = 0
    length = len(normalized)
    while start < length:
        hard_end = min(start + size, length)
        end = hard_end
        if hard_end < length:
            search_floor = start + max(1, size // 2)
            newline = normalized.rfind("\n", search_floor, hard_end)
            space = normalized.rfind(" ", search_floor, hard_end)
            boundary = max(newline, space)
            if boundary > start:
                end = boundary
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        next_start = max(0, end - overlap)
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


def load_record(path_value: str) -> dict:
    return read_json(Path(path_value))


def current_records(registry: dict, data_root: Path) -> list[dict]:
    records = []
    for source in registry["sources"]:
        latest = load_latest(data_root, source["source_id"])
        if not latest or not latest.get("record_path"):
            continue
        record = load_record(latest["record_path"])
        record["_source_registry"] = source
        records.append(record)
    return records


def dedup_annotations(records: list[dict]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for record in records:
        groups.setdefault(record["normalized_sha256"], []).append(record)

    annotations: dict[str, dict] = {}
    for normalized_sha, members in groups.items():
        ordered = sorted(
            members,
            key=lambda r: (
                LANE_PRIORITY.get(r["source_lane"], 99),
                r["source_id"],
                r["source_record_id"],
            ),
        )
        canonical = ordered[0]["source_record_id"]
        for record in members:
            annotations[record["source_record_id"]] = {
                "content_group_sha256": normalized_sha,
                "duplicate_group_size": len(members),
                "duplicate_of_source_record_id": (
                    None if record["source_record_id"] == canonical else canonical
                ),
            }
    return annotations


def build_projection(repo_dir: Path, data_root: Path) -> dict:
    registry = read_json(repo_dir / "sources.v1.json")
    policy = read_json(repo_dir / "ingestion-policy.v1.json")
    records = current_records(registry, data_root)
    annotations = dedup_annotations(records)
    projected = []

    for record in sorted(records, key=lambda r: r["source_id"]):
        source = record["_source_registry"]
        mode_policy = policy["storage_modes"][source["storage_mode"]]
        text = Path(record["text_path"]).read_text(encoding="utf-8")
        chunks = paragraph_chunks(
            text,
            int(mode_policy["chunk_size_chars"]),
            int(mode_policy["chunk_overlap_chars"]),
        )
        ann = annotations[record["source_record_id"]]
        for ordinal, chunk in enumerate(chunks):
            chunk_sha = sha256_text(chunk)
            projected.append(
                {
                    "chunk_id": (
                        f"INGEST:{safe_source_id(source['source_id'])}:"
                        f"{record['raw_sha256'][:12]}:{ordinal:04d}"
                    ),
                    "chunk_kind": "NETWORK_SOURCE",
                    "source_id": source["source_id"],
                    "source_lane": source["lane"],
                    "authority_class": source["authority_class"],
                    "traditions": source["traditions"],
                    "title": record["page_title"] or source["title"],
                    "body": chunk,
                    "source_uri": record["observed_url"],
                    "source_record_id": record["source_record_id"],
                    "observed_at_utc": record["observed_at_utc"],
                    "raw_sha256": record["raw_sha256"],
                    "normalized_document_sha256": record["normalized_sha256"],
                    "content_group_sha256": ann["content_group_sha256"],
                    "duplicate_group_size": ann["duplicate_group_size"],
                    "duplicate_of_source_record_id": ann["duplicate_of_source_record_id"],
                    "chunk_ordinal": ordinal,
                    "chunk_sha256": chunk_sha,
                    "storage_mode": source["storage_mode"],
                    "mechanical_acceptance_granted": False,
                    "cad_write_authority": "NONE",
                }
            )

    active_path = data_root / "active_chunks.jsonl"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    temp = active_path.with_suffix(".jsonl.tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in projected:
            handle.write(json.dumps(chunk, sort_keys=True) + "\n")
    temp.replace(active_path)

    summary = {
        "projected_at_utc": iso_z(utcnow()),
        "active_chunks_path": str(active_path),
        "source_records": len(records),
        "chunks": len(projected),
        "duplicate_source_records": sum(
            1 for value in annotations.values() if value["duplicate_of_source_record_id"]
        ),
        "mechanical_acceptance_authority": "NONE",
        "cad_write_authority": "NONE",
    }
    write_json_atomic(data_root / "projection-status.json", summary)
    return summary


def within_lane_ttl(source: dict, checked_at: str | None, policy: dict) -> bool:
    if not checked_at:
        return False
    checked_dt = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    ttl = int(policy["freshness_days_by_lane"][source["lane"]])
    return utcnow() <= checked_dt + timedelta(days=ttl)


def auto_refresh_due(source: dict, policy: dict, data_root: Path) -> bool:
    if not source_action(source, policy)["network_body_ingestion"]:
        return False
    last_check = load_last_check(data_root, source["source_id"])
    if not last_check:
        return True
    return not within_lane_ttl(source, last_check.get("checked_at_utc"), policy)


def freshness_state(
    source: dict,
    latest: dict | None,
    last_check: dict | None,
    policy: dict,
) -> str:
    if not source_action(source, policy)["network_body_ingestion"]:
        return "POLICY_METADATA_ONLY"
    if latest:
        checked = latest.get("last_checked_at_utc")
        return "FRESH" if within_lane_ttl(source, checked, policy) else "STALE"
    if last_check:
        return (
            "CHECKED_NO_ACTIVE_RECORD"
            if within_lane_ttl(source, last_check.get("checked_at_utc"), policy)
            else "STALE_NO_ACTIVE_RECORD"
        )
    return "NEVER_CHECKED"


def ingestion_status(repo_dir: Path, data_root: Path) -> dict:
    registry = read_json(repo_dir / "sources.v1.json")
    policy = read_json(repo_dir / "ingestion-policy.v1.json")
    rows = []
    for source in registry["sources"]:
        latest = load_latest(data_root, source["source_id"])
        last_check = load_last_check(data_root, source["source_id"])
        action = source_action(source, policy)
        rows.append(
            {
                "source_id": source["source_id"],
                "lane": source["lane"],
                "storage_mode": source["storage_mode"],
                "network_body_ingestion": action["network_body_ingestion"],
                "freshness": freshness_state(source, latest, last_check, policy),
                "source_record_id": latest.get("source_record_id") if latest else None,
                "raw_sha256": latest.get("raw_sha256") if latest else None,
                "last_checked_at_utc": latest.get("last_checked_at_utc") if latest else None,
                "last_attempt_at_utc": last_check.get("checked_at_utc") if last_check else None,
                "last_check_state": last_check.get("state") if last_check else None,
                "auto_refresh_due": auto_refresh_due(source, policy, data_root),
            }
        )
    return {
        "service_id": "CADGROUNDED.TRADITION_RAG.INGESTION.V1",
        "sources": rows,
        "mechanical_acceptance_authority": "NONE",
        "cad_write_authority": "NONE",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CADGrounded Tradition RAG ingestion")
    parser.add_argument(
        "--repo-dir",
        default=str(Path(__file__).resolve().parent),
    )
    parser.add_argument(
        "--data-root",
        default=r"C:\CADGrounded\tradition-rag-data",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("plan")
    sub.add_parser("status")
    sub.add_parser("project")

    ingest = sub.add_parser("ingest")
    group = ingest.add_mutually_exclusive_group(required=True)
    group.add_argument("--source")
    group.add_argument("--all-safe", action="store_true")
    ingest.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_dir = Path(args.repo_dir)
    data_root = Path(args.data_root)
    registry = read_json(repo_dir / "sources.v1.json")
    policy = read_json(repo_dir / "ingestion-policy.v1.json")

    if args.command == "plan":
        output = {
            "service_id": "CADGROUNDED.TRADITION_RAG.INGESTION.V1",
            "actions": [source_action(source, policy) for source in registry["sources"]],
            "mechanical_acceptance_authority": "NONE",
            "cad_write_authority": "NONE",
        }
    elif args.command == "status":
        output = ingestion_status(repo_dir, data_root)
    elif args.command == "project":
        output = build_projection(repo_dir, data_root)
    elif args.command == "ingest":
        skipped_fresh = []
        if args.all_safe:
            candidates = [
                source
                for source in registry["sources"]
                if source_action(source, policy)["network_body_ingestion"]
            ]
            if args.force:
                selected = candidates
            else:
                selected = [
                    source
                    for source in candidates
                    if auto_refresh_due(source, policy, data_root)
                ]
                selected_ids = {source["source_id"] for source in selected}
                skipped_fresh = [
                    source["source_id"]
                    for source in candidates
                    if source["source_id"] not in selected_ids
                ]
        else:
            selected = [
                source for source in registry["sources"]
                if source["source_id"] == args.source
            ]
            if not selected:
                raise SystemExit(f"Unknown source_id: {args.source}")

        results = []
        interval = float(policy["network"].get("minimum_interval_seconds", 0))
        for index, source in enumerate(selected):
            if index and interval > 0:
                time.sleep(interval)
            results.append(fetch_source(source, policy, data_root))
        output = {
            "service_id": "CADGROUNDED.TRADITION_RAG.INGESTION.V1",
            "results": results,
            "skipped_recent_source_ids": skipped_fresh,
            "mechanical_acceptance_authority": "NONE",
            "cad_write_authority": "NONE",
        }
    else:
        raise AssertionError(args.command)

    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
