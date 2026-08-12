# Validation plan

[中文](validation_CN.md)

## Separate hypotheses

The NVR foundation validates installation, compatibility and clip extraction. It does not validate high-confidence differentiation. The timeline phase validates signal quality and operator value.

## Primary metrics

| Metric | Definition |
| --- | --- |
| Important-event recall | Labelled important events covered by bookmarks / all labelled important events |
| Bookmark precision | Person-relevant bookmarks / all bookmarks |
| Review-volume reduction | `1 - high-confidence bookmarks / NVR candidates` for the same window |
| Find time | Time from a room/date request to opening the correct clip |
| Clip success rate | Playable clips / valid clip requests |
| Time-to-first-play | Request accepted to first playable browser response |

Never report review-volume reduction without recall. Reducing bookmark count by dropping real events is not improvement.

## Evidence levels

1. Unit/contract fixtures prove parsing and algorithms.
2. Golden labelled sessions prove expected event coverage.
3. Model/firmware hardware tests prove compatibility.
4. Unfamiliar-user tests prove installability and workflow.
5. Pilot operations prove repeat use and willingness to pay.

Open-source usage and GitHub stars are supporting signals, not product-market validation.

## Minimum golden dataset

- Raw NVR candidates for a complete test day.
- Sensor observations and generated intervals.
- Human labels with start/end, space and importance.
- NVR/device time observations and any manual skew correction.
- Expected matched recording coverage and clip outcome.
- A versioned manifest identifying algorithm/config versions.

Customer footage must not enter the repository. Store synthetic or explicitly cleared redacted fixtures only.
