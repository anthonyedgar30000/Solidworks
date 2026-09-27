#!/usr/bin/env python3
"""Send one bounded source-freshness OTLP event to a local HTTP collector."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from source_freshness import SourceFreshnessError, compare
from source_freshness_bundle import normalize
from source_freshness_otlp import to_otlp_json


def send(report: dict, port: int = 4318) -> None:
    """POST only the projected event to OTLP/HTTP JSON on loopback."""
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    payload = to_otlp_json(report)
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:{port}/v1/logs", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    # Ignore proxy settings for local telemetry; neither source data nor the
    # event should be routed to a configured HTTP proxy.
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=3) as response:
            if response.status != 200:
                raise ValueError(f"collector returned HTTP {response.status}")
            response_body = response.read(4097)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"local collector delivery failed: {type(exc).__name__}") from exc
    if len(response_body) > 4096:
        raise ValueError("collector response exceeds 4096 bytes")
    if response_body:
        try:
            result = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("collector response is not JSON") from exc
        if not isinstance(result, dict) or result.get("partialSuccess") is not None:
            raise ValueError("collector response reports partial success or is invalid")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="freshness report or captured response bundle")
    parser.add_argument("--bundle", action="store_true", help="normalize captured responses first")
    parser.add_argument("--port", type=int, default=4318, help="local OTLP/HTTP port (default: 4318)")
    args = parser.parse_args()
    try:
        value = json.loads(args.input.read_text(encoding="utf-8-sig"))
        report = compare(normalize(value)) if args.bundle else value
        send(report, args.port)
    except (OSError, ValueError, json.JSONDecodeError, SourceFreshnessError) as exc:
        parser.error(str(exc))
    print("One bounded source-freshness event accepted by local collector (HTTP 200).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
