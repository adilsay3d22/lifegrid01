"""Experiment harness (FR-SIM-02): run policies over scenarios and seeds, write JSON per run, a CSV and a report."""

import csv
import json
import math
import os
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from simulation.engine import K_UPPER, run
from simulation.generator import generate
from simulation.scenario import load

RESULTS = Path(__file__).resolve().parents[2] / "docs" / "results"


def label(policy: str, k: float) -> str:
    return policy if policy != "C" or k == K_UPPER else f"C@k={k:g}"


def one(args: tuple[str, str, int, float]) -> dict[str, object]:
    scenario, policy, seed, k = args
    sc = load(scenario)
    r = run(generate(sc, seed), policy, demand_k=k)
    return {"scenario": scenario, "policy": label(policy, k), "seed": seed, "config": sc.model_dump(), "metrics": r.metrics, "timing": r.timing}


def experiment(scenarios: list[str], policies: list[str], seeds: int, workers: int | None = None, ablate_k: bool = False) -> list[dict[str, object]]:
    jobs = [(s, p, seed, K_UPPER) for s in scenarios for p in policies for seed in range(1, seeds + 1)]
    if ablate_k and "C" in policies:
        jobs += [(s, "C", seed, 0.0) for s in scenarios for seed in range(1, seeds + 1)]
    out_dir = RESULTS / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    with ProcessPoolExecutor(max_workers=workers or max(1, (os.cpu_count() or 2) - 1)) as ex:
        for res in ex.map(one, jobs):
            name = f"{res['scenario']}_{res['policy']}_{res['seed']:02d}.json".replace("@", "_").replace("=", "")  # type: ignore[str-format]
            (out_dir / name).write_text(json.dumps(res, indent=1, sort_keys=True), encoding="utf-8")
            rows.append(res)
            print(f"done {res['scenario']} {res['policy']} seed {res['seed']}", flush=True)
    return rows


KEY_METRICS = ["expired_units", "expired_share", "unmet_units", "shortage_events", "unmet_units_rh_neg", "shortage_events_rh_neg",
               "avg_age_at_issue_days", "transfers", "transfer_units", "unit_km", "lanes_used", "fallback_count"]


def _ci(xs: list[float]) -> tuple[float, float]:
    m = statistics.fmean(xs)
    half = 1.96 * statistics.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else 0.0
    return m, half


def report() -> Path:
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((RESULTS / "runs").glob("*.json"))]
    if not runs:
        raise SystemExit("no runs in docs/results/runs; run `make sim` first")
    metric_keys = sorted({k for r in runs for k in r["metrics"]})
    with (RESULTS / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "policy", "seed", *metric_keys, "solver_seconds"])
        for r in runs:
            w.writerow([r["scenario"], r["policy"], r["seed"], *(r["metrics"].get(k, 0) for k in metric_keys), r["timing"]["solver_seconds"]])
    lines = ["# LifeGrid simulation results", "",
             "Synthetic data only. Mean and 95% interval (1.96 × standard error) across seeds, after warm-up days.",
             "Policies: A independent reorder levels · B rule-based sharing · C forecasts + optimizer (k = 0.5, spec default)"
             " · C@k=0 point forecasts (ablation).", ""]
    for sc in sorted({r["scenario"] for r in runs}):
        group = [r for r in runs if r["scenario"] == sc]
        pols = sorted({r["policy"] for r in group})
        n = len({r["seed"] for r in group})
        lines += [f"## {sc} ({n} seeds)", "", "| metric | " + " | ".join(pols) + " |", "|---|" + "---|" * len(pols)]
        for k in KEY_METRICS:
            cells = []
            for p in pols:
                m, h = _ci([float(r["metrics"].get(k, 0)) for r in group if r["policy"] == p])
                cells.append(f"{m:,.3f} ± {h:,.3f}" if k == "expired_share" else f"{m:,.1f} ± {h:,.1f}")
            lines.append(f"| {k} | " + " | ".join(cells) + " |")
        solver = {p: statistics.fmean(r["timing"]["solver_seconds"] for r in group if r["policy"] == p) for p in pols}
        lines += ["", "Mean solver seconds per run: " + ", ".join(f"{p} {v:.1f}" for p, v in solver.items()), ""]
    out = RESULTS / "report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return out
