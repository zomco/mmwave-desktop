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

Each module README/manifest is authoritative. Install the exact shared development environment first:

```powershell
python -m pip install -r requirements-dev.lock.txt
python -m pip install --no-build-isolation --no-deps -e ./engine -e ./integrations/hikvision -e ./gateway -e ./desktop/backend
```

CI uses these conventional commands:

```text
engine:  python -m pytest engine/tests
Hikvision: python -m pytest integrations/hikvision/tests
gateway: python -m pytest gateway/tests
desktop backend: python -m pytest desktop/backend/tests
desktop frontend: npm ci --prefix desktop/frontend && npm test --prefix desktop/frontend && npm run build --prefix desktop/frontend
```

`packaging/windows/build.ps1 -Mode Verify` runs all software checks on Windows. Each invocation uses and then removes a unique repository-local verification virtual environment, so a running test build cannot lock the next verifier's console entry point. `-Mode Release` is intentionally blocked unless licensing, FFmpeg hashes/notices and signing inputs are explicitly satisfied.

The Windows verification script gives pytest a unique base directory under repository-local `build/`. This avoids `WinError 5` when `%TEMP%\pytest-of-<user>` was created by an elevated process, IDE sandbox or another Windows identity. For a direct local pytest invocation, use the same pattern:

```powershell
$pytestTemp = Join-Path (Resolve-Path ./build) ("pytest-manual-" + [guid]::NewGuid().ToString("N"))
python -m pytest engine/tests integrations/hikvision/tests gateway/tests desktop/backend/tests --basetemp $pytestTemp
```

Do not add placeholder tests that only assert framework startup. A test should protect a product invariant, protocol observation or failure mode.

## Fixture policy

- Redact credentials, serials, public IPs, customer names and image URLs.
- Preserve namespaces, optional-field absence, malformed samples and pagination boundaries.
- Record model/firmware and collection date in fixture metadata.
- Customer footage is prohibited; media fixtures are synthetic or explicitly cleared.

## Hardware claims

CI without hardware validates parsers and contracts, not real compatibility. A support claim requires a repeatable hardware scenario and recorded expected outcome.
