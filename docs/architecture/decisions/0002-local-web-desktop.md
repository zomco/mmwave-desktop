# ADR-0002: Loopback local Web desktop

[中文](0002-local-web-desktop_CN.md)

- Status: Accepted
- Date: 2026-08-12

## Context

Browser JavaScript cannot reliably reach private NVRs from a cloud HTTPS page because of network, CORS, private-network and media constraints. The target user will not operate Docker or Home Assistant.

## Decision

Ship a Windows process that serves the SPA and HTTP API from the same origin and opens a loopback URL. Bind to `127.0.0.1` by default. LAN mode is a later explicit security feature.

## Consequences

Installation and signing become product responsibilities. The design avoids browser mixed-content/CORS dead ends and keeps NVR credentials local.
