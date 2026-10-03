"""CLI (spec section 14).

python -m simulation run    --scenario normal --policies A,B,C --seeds 30 [--ablate-k]
python -m simulation report
python -m simulation seed   --scenario normal --seed 42 [--create-schema]
"""

import argparse


def main() -> None:
    ap = argparse.ArgumentParser(prog="simulation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--scenario", default="normal", help="comma-separated scenario names")
    r.add_argument("--policies", default="A,B,C")
    r.add_argument("--seeds", type=int, default=30)
    r.add_argument("--workers", type=int)
    r.add_argument("--ablate-k", action="store_true", help="also run policy C with point forecasts (k=0)")
    sub.add_parser("report")
    s = sub.add_parser("seed")
    s.add_argument("--scenario", default="normal")
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--create-schema", action="store_true", help="create tables directly (SQLite dev); otherwise run migrations first")
    a = ap.parse_args()

    if a.cmd == "run":
        from simulation.runner import experiment, report

        experiment(a.scenario.split(","), a.policies.split(","), a.seeds, a.workers, a.ablate_k)
        print(report())
    elif a.cmd == "report":
        from simulation.runner import report

        print(report())
    else:
        from simulation.seed import seed_demo

        seed_demo(a.scenario, a.seed, a.create_schema)


if __name__ == "__main__":
    main()
