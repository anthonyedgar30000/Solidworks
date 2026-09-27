from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping


TRADITION_RAG_RELATIVE = Path("agent-registry/tradition-rag-v1")
SUPPORTED_PLAN_PROFILE = {
    (
        "PLAN-0011",
        "IXOR_FUNCTION_FIRST_BOTTLE_HANDLING_REFERENCE",
    ): (
        "MACHINE_DESIGN",
        "MILLWRIGHT",
        "CONTROLS_AUTOMATION",
        "FLUID_POWER",
        "PACKAGING_MACHINE_BUILDING",
        "MACHINE_SAFETY",
        "RELIABILITY_MAINTENANCE",
    ),
}

DEFAULT_LIMITS = {
    "authoritative": 2,
    "professional": 1,
    "chatter": 1,
    "excerpt_chars": 520,
}

TRADITION_QUERY_LENSES = {
    "MACHINE_DESIGN": (
        "kinematics degrees of freedom contact geometry reaction path "
        "clearance compliance mechanism risk assessment risk reduction design"
    ),
    "MILLWRIGHT": (
        "alignment adjustment installation service access setup wear "
        "maintenance troubleshooting"
    ),
    "CONTROLS_AUTOMATION": (
        "sequence state transition interlock sensor proof index release "
        "fault jam control"
    ),
    "FLUID_POWER": (
        "actuator cylinder pressure force normal load compliance preload "
        "speed valve"
    ),
    "PACKAGING_MACHINE_BUILDING": (
        "label transfer wrap application product flow changeover indexing "
        "entry exit package handling"
    ),
    "MACHINE_SAFETY": (
        "in-running nip pinch crush guarding hazardous energy lockout "
        "emergency stop maintenance access"
    ),
    "RELIABILITY_MAINTENANCE": (
        "equipment reliability work management asset lifecycle wear drift "
        "inspection adjustment failure mode preventive maintenance serviceability"
    ),
}


class TraditionContextError(ValueError):
    def __init__(self, violations: list[str]):
        self.violations = tuple(violations)
        super().__init__("; ".join(self.violations))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require(condition: bool, violation: str) -> None:
    if not condition:
        raise TraditionContextError([violation])


def _repo_tradition_tree(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "rev-parse",
                f"HEAD:{TRADITION_RAG_RELATIVE.as_posix()}",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        raise TraditionContextError([
            f"TRADITION_REPO_TREE_UNAVAILABLE:{type(exc).__name__}"
        ]) from exc

    tree = completed.stdout.strip()
    _require(bool(tree), "TRADITION_REPO_TREE_EMPTY")
    return tree


def _load_rag_module(code_root: Path):
    module_path = code_root / "tradition_rag.py"
    _require(module_path.is_file(), "TRADITION_RAG_MODULE_MISSING")

    spec = importlib.util.spec_from_file_location(
        "cadgrounded_tradition_rag_runtime",
        module_path,
    )
    _require(
        spec is not None and spec.loader is not None,
        "TRADITION_RAG_MODULE_SPEC_INVALID",
    )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bounded_excerpt(value: str, limit: int) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "…"


def _selected_traditions(
    frontier_snapshot: Mapping[str, Any],
) -> tuple[str, ...]:
    key = (
        str(frontier_snapshot.get("current_plan_id") or ""),
        str(frontier_snapshot.get("current_architecture_id") or ""),
    )
    traditions = SUPPORTED_PLAN_PROFILE.get(key)
    _require(
        traditions is not None,
        f"TRADITION_PLAN_PROFILE_UNREGISTERED:{key[0]}:{key[1]}",
    )
    return traditions


def _runtime_binding(
    *,
    repo_root: Path,
    code_root: Path,
    data_root: Path,
    tree_resolver: Callable[[Path], str] | None = None,
) -> dict[str, Any]:
    manifest_path = code_root / "deployment-manifest.json"
    refresh_path = data_root / "last-refresh.json"
    active_chunks_path = data_root / "active_chunks.jsonl"

    _require(manifest_path.is_file(), "TRADITION_DEPLOYMENT_MANIFEST_MISSING")
    _require(refresh_path.is_file(), "TRADITION_LAST_REFRESH_MISSING")
    _require(active_chunks_path.is_file(), "TRADITION_ACTIVE_CHUNKS_MISSING")

    manifest = _read_json(manifest_path)
    refresh = _read_json(refresh_path)

    _require(
        manifest.get("cad_write_authority") == "NONE",
        "TRADITION_RUNTIME_CAD_WRITE_AUTHORITY_NOT_NONE",
    )
    _require(
        manifest.get("mechanical_acceptance_authority") == "NONE",
        "TRADITION_RUNTIME_MECHANICAL_ACCEPTANCE_AUTHORITY_NOT_NONE",
    )
    _require(
        refresh.get("cad_write_authority") == "NONE",
        "TRADITION_REFRESH_CAD_WRITE_AUTHORITY_NOT_NONE",
    )
    _require(
        refresh.get("mechanical_acceptance_authority") == "NONE",
        "TRADITION_REFRESH_MECHANICAL_ACCEPTANCE_AUTHORITY_NOT_NONE",
    )
    _require(
        refresh.get("state") == "COMPLETED",
        f"TRADITION_REFRESH_NOT_COMPLETED:{refresh.get('state')}",
    )

    runtime_tree = str(manifest.get("tradition_rag_tree") or "")
    refresh_tree = str(refresh.get("tradition_rag_tree") or "")
    _require(bool(runtime_tree), "TRADITION_RUNTIME_TREE_MISSING")
    _require(
        refresh_tree == runtime_tree,
        "TRADITION_REFRESH_TREE_MISMATCH",
    )

    resolver = tree_resolver or _repo_tradition_tree
    repo_tree = resolver(repo_root)
    _require(
        repo_tree == runtime_tree,
        "TRADITION_RUNTIME_REPO_TREE_MISMATCH",
    )

    manifest_data_root = str(manifest.get("data_root") or "")
    _require(
        Path(manifest_data_root) == data_root,
        "TRADITION_RUNTIME_DATA_ROOT_MISMATCH",
    )

    return {
        "deployment_id": manifest.get("deployment_id"),
        "source_commit": manifest.get("source_commit"),
        "tradition_rag_tree": runtime_tree,
        "repo_tradition_rag_tree": repo_tree,
        "last_refresh_completed_at_utc": refresh.get("completed_at_utc"),
        "active_chunks_path": str(active_chunks_path),
        "code_update_policy": manifest.get("code_update_policy"),
        "corpus_refresh_policy": manifest.get("corpus_refresh_policy"),
    }


def build_review_query(
    evidence: str,
    frontier_snapshot: Mapping[str, Any],
) -> str:
    # Keep the shared query mechanism-centric. Discipline-specific concerns are
    # added by TRADITION_QUERY_LENSES so safety/maintenance vocabulary does not
    # dominate every tradition through FTS OR matching.
    pieces = [
        "bottle capture driven wrap belt support rollers",
        "closure release maintained contact wrap-axis rotation",
        "label transfer product handling entry exit",
    ]
    return " ".join(" ".join(piece.split()) for piece in pieces if piece)


def load_tradition_context(
    *,
    repo_root: Path,
    code_root: Path,
    data_root: Path,
    evidence: str,
    frontier_snapshot: Mapping[str, Any],
    limits: Mapping[str, int] | None = None,
    tree_resolver: Callable[[Path], str] | None = None,
    retriever: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    runtime = _runtime_binding(
        repo_root=repo_root,
        code_root=code_root,
        data_root=data_root,
        tree_resolver=tree_resolver,
    )
    traditions = _selected_traditions(frontier_snapshot)
    query = build_review_query(evidence, frontier_snapshot)

    bounded = dict(DEFAULT_LIMITS)
    if limits:
        bounded.update({
            key: int(value)
            for key, value in limits.items()
            if key in bounded
        })

    for key in ("authoritative", "professional", "chatter"):
        _require(
            0 <= bounded[key] <= 4,
            f"TRADITION_LIMIT_INVALID:{key}:{bounded[key]}",
        )
    _require(
        120 <= bounded["excerpt_chars"] <= 1200,
        "TRADITION_EXCERPT_LIMIT_INVALID",
    )

    if retriever is None:
        rag_module = _load_rag_module(code_root)
        retriever = rag_module.retrieve

    tradition_rows: list[dict[str, Any]] = []
    total_hits = 0

    for tradition_id in traditions:
        tradition_query = (
            query
            + " "
            + TRADITION_QUERY_LENSES.get(tradition_id, "")
        ).strip()
        candidate_limits = {
            "AUTHORITATIVE": min(8, max(bounded["authoritative"] * 3, bounded["authoritative"])),
            "PROFESSIONAL_PRACTICE": min(6, max(bounded["professional"] * 3, bounded["professional"])),
            "FIELD_CHATTER": min(6, max(bounded["chatter"] * 3, bounded["chatter"])),
        }
        bundle = retriever(
            data_root,
            tradition_id,
            tradition_query,
            candidate_limits["AUTHORITATIVE"],
            candidate_limits["PROFESSIONAL_PRACTICE"],
            candidate_limits["FIELD_CHATTER"],
        )
        authority_boundary = bundle.get("authority_boundary") or {}
        _require(
            authority_boundary.get("retrieval_is_engineering_evidence") is False,
            f"TRADITION_RETRIEVAL_AUTHORITY_INVALID:{tradition_id}",
        )
        _require(
            authority_boundary.get("mechanical_acceptance_granted") is False,
            f"TRADITION_RETRIEVAL_ACCEPTANCE_INVALID:{tradition_id}",
        )
        _require(
            authority_boundary.get("cad_write_authority") == "NONE",
            f"TRADITION_RETRIEVAL_CAD_WRITE_INVALID:{tradition_id}",
        )

        hits_out: list[dict[str, Any]] = []
        hits = bundle.get("hits") or {}
        output_limits = {
            "AUTHORITATIVE": bounded["authoritative"],
            "PROFESSIONAL_PRACTICE": bounded["professional"],
            "FIELD_CHATTER": bounded["chatter"],
        }
        for lane in (
            "AUTHORITATIVE",
            "PROFESSIONAL_PRACTICE",
            "FIELD_CHATTER",
        ):
            seen_sources: set[str] = set()
            emitted = 0
            for hit in hits.get(lane) or []:
                score = float(hit.get("retrieval_score") or 0.0)
                source_id = str(hit.get("source_id") or "")
                if score <= 0.0 or not source_id:
                    continue
                if source_id in seen_sources:
                    continue
                if emitted >= output_limits[lane]:
                    break
                seen_sources.add(source_id)
                emitted += 1
                hits_out.append({
                    "chunk_id": hit.get("chunk_id"),
                    "source_id": source_id,
                    "source_lane": lane,
                    "permitted_effect": hit.get("permitted_effect"),
                    "authority_class": hit.get("authority_class"),
                    "chunk_kind": hit.get("chunk_kind"),
                    "source_record_id": hit.get("source_record_id"),
                    "observed_at_utc": hit.get("observed_at_utc"),
                    "source_uri": hit.get("source_uri"),
                    "retrieval_score": score,
                    "excerpt": _bounded_excerpt(
                        hit.get("body") or "",
                        bounded["excerpt_chars"],
                    ),
                })

        total_hits += len(hits_out)
        tradition_rows.append({
            "tradition_id": tradition_id,
            "query_sha256": _sha256_text(tradition_query),
            "hits": hits_out,
        })

    return {
        "schema_version": 1,
        "context_id": "CADGROUNDED.TRADITION_CONTEXT.V1",
        "state": "BOUND_UNADMITTED_ADVISORY",
        "selection_basis": "PLAN0011_BOTTLE_HANDLING_PROFILE_V1",
        "plan_id": frontier_snapshot.get("current_plan_id"),
        "architecture_id": frontier_snapshot.get(
            "current_architecture_id"
        ),
        "query_sha256": _sha256_text(query),
        "runtime": runtime,
        "selected_traditions": list(traditions),
        "traditions": tradition_rows,
        "total_hits": total_hits,
        "engineering_evidence_admissibility": "NONE",
        "frontier_mutation_authority": "NONE",
        "solidworks_geometry_authority": "NONE",
        "cad_write_authority": "NONE",
        "mechanical_acceptance_authority": "NONE",
        "evidence_verification_authority": "NONE",
    }


def render_tradition_context(
    snapshot: Mapping[str, Any],
) -> str:
    lines = [
        "TRADITION RAG ADVISORY CONTEXT:",
        f"context_id: {snapshot.get('context_id')}",
        f"state: {snapshot.get('state')}",
        f"selection_basis: {snapshot.get('selection_basis')}",
        f"plan_id: {snapshot.get('plan_id')}",
        f"architecture_id: {snapshot.get('architecture_id')}",
        f"tradition_rag_tree: {(snapshot.get('runtime') or {}).get('tradition_rag_tree')}",
        "",
        "TRADITION CONTEXT AUTHORITY CONTRACT:",
        "- This material is UNADMITTED advisory context, not engineering evidence.",
        "- Do NOT copy Tradition-RAG text into claims_used or anchor_claims unless the exact same claim independently appears in SUPPLIED EVIDENCE and in the deterministic grounding catalog.",
        "- AUTHORITATIVE lane material is source-scoped reference only; it does not establish project-specific geometry, dimensions, mechanism ownership, force, motion, or acceptance.",
        "- PROFESSIONAL_PRACTICE may suggest heuristics and tests only.",
        "- FIELD_CHATTER has a hard HYPOTHESIS_ONLY effect ceiling.",
        "- Tradition context may suggest mechanism classes, hazards, failure modes, service concerns, or discriminating tests.",
        "- Tradition context cannot mutate the investigation frontier, verify evidence, authorize CAD writes, or grant mechanical acceptance.",
        "",
    ]

    for tradition in snapshot.get("traditions") or []:
        lines.append(f"## {tradition.get('tradition_id')}")
        hits = tradition.get("hits") or []
        if not hits:
            lines.append("(no positive-score retrieved context)")
            lines.append("")
            continue

        for hit in hits:
            lines.extend([
                (
                    f"[{hit.get('chunk_id')}] "
                    f"lane={hit.get('source_lane')} "
                    f"effect={hit.get('permitted_effect')} "
                    f"source={hit.get('source_id')}"
                ),
                str(hit.get("excerpt") or ""),
                f"source_uri: {hit.get('source_uri')}",
                "",
            ])

    return "\n".join(lines)


def tradition_runtime_status(
    *,
    repo_root: Path,
    code_root: Path,
    data_root: Path,
    tree_resolver: Callable[[Path], str] | None = None,
) -> dict[str, Any]:
    try:
        runtime = _runtime_binding(
            repo_root=repo_root,
            code_root=code_root,
            data_root=data_root,
            tree_resolver=tree_resolver,
        )
        return {
            "status": "bound",
            "runtime": runtime,
            "engineering_evidence_admissibility": "NONE",
            "cad_write_authority": "NONE",
            "mechanical_acceptance_authority": "NONE",
        }
    except TraditionContextError as exc:
        return {
            "status": "unavailable",
            "violations": list(exc.violations),
            "engineering_evidence_admissibility": "NONE",
            "cad_write_authority": "NONE",
            "mechanical_acceptance_authority": "NONE",
        }
