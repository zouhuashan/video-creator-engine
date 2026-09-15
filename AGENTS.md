# VideoCreator Engine instructions

- `VIDEO-CREATOR-TASK.md` is the single source of truth for scope and execution order.
- Work only on the current `NEXT` task. Do not implement later phases early.
- Keep external services behind replaceable provider/adapter interfaces.
- Never commit credentials, upload private media without authorization, or publish automatically. Final publishing requires human confirmation.
- Prefer the codebase knowledge graph tools for code discovery when available; fall back to `rg` for text, config, and when graph tools are unavailable.
- Run `scripts/check-env.sh` before environment-dependent work.
