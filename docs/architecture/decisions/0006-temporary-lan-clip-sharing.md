# ADR-0006: Temporary token-scoped LAN clip sharing

[中文](0006-temporary-lan-clip-sharing_CN.md)

- Status: Accepted
- Date: 2026-08-14

## Context

ADR-0002 keeps the TraceCue SPA and API on loopback. A user who has already reviewed a generated clip also needs a low-friction way to open, save and share that clip on a phone connected to the same private LAN. Binding the main API to the LAN would expose device management and NVR-adjacent control surfaces and is disproportionate to this task.

## Decision

Keep the main service on `127.0.0.1`. Only after an explicit “phone QR code” action, start a separate ephemeral HTTP listener on the private interface and issue a 256-bit random capability URL for exactly one verified local MP4. The token is held only in memory, expires after 15 minutes and authorizes only `GET`/`HEAD` access to a minimal playback page and bounded HTTP Range delivery for that clip. The share listener exposes no TraceCue API, database, NVR address, credentials or filesystem path, emits no token-bearing access log and sends restrictive browser security headers.

Generate the QR code locally in the SPA. Do not send the URL to a cloud QR service. The installer still does not open a firewall port; the UI explains that Windows may request explicit private-network permission when the user invokes sharing.

## Consequences

The token is a temporary bearer secret: anyone who receives it while connected to the LAN can view that clip until expiry. Transport is plain HTTP because local ad-hoc HTTPS identity is not available, so this feature is limited to a trusted private LAN and non-sensitive beta evaluation. Full LAN administration, durable sharing, remote relay, revocation UI and HTTPS pairing remain separate security work.
