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

- Pin version, source URL and SHA-256.
- Record `ffmpeg -version` and `-buildconf` in release provenance.
- Prefer a verifiable LGPL build and ship required license/source-offer notices.
- Do not use `nonfree`; review any GPL-enabled build against the resolved product license.
- Distribute `ffprobe` with `ffmpeg`.
- Treat codec patent/licensing questions separately from LGPL/GPL compliance.

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
- `release/manifest.json` currently has `release_ready=false`. It must remain false until ADR-0004 is resolved, an LGPL-compatible FFmpeg build and hashes/notices are recorded, and signing credentials are approved.
