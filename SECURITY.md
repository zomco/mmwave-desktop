# Security policy

[中文](SECURITY_CN.md)

## Reporting

Do not disclose a vulnerability in a public issue. Use GitHub private vulnerability reporting when enabled, or contact the repository owner through the private address listed on the GitHub profile. Include affected version, reproduction steps, impact and suggested mitigation if known.

## Security boundaries

- TraceCue defaults to loopback-only access.
- LAN exposure is out of MVP scope and must add authentication, CSRF protection, origin checks and an explicit firewall/install flow.
- NVR credentials belong in Windows Credential Manager or a DPAPI-protected store, never plaintext SQLite.
- Logs and support bundles must redact authorization headers, passwords, private customer data and credential-bearing URLs.
- Imported timeline documents and NVR XML/JSON are untrusted input.
- FFmpeg and other subprocesses use fixed executables and argument arrays without shell expansion.
- Clip downloads enforce ownership/path checks and HTTP Range bounds.

## Supported versions

No production version has been released. Security support begins with the first tagged beta. Until then, report issues against `main`.
