# ADR-0003: NVR remains authoritative media storage

[中文](0003-nvr-authoritative-media_CN.md)

- Status: Accepted
- Date: 2026-08-12

## Context

Target sites already record continuously to an NVR. A second archive would increase storage, transcoding, reliability and operational burden while weakening the adoption path.

## Decision

Index metadata intervals only. Resolve channel/time against the NVR and export a short derived clip on demand. Do not continuously ingest all recording streams.

## Consequences

Media availability depends on NVR retention and compatibility. Recording coverage, gaps and expired media must be explicit. Clip cache is disposable derived data; bookmark metadata is the durable product index.
