#!/usr/bin/env python3
"""
Optional Ollama investigation selector.

Important:
- It does NOT write verified values into graph.json.
- It does NOT decide project-health state.
- It receives deterministic candidate context and selects/formulates the next investigation.
"""

from __future__ import annotations
import argparse
import json
import urllib.request
import urllib.error

from reasoner import load_graph, explain

SYSTEM = """You are an investigation planner inside an engineering reasoning loop.
The deterministic reasoner owns verification, project-health states, constraints, and accepted evidence.
You may only choose the next investigation and explain why it is useful.
Never convert a hypothesis into a verified fact.
Prefer investigations that reduce critical project exposure using authoritative evidence.
Return valid JSON only with keys:
node_id, rationale, requested_evidence, proposed_action, do_not_assume.
"""


def ask_ollama(model, candidates, url):
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": json.dumps({
                    "task": "Choose the single best next investigation from these deterministic candidates.",
                    "candidates": candidates
                }, indent=2)
            }
        ]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    content = data["message"]["content"]
    return json.loads(content)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("graph", nargs="?", default="graph.json")
    p.add_argument("--model", default="qwen2.5:3b")
    p.add_argument("--url", default="http://127.0.0.1:11434/api/chat")
    args = p.parse_args()

    graph = load_graph(args.graph)
    report = explain(graph)
    candidates = report["next_investigation_candidates"]

    if not candidates:
        print(json.dumps({"status": "no_unresolved_candidates"}, indent=2))
        return

    try:
        result = ask_ollama(args.model, candidates, args.url)
        print(json.dumps(result, indent=2))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
        top = candidates[0]
        print(json.dumps({
            "node_id": top["node_id"],
            "rationale": "Ollama unavailable or returned invalid JSON; using deterministic highest-exposure candidate.",
            "requested_evidence": top.get("expected_authority", []),
            "proposed_action": "Resolve this field using an authoritative measurement or deterministic derivation, then rerun reasoner.py.",
            "do_not_assume": True,
            "ollama_error": str(e)
        }, indent=2))


if __name__ == "__main__":
    main()
