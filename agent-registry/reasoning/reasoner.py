#!/usr/bin/env python3
"""
Deterministic epistemic graph reasoner.

The LLM is NOT allowed to set VERIFIED/FAILED project-health states.
Those are derived here from graph state, dependencies, and explicit evidence.
"""

from __future__ import annotations
import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, Any

TERMINAL_OK = {"KNOWN", "ASSERTED"}
BAD = {"VIOLATED", "INVALID"}
UNKNOWN = {"NULL", "CONFLICT"}


def load_graph(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def node_map(graph):
    return {n["id"]: n for n in graph["nodes"]}


def dependency_map(graph):
    deps = defaultdict(list)
    reverse = defaultdict(list)
    for r in graph.get("relations", []):
        if r["type"] in {"depends_on", "constrained_by"}:
            deps[r["from"]].append((r["to"], r))
            reverse[r["to"]].append((r["from"], r))
    return deps, reverse


def base_effective_state(node):
    state = node.get("state", "NULL")
    if state in BAD:
        return "FAILED"
    if state == "CONFLICT":
        return "CONFLICT"
    if state == "NULL":
        return "UNRESOLVED"
    if state in TERMINAL_OK:
        return "VERIFIED"
    return "UNRESOLVED"


def compute_effective_states(graph):
    nodes = node_map(graph)
    deps, _ = dependency_map(graph)
    memo = {}
    visiting = set()

    def visit(node_id):
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            memo[node_id] = "CONFLICT"
            return "CONFLICT"

        visiting.add(node_id)
        node = nodes[node_id]
        base = base_effective_state(node)

        if base in {"FAILED", "CONFLICT", "UNRESOLVED"}:
            result = base
        else:
            dep_states = [visit(dep_id) for dep_id, _ in deps.get(node_id, [])]
            if any(s == "FAILED" for s in dep_states):
                result = "FAILED"
            elif any(s == "CONFLICT" for s in dep_states):
                result = "EXPOSED"
            elif any(s in {"UNRESOLVED", "EXPOSED"} for s in dep_states):
                result = "EXPOSED"
            else:
                result = "VERIFIED"

        visiting.remove(node_id)
        memo[node_id] = result
        return result

    for nid in nodes:
        visit(nid)
    return memo


def downstream_closure(start_id, reverse):
    seen = set()
    q = deque([start_id])
    while q:
        cur = q.popleft()
        for nxt, rel in reverse.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return seen


def risk_footprints(graph, states):
    nodes = node_map(graph)
    _, reverse = dependency_map(graph)
    results = []

    for n in graph["nodes"]:
        if n.get("state") not in UNKNOWN:
            continue

        downstream = downstream_closure(n["id"], reverse)
        obligations = []
        gates = []
        exposure = 0.0

        for did in downstream:
            dn = nodes[did]
            if dn.get("kind") in {"obligation", "invariant"}:
                obligations.append(did)
                weight = float(dn.get("criticality", 1))
                if dn.get("acceptance_gate"):
                    weight *= 2.0
                    gates.append(did)
                exposure += weight

        centrality = len(downstream)
        own_criticality = float(n.get("criticality", 1))
        resolution_cost = max(float(n.get("resolution_cost", 1)), 0.1)

        investigation_score = (
            own_criticality
            + exposure
            + 0.5 * centrality
        ) / resolution_cost

        results.append({
            "node_id": n["id"],
            "state": n.get("state"),
            "description": n.get("description"),
            "downstream_count": centrality,
            "affected_obligations": sorted(obligations),
            "acceptance_gates_exposed": sorted(gates),
            "risk_exposure": round(exposure, 2),
            "investigation_score": round(investigation_score, 2),
            "expected_authority": n.get("expected_authority", []),
            "why_it_matters": n.get("metadata", {}).get("why_it_matters")
        })

    return sorted(results, key=lambda x: x["investigation_score"], reverse=True)


def trace_blockers(target_id, graph, states):
    nodes = node_map(graph)
    deps, _ = dependency_map(graph)
    out = []
    seen = set()

    def walk(nid, path):
        if nid in seen and nid != target_id:
            return
        seen.add(nid)
        for dep_id, rel in deps.get(nid, []):
            s = states[dep_id]
            new_path = path + [dep_id]
            if s != "VERIFIED":
                out.append({
                    "node_id": dep_id,
                    "effective_state": s,
                    "description": nodes[dep_id].get("description"),
                    "relation": rel["type"],
                    "path": new_path
                })
                walk(dep_id, new_path)

    walk(target_id, [target_id])

    best = {}
    for item in out:
        nid = item["node_id"]
        if nid not in best or len(item["path"]) < len(best[nid]["path"]):
            best[nid] = item
    return sorted(best.values(), key=lambda x: (len(x["path"]), x["node_id"]))


def project_health(graph, states):
    acceptance_id = graph.get("project", {}).get("acceptance_obligation")
    nodes = node_map(graph)

    obligations = []
    for n in graph["nodes"]:
        if n.get("kind") in {"obligation", "invariant"}:
            obligations.append({
                "node_id": n["id"],
                "kind": n["kind"],
                "effective_state": states[n["id"]],
                "description": n.get("description"),
                "criticality": n.get("criticality", 1),
                "acceptance_gate": bool(n.get("acceptance_gate"))
            })

    if acceptance_id and acceptance_id in nodes:
        overall = states[acceptance_id]
    else:
        if any(o["effective_state"] == "FAILED" for o in obligations):
            overall = "FAILED"
        elif any(o["effective_state"] in {"EXPOSED", "UNRESOLVED", "CONFLICT"} for o in obligations):
            overall = "EXPOSED"
        else:
            overall = "VERIFIED"

    blockers = trace_blockers(acceptance_id, graph, states) if acceptance_id else []

    return {
        "project": graph.get("project", {}),
        "overall_state": overall,
        "acceptance_obligation": acceptance_id,
        "obligations": obligations,
        "acceptance_blockers": blockers,
        "known_violations": [
            n["id"] for n in graph["nodes"] if n.get("state") in BAD
        ]
    }


def explain(graph):
    states = compute_effective_states(graph)
    health = project_health(graph, states)
    footprints = risk_footprints(graph, states)

    return {
        "health": health,
        "effective_states": states,
        "risk_footprints": footprints,
        "next_investigation_candidates": footprints[:5]
    }


def print_human(report):
    h = report["health"]
    print(f'PROJECT: {h["project"].get("name", h["project"].get("id", "unknown"))}')
    print(f'OVERALL STATE: {h["overall_state"]}')
    print()

    if h["known_violations"]:
        print("KNOWN VIOLATIONS:")
        for v in h["known_violations"]:
            print(f"  - {v}")
    else:
        print("KNOWN VIOLATIONS: none")
    print()

    print("ACCEPTANCE BLOCKERS / EXPOSURES:")
    if not h["acceptance_blockers"]:
        print("  none")
    else:
        for b in h["acceptance_blockers"]:
            path = " -> ".join(b["path"])
            print(f'  - {b["node_id"]}: {b["effective_state"]}')
            print(f'    path: {path}')
            print(f'    {b["description"]}')
    print()

    print("UNRESOLVED RISK FOOTPRINTS:")
    for f in report["risk_footprints"]:
        print(f'  - {f["node_id"]}: risk_exposure={f["risk_exposure"]}, '
              f'downstream={f["downstream_count"]}, '
              f'investigation_score={f["investigation_score"]}')
        if f["affected_obligations"]:
            print("    exposes: " + ", ".join(f["affected_obligations"]))
        if f["expected_authority"]:
            print("    evidence wanted: " + ", ".join(f["expected_authority"]))
    print()

    candidates = report["next_investigation_candidates"]
    if candidates:
        top = candidates[0]
        print("DETERMINISTIC NEXT CANDIDATE:")
        print(f'  {top["node_id"]}')
        print(f'  reason: unresolved field exposes {len(top["affected_obligations"])} '
              f'obligation/invariant node(s) and {top["downstream_count"]} downstream node(s).')


def main():
    p = argparse.ArgumentParser()
    p.add_argument("graph", nargs="?", default="graph.json")
    p.add_argument("--json", action="store_true", help="Emit JSON report")
    p.add_argument("--out", help="Write JSON report to a file")
    args = p.parse_args()

    graph = load_graph(args.graph)
    report = explain(graph)

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)


if __name__ == "__main__":
    main()
