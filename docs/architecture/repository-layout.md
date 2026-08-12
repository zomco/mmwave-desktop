# Repository layout

[中文](repository-layout_CN.md)

```text
tracecue/
├─ desktop/                  On-demand local Web application
├─ gateway/                  Always-on source acquisition
├─ engine/                   Vendor-neutral interval core
├─ integrations/hikvision/  Hikvision adapter boundary
├─ contracts/timeline/v1/   Machine-readable public contract
├─ docs/                     Product and engineering source of truth
├─ scripts/ci/               Dependency-light repository checks
└─ .github/                  Collaboration, CI and release automation
```

## Dependency direction

```text
desktop ───────→ engine
gateway ───────→ engine
desktop ───────→ integrations/hikvision

engine ─X→ desktop, gateway, Hikvision, HA or FFmpeg
gateway ─X→ desktop UI or NVR media
```

Cross-module data crosses typed interfaces or versioned contracts. A module must not read another module's SQLite tables directly.

## Planned module-internal structure

Executable language/framework choices remain provisional until the first implementation ADR. The current recommendation is `desktop/backend/` with Python/FastAPI, `desktop/frontend/` with React/TypeScript, a dependency-light Python engine, and FFmpeg as a subprocess. Create these directories when code lands; do not create empty architecture theatre.

## Documentation ownership

- Product claims: `docs/product/`.
- Runtime decisions: `docs/architecture/` and ADRs.
- Public data/API contracts: `docs/specifications/` plus `contracts/`.
- Repeatable developer/operations procedures: `docs/development/` and `docs/operations/`.
- AI context that would otherwise be lost between sessions: `AGENTS*` and `docs/ai/`.
