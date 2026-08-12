# Windows and FFmpeg packaging

[中文](windows-packaging_CN.md)

## Packaging shape

Prefer a per-user one-folder installer for the first release. It starts faster, avoids extracting FFmpeg/Python on every run and is easier to inspect than one-file packaging.

Recommended locations:

```text
Program:  %LocalAppData%\Programs\TraceCue
Data:     %LocalAppData%\TraceCue
Clips:    %USERPROFILE%\Videos\TraceCue
```

The installer should not require elevation, enable startup, open a firewall port or delete user data by default. Uninstall offers a separate explicit data-removal choice.

## Process behavior

- Single-instance lock.
- Tray actions: open, status and exit.
- Stable preferred port with safe fallback.
- Loopback bind by default.
- Graceful job cancellation and interrupted-job recovery.
- Support bundle with redaction preview.

## Code signing

Sign the application launcher, installer, uninstaller and future updater with a consistent trusted identity. Store certificate material only in protected CI secrets/HSM-backed services. Early signed releases can still receive SmartScreen warnings; signing establishes publisher identity but does not guarantee instant reputation.

## FFmpeg distribution

- Pin version, immutable release URL, source commits and SHA-256.
- Record `ffmpeg -version` and `-buildconf` in release provenance.
- Prefer a verifiable LGPL build and ship required license/source-offer notices.
- Do not use `nonfree`; review any GPL-enabled build against the resolved product license.
- Distribute `ffprobe` with `ffmpeg`.
- Treat codec patent/licensing questions separately from LGPL/GPL compliance.

### Pinned 0.1.0 input

TraceCue pins BtbN's monthly-retained Windows x64 static LGPL build `n8.1.2-34-g9b6c8969e0-20260731` from release tag `autobuild-2026-07-31-14-10`. FFmpeg's download page lists BtbN as a Windows binary provider. The archive, executables, FFmpeg source commit `9b6c8969e05b4f0b29f0f85cd501be6b3e582e6b`, BtbN build-script commit `a99e8230eae00d1cee38f23076a7a1f55cd984e2`, license texts and all SHA-256 values are recorded in `release/manifest.json`.

The build enables `--enable-version3` and `--enable-libopenh264`, while `--enable-gpl`, `--enable-nonfree`, `libx264` and `libx265` are absent/disabled. TraceCue therefore uses `libopenh264` for the compatibility transcode fallback. Codec patent review remains a separate product-release decision.

Fetch and verify packaging inputs without committing binaries:

```powershell
./packaging/windows/fetch-ffmpeg.ps1 -IncludeSourceSnapshots
```

The script verifies the archive and per-executable hashes, version/build configuration, required LGPL/GPL texts and optional source snapshots. It writes binaries to the ignored `packaging/windows/tools/` directory and source snapshots to ignored `release/output/source/`.

## Media policy

- RTSP TCP by default.
- Fixed executable path and argument arrays; no shell interpolation.
- Connection, no-data and total-job timeouts.
- Start with one concurrent media job per NVR.
- H.264 stream copy first; H.265/video and incompatible audio use an explicit compatibility profile.
- Use MP4 `faststart`, `.partial` output and atomic completion.
- Check free space, enforce clip quota and report partial recording coverage.

## Release contents

Every binary release includes application version, database migration version, FFmpeg provenance, third-party notices, supported compatibility matrix, checksum file and signed artifact metadata.

## Implemented automation and current gate

- `packaging/windows/build.ps1 -Mode Verify` runs repository/security, Python module and frontend checks.
- `-Mode Release` builds a PyInstaller one-folder application, signs it, creates a per-user Inno Setup installer, generates a CycloneDX SBOM and checksums, and refuses to proceed without explicit inputs.
- `packaging/windows/smoke.ps1` launches the packaged process hidden, verifies loopback status and SQLite initialization, then removes its isolated temporary data.
- ADR-0004 and FFmpeg selection are resolved. `release/manifest.json` remains `release_ready=false` until the complete corresponding-source/notices set for all statically incorporated dependencies is mirrored and reviewed, signing credentials are approved, and signed-installer/hardware tests pass.
