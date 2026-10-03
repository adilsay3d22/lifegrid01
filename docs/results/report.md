# LifeGrid simulation results

Synthetic data only. Mean and 95% interval (1.96 × standard error) across seeds, after warm-up days.
Policies: A independent reorder levels · B rule-based sharing · C forecasts + optimizer (k = 0.5, spec default) · C@k=0 point forecasts (ablation).

## normal (30 seeds)

| metric | A | B | C | C@k=0 |
|---|---|---|---|---|
| expired_units | 506.2 ± 25.0 | 324.9 ± 13.8 | 422.3 ± 17.8 | 328.8 ± 13.2 |
| expired_share | 0.031 ± 0.002 | 0.020 ± 0.002 | 0.026 ± 0.002 | 0.020 ± 0.001 |
| unmet_units | 867.3 ± 83.7 | 580.6 ± 56.5 | 668.3 ± 58.4 | 577.6 ± 57.9 |
| shortage_events | 618.4 ± 45.8 | 471.6 ± 37.1 | 520.0 ± 32.5 | 461.4 ± 36.8 |
| unmet_units_rh_neg | 155.0 ± 16.9 | 136.8 ± 18.9 | 143.4 ± 17.3 | 133.7 ± 17.1 |
| shortage_events_rh_neg | 138.0 ± 14.0 | 124.6 ± 16.1 | 130.2 ± 14.2 | 120.9 ± 14.3 |
| avg_age_at_issue_days | 18.2 ± 0.4 | 17.7 ± 0.5 | 17.8 ± 0.5 | 17.7 ± 0.5 |
| transfers | 0.0 ± 0.0 | 1,411.6 ± 149.3 | 2,227.0 ± 147.3 | 1,445.5 ± 141.4 |
| transfer_units | 0.0 ± 0.0 | 1,885.2 ± 303.1 | 3,953.4 ± 392.6 | 2,188.1 ± 345.3 |
| unit_km | 0.0 ± 0.0 | 40,535.6 ± 6,619.2 | 75,069.6 ± 8,670.6 | 44,055.5 ± 7,510.3 |
| lanes_used | 0.0 ± 0.0 | 977.6 ± 79.7 | 1,198.3 ± 67.6 | 792.2 ± 59.6 |
| fallback_count | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.8 ± 0.4 | 0.1 ± 0.1 |

Mean solver seconds per run: A 0.0, B 0.0, C 386.4, C@k=0 135.8

