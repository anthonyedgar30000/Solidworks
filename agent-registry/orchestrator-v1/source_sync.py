"""Fetch exact PLAN-0010 inputs from GitHub main without touching a checkout."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from frontier_runner import INPUTS, run_once


REMOTE = "https://github.com/anthonyedgar30000/Solidworks.git"
RAW_BASE = "https://raw.githubusercontent.com/anthonyedgar30000/Solidworks"
MAX_INPUT_BYTES = 1_000_000
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


class SyncBlocked(ValueError):
    pass


def resolve_main() -> str:
    result = subprocess.run(
        ["git", "ls-remote", REMOTE, "refs/heads/main"],
        capture_output=True, text=True, check=True, timeout=20,
    )
    lines = result.stdout.strip().splitlines()
    if len(lines) != 1:
        raise SyncBlocked("MAIN_REF_UNAVAILABLE")
    parts = lines[0].split()
    if len(parts) != 2 or parts[1] != "refs/heads/main" or not COMMIT_RE.fullmatch(parts[0]):
        raise SyncBlocked("INVALID_MAIN_REF")
    return parts[0]


def download_input(commit: str, path: str) -> bytes:
    if not COMMIT_RE.fullmatch(commit) or path not in INPUTS:
        raise SyncBlocked("INPUT_NOT_ALLOWLISTED")
    url = f"{RAW_BASE}/{commit}/{path}"
    request = Request(url, headers={"User-Agent": "CADGrounded-frontier-sync-v1"})
    with urlopen(request, timeout=15) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.netloc != "raw.githubusercontent.com" or final.path != urlparse(url).path:
            raise SyncBlocked("SOURCE_REDIRECT_REJECTED")
        raw = response.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise SyncBlocked("INPUT_TOO_LARGE")
    # No remote code is executed. Invalid JSON is rejected before persistence.
    json.loads(raw.decode("utf-8-sig"))
    return raw


def materialize_snapshot(commit: str, state_dir: Path, fetch=download_input) -> tuple[Path, dict[str, str]]:
    if not COMMIT_RE.fullmatch(commit):
        raise SyncBlocked("INVALID_COMMIT")
    parent = state_dir / "snapshots"
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / commit
    pending = Path(tempfile.mkdtemp(prefix=".pending-", dir=parent))
    hashes: dict[str, str] = {}
    try:
        for path in INPUTS:
            raw = fetch(commit, path)
            if len(raw) > MAX_INPUT_BYTES:
                raise SyncBlocked("INPUT_TOO_LARGE")
            json.loads(raw.decode("utf-8-sig"))
            hashes[path] = hashlib.sha256(raw).hexdigest()
            target = pending / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        (pending / "source_manifest.json").write_text(
            json.dumps({"source_commit_sha": commit, "input_sha256": hashes}, indent=2) + "\n",
            encoding="utf-8",
        )
        if destination.exists():
            manifest = json.loads((destination / "source_manifest.json").read_text(encoding="utf-8"))
            if manifest != {"source_commit_sha": commit, "input_sha256": hashes}:
                raise SyncBlocked("IMMUTABLE_SNAPSHOT_DRIFT")
            if any(hashlib.sha256((destination / path).read_bytes()).hexdigest() != digest
                   for path, digest in hashes.items()):
                raise SyncBlocked("IMMUTABLE_SNAPSHOT_DRIFT")
        else:
            pending.rename(destination)
        return destination, hashes
    finally:
        if pending.exists():
            shutil.rmtree(pending)


def _write_status(state_dir: Path, status: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=state_dir,
                                         prefix=".status-", delete=False) as output:
            name = output.name
            json.dump(status, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, state_dir / "last_sync_status.json")
    finally:
        if name is not None and os.path.exists(name):
            os.unlink(name)


def sync_once(state_dir: Path, resolve=resolve_main, fetch=download_input) -> dict:
    status = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_repository": REMOTE,
        "execution_authority": "NONE",
    }
    try:
        commit = resolve()
        status["source_commit_sha"] = commit
        snapshot, hashes = materialize_snapshot(commit, state_dir, fetch)
        status["input_sha256"] = hashes
        projection = run_once(snapshot, state_dir)
        status["projection"] = projection
        status["status"] = projection["status"]
    except (SyncBlocked, OSError, UnicodeError, json.JSONDecodeError,
            subprocess.SubprocessError, TimeoutError) as exc:
        status.update(status="BLOCKED", reason=f"{type(exc).__name__}: {exc}")
    _write_status(state_dir, status)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True, type=Path)
    args = parser.parse_args()
    result = sync_once(args.state_dir)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] != "BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
