"""Score live agent runs against the gold mapping (never run in CI).

It drives the real API (local or hosted): log in as the operator, create a fresh project, start
an agent run, poll until it finishes, then score the resulting DRAFT plan against
backend/app/data/gold_mapping.json and dry-run it for the counts.

Scores per run:
- mapping_accuracy: target columns whose source fields match the gold mapping
- transform_correctness: target columns whose chain contains the gold's required transforms
- unmapped_sources: gold "drop" fields that the plan lists as unmapped (and does not map)
- question_recall: expected clarification topics covered by the plan's questions

Usage (from the repo root):
    backend\\.venv\\Scripts\\python.exe scripts\\eval_agent.py --base-url http://localhost:8000 \\
        --runs 3 [--dataset baseline_60] [--out eval.json]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

GOLD = json.loads((Path(__file__).resolve().parent.parent / "backend" / "app" / "data"
                   / "gold_mapping.json").read_text(encoding="utf-8"))
TERMINAL = {"SUCCEEDED", "FAILED"}


def score(plan: dict[str, Any]) -> dict[str, float]:
    by_target = {m["target_field"]: m for m in plan.get("mappings", [])}
    gold = GOLD["mappings"]
    sources_ok = transforms_ok = 0
    for target, expected in gold.items():
        m = by_target.get(target)
        if m is None:
            continue
        if sorted(m.get("source_fields", [])) == sorted(expected["source_fields"]):
            sources_ok += 1
            names = {t["name"] for t in m.get("transforms", [])}
            if set(expected["required_transforms"]) <= names:
                transforms_ok += 1
    mapped = {s for m in plan.get("mappings", []) for s in m.get("source_fields", [])}
    declared = {u["field"] for u in plan.get("unmapped_source_fields", [])}
    dropped_ok = sum(1 for f in GOLD["unmapped_source_fields"] if f in declared and f not in mapped)
    questions = plan.get("clarification_questions", [])
    covered = 0
    for topic in GOLD["expected_questions"]:
        for q in questions:
            text = (q.get("question", "") + " " + " ".join(q.get("options", []))).lower()
            if (set(q.get("related_fields", [])) & set(topic["related_fields"])
                    or any(k in text for k in topic["keywords"])):
                covered += 1
                break
    n = len(gold)
    return {
        "mapping_accuracy": round(sources_ok / n, 3),
        "transform_correctness": round(transforms_ok / n, 3),
        "unmapped_sources": round(dropped_ok / len(GOLD["unmapped_source_fields"]), 3),
        "question_recall": round(covered / len(GOLD["expected_questions"]), 3),
    }


def _check(res: httpx.Response, expected: int) -> dict[str, Any]:
    if res.status_code != expected:
        raise SystemExit(f"{res.request.method} {res.request.url} -> {res.status_code}: "
                         f"{res.text[:500]}")
    return res.json()


def one_run(http: httpx.Client, headers: dict[str, str], dataset: str, timeout_s: float,
            index: int) -> dict[str, Any]:
    project = _check(http.post("/api/projects", headers=headers,
                               json={"name": f"eval-{index}-{int(time.time())}",
                                     "dataset_key": dataset}), 201)
    started = time.perf_counter()
    run = _check(http.post(f"/api/projects/{project['id']}/agent-runs", headers=headers), 202)
    while run["status"] not in TERMINAL:
        if time.perf_counter() - started > timeout_s:
            raise SystemExit(f"agent run {run['id']} did not finish in {timeout_s} s")
        time.sleep(2)
        run = _check(http.get(f"/api/agent-runs/{run['id']}", headers=headers), 200)
    wall_s = round(time.perf_counter() - started, 1)
    llm_steps = [s for s in run["trace"] if s["kind"] == "llm_call"]
    out: dict[str, Any] = {
        "project_id": project["id"], "agent_run_id": run["id"], "status": run["status"],
        "error_code": run["error_code"], "engine": run["engine"], "mode": run["mode"],
        "fell_back": run["fell_back"], "steps": run["steps"], "llm_calls": len(llm_steps),
        "llm_ms": [s["latency_ms"] for s in llm_steps], "tokens_in": run["tokens_in"],
        "tokens_out": run["tokens_out"], "server_latency_ms": run["latency_ms"],
        "wall_s": wall_s,
    }
    if run["status"] == "SUCCEEDED":
        version = _check(http.get(f"/api/plan-versions/{run['result_version_id']}",
                                  headers=headers), 200)
        out.update({"version_id": version["id"], "version_status": version["status"],
                    "author_type": version["author_type"],
                    "questions": len(version["plan"]["clarification_questions"])})
        out["scores"] = score(version["plan"])
        dry = _check(http.post(f"/api/plan-versions/{version['id']}/dry-runs", headers=headers),
                     201)
        out["dry_run"] = dry["counts"]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--dataset", default="baseline_60")
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--out", help="write the results as JSON to this file")
    args = parser.parse_args()
    password = os.environ.get("DEMO_PASSWORD", "migrateiq-demo")
    with httpx.Client(base_url=args.base_url, timeout=60) as http:
        token = _check(http.post("/api/auth/login",
                                 json={"username": "operator", "password": password}),
                       200)["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        results = []
        for i in range(1, args.runs + 1):
            result = one_run(http, headers, args.dataset, args.timeout, i)
            print(json.dumps(result), flush=True)
            results.append(result)
    ok = [r for r in results if r["status"] == "SUCCEEDED"]
    summary: dict[str, Any] = {"runs": len(results), "succeeded": len(ok),
                               "engines": sorted({r["engine"] for r in results if r["engine"]})}
    if ok:
        for key in ("mapping_accuracy", "transform_correctness", "unmapped_sources",
                    "question_recall"):
            summary[key] = round(statistics.mean(r["scores"][key] for r in ok), 3)
        summary["median_wall_s"] = statistics.median(r["wall_s"] for r in ok)
    print(json.dumps({"summary": summary}))
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "runs": results}, indent=2),
                                  encoding="utf-8")
    return 0 if len(ok) == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
