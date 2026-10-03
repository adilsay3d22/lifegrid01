# 0003: Forecasting, optimizer and simulator choices

Date: 2026-10-03

## Forecasting (13.1)
- Models: seasonal naive (baseline), Poisson (sparse series only), exponential smoothing (statsmodels, additive weekly seasonality). Gradient boosting is **deferred**: FR-FC-03 asks for the baseline plus at least one better model, and ETS beats the baseline on the `normal` scenario out of sample (`test_phase4_exit_chosen_models_beat_seasonal_baseline_on_normal_scenario`). Add GBM if a scenario shows ETS falling short.
- Backtest: rolling origin over the last 28 days, re-fitting every 7 days (4 origins) rather than daily — same intent, about 7× cheaper.
- ETS needs 8 weeks of history plus the 28-day backtest window; series with less use the baseline or Poisson. The demo seed has 56 days, so ETS appears after about 4 more weeks of usage.
- Plasma is forecast by ABO group only and stored under `rh = pos` (plasma rules ignore Rh).
- The simulator uses `ets_fast` (fixed smoothing constants) and refits weekly, for speed.

## Optimizer (13.2)
- One MILP per component (OR-Tools + SCIP). Transfers `x` are integers and lanes `z` binary; usage, waste and unmet (`y, w, u`) are continuous — an allocation of fixed integer stock.
- **Integer demand.** Forecast demand is fractional (0.37/day). Left as is, the LP spreads slivers of one unit across sites, the bound is weak and SCIP hits the 30 s limit. Demand is made whole-unit by rounding the cumulative sum over the horizon (totals kept). With that, the relaxation is tight.
- **Exact shortcut.** Solve with continuous `x` first; if the optimum already has integral `x` (the usual case) it is optimal for the integer model. Otherwise re-solve with integer `x` in the remaining time.
- Relative MIP gap 1e-4. A 1 % gap let useless moves through, because transport cost is tiny next to shortage penalties.
- Expiry buckets: one per day inside the horizon, then "beyond, cannot travel" and "beyond, can travel" (`e ≥ minLife`). This keeps plasma (30-day minimum) from creating 30 buckets.
- Candidate lanes per site are limited to the 12 nearest (NFR-08: 100 sites).
- Per-line benefit: shortage avoided at the destination first, then expiry avoided at the source. Lines with neither are labelled `rebalance` (relays caused by the 3-lanes-per-site limit).

## Finding: k = 0.5 over-hedges
`D = point + k(high − point)` with the spec default k = 0.5 makes policy C move platelets toward phantom upper-band demand on sparse series; they then expire. Over 30 seeds on `normal`, C with k = 0 beats C with k = 0.5 on both expiry and shortage (see docs/results/report.md). **k stays 0.5 (spec default) and is configurable** (`optimizer_demand_k`); the evidence suggests setting it to 0 or applying k only to the horizon total. Needs a product decision.

## Simulator (section 14)
- Supply: collections arrive at blood banks on delivery days (3/week, fill rate, `SUPPLY_FACTOR` 1.08); hospitals reorder up to a cover level (red cells 7 days, platelets 3, plasma 14) from the nearest bank. Policy A stops there; B adds the fallback heuristic; C adds forecasts and the optimizer. All policies run as A during warm-up so they start from the same state.
- Plasma Rh is collapsed to `pos` in the simulator.
- Solver wall time is reported under `timing`, outside `metrics`, so repeated runs compare byte for byte (NFR-15).
- No charts yet in `make sim-report` (matplotlib is not a listed dependency); the report is Markdown tables and a CSV.
