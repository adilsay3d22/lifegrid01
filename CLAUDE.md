# LifeGrid: build rules
Spec: docs/spec.md (source of truth). Build phases in order (section 18).
- Finish a phase only when its exit criteria and the definition of done (section 17) pass.
- Synthetic data only. Never commit secrets or real personal data.
- Rules and thresholds live in settings and rule tables, not in code.
- Every state change: lock row, validate transition, write movement + audit event, one commit.
- Check role and site scope on every endpoint; deny by default.
- Reference requirement IDs in commits and test names.
- If the spec is unclear, pick the simplest option and add a note in docs/decisions/.
Commands: make up | make migrate | make seed | make test | make lint | make sim
Without Docker: see README "Run without Docker".
