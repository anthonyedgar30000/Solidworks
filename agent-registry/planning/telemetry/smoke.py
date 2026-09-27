#!/usr/bin/env python3
"""Exercise the real local Collector with a synthetic, unverified fixture."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PLANNING = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLANNING))

from source_freshness import compare  # noqa: E402
from source_freshness_send import send  # noqa: E402
from source_freshness_otlp import EVENT_NAME  # noqa: E402
from test_source_freshness import snapshot  # noqa: E402

COMPOSE = Path(__file__).with_name("compose.yaml")


def exported_event(path: Path) -> dict:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    if len(records) != 1:
        raise ValueError("expected exactly one exported request")
    request = records[0]
    logs = request["resourceLogs"]
    if len(logs) != 1 or len(logs[0]["scopeLogs"]) != 1:
        raise ValueError("expected one resource and scope")
    events = logs[0]["scopeLogs"][0]["logRecords"]
    if len(events) != 1:
        raise ValueError("expected exactly one event")
    if any(secret in json.dumps(request) for secret in
           ("IXOR_Benchmark", "C:\\ChatGPT", "OBS:test", "drive:test")):
        raise ValueError("source identity escaped the bounded projection")
    return events[0]


def main() -> int:
    # The fixture is deliberately caller supplied; no connector is contacted.
    report = compare(snapshot())
    deadline = time.monotonic() + 30
    while True:
        try:
            send(report)
            break
        except ValueError as exc:
            if time.monotonic() >= deadline:
                raise RuntimeError("collector did not accept OTLP/HTTP within 30 seconds") from exc
            time.sleep(0.5)

    with tempfile.TemporaryDirectory() as directory:
        exported = Path(directory) / "freshness.json"
        deadline = time.monotonic() + 30
        while True:
            result = subprocess.run(
                ["docker", "compose", "-f", str(COMPOSE), "cp",
                 "collector:/data/freshness.json", str(exported)],
                capture_output=True, timeout=5, check=False,
            )
            if result.returncode == 0:
                try:
                    event = exported_event(exported)
                    break
                except (ValueError, KeyError, IndexError, json.JSONDecodeError):
                    pass  # The exporter can still be flushing the file.
            if time.monotonic() >= deadline:
                raise RuntimeError("collector did not export one bounded event within 30 seconds")
            time.sleep(0.5)

    if event["eventName"] != EVENT_NAME or event["severityText"] != "WARN":
        raise ValueError("exported event name or severity does not match")
    attributes = {item["key"]: item["value"] for item in event["attributes"]}
    if attributes.get("cadgrounded.freshness.overall_state") != {"stringValue": "STALE_REFERENCE"}:
        raise ValueError("exported state does not match synthetic observation")
    if attributes.get("cadgrounded.freshness.mechanical_acceptance_granted") != {"boolValue": False}:
        raise ValueError("exported event grants mechanical acceptance")
    print("Collector accepted and exported one bounded synthetic freshness event.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
