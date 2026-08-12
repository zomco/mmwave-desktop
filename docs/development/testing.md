# Testing strategy

[中文](testing_CN.md)

## Test pyramid

1. **Repository contract:** bilingual pairs, local links, required files and JSON validity.
2. **Engine unit/property tests:** interval invariants, timezones, deterministic merge and quality behavior.
3. **Adapter contract tests:** redacted Hikvision XML/JSON fixtures, pagination and error mapping.
4. **Media integration tests:** generated local RTSP/media samples covering H.264, H.265, audio and gaps.
5. **Hardware compatibility tests:** explicit NVR model/firmware matrix.
6. **Windows end-to-end tests:** install, launch, add test NVR, search, export, uninstall/retain data.

## Commands

Always:

```powershell
python scripts/ci/verify_repo.py
```

Once manifests land, each module README/manifest becomes authoritative. CI expects conventional commands:

```text
engine:  python -m pytest engine/tests
gateway: python -m pytest gateway/tests
desktop backend: python -m pytest desktop/backend/tests
desktop frontend: npm ci --prefix desktop/frontend && npm test --prefix desktop/frontend && npm run build --prefix desktop/frontend
```

Do not add placeholder tests that only assert framework startup. A test should protect a product invariant, protocol observation or failure mode.

## Fixture policy

- Redact credentials, serials, public IPs, customer names and image URLs.
- Preserve namespaces, optional-field absence, malformed samples and pagination boundaries.
- Record model/firmware and collection date in fixture metadata.
- Customer footage is prohibited; media fixtures are synthetic or explicitly cleared.

## Hardware claims

CI without hardware validates parsers and contracts, not real compatibility. A support claim requires a repeatable hardware scenario and recorded expected outcome.
