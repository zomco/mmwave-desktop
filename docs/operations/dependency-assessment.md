# Dependency assessment

[中文](dependency-assessment_CN.md)

Direct dependencies are deliberately small. Exact development versions live in `requirements-dev.lock.txt` and `desktop/frontend/package-lock.json`; packaging-only versions live in `packaging/windows/requirements.lock.txt`.

| Dependency | Reason | License check | Owner-maintenance assessment |
| --- | --- | --- | --- |
| FastAPI / Starlette / Pydantic | Typed same-origin HTTP API and validation | MIT / BSD-3-Clause / MIT | Widely used, active upstreams; isolate framework code in Desktop so Engine/Gateway remain independent |
| Uvicorn | Loopback ASGI server | BSD-3-Clause | Mature and replaceable behind ASGI; no LAN exposure is enabled |
| React / React DOM | Desktop SPA state and accessible components | MIT | Mature upstream; only same-origin browser UI depends on it |
| qrcode | Generate temporary clip-share QR images entirely in the local SPA | MIT | Mature, small browser library with no network service; exact npm lock retained and generated data never leaves the page |
| Vite / TypeScript | Deterministic frontend build and static checking | MIT / Apache-2.0 | Active upstreams; build-time only, exact lock retained |
| Tailwind CSS / Tailwind Vite plugin | Utility-first UI styling that developers can adjust in colocated React markup | MIT / MIT | Build-time only, active upstream, exact npm lock retained; no runtime service or network dependency |
| Vitest | Frontend invariant tests | MIT | Build/test-only; small tests can migrate if upstream maintenance changes |
| pytest / httpx | Python behavior and HTTP integration tests | MIT / BSD-3-Clause | Development-only; production code does not import them |
| PyInstaller | Windows one-folder assembly | GPL-2.0-or-later with bootloader exception | Packaging-only and pinned; verify the current exception/notices for each release |
| Inno Setup | Per-user Windows installer | Custom redistribution terms | External build tool; not vendored. Owner must review current commercial redistribution terms before release |
| FFmpeg / FFprobe | NVR media remux/transcode/probe without Python video decoding | Pinned BtbN build: LGPL-3.0-or-later; GPL/nonfree disabled; OpenH264 remains separately reviewable for patent posture | Version/source/archive/executable/license hashes and reproducible build-script commit are pinned; binaries stay outside Git; release remains gated on the complete static-dependency source/notices mirror and hardware evidence |
| NumPy / ONNX Runtime (optional vision extra) | Convert bounded FFmpeg-decoded BGR tensors and run local event inference | BSD-3-Clause / MIT | Optional and isolated behind a small analyzer interface; exact versions live in `requirements-vision.lock.txt`; base Desktop runs without them. Reassess Windows CPU/GPU providers before release packaging |
| YOLOX-Nano ONNX weights (optional) | Initial person/vehicle detector for event-window validation | Apache-2.0 code/model source; pinned upstream release and license hashes | Weight stays outside Git and is fetched by `packaging/windows/fetch-vision-model.ps1`. Bundling is blocked until cleared day/night hardware accuracy, latency and redistribution evidence exists |

The Python standard library implements Hikvision HTTP Digest, XML parsing, SQLite and Gateway TCP acquisition to avoid additional protocol/runtime dependencies. Untrusted XML is rejected if it includes DTD/entity declarations and is depth/size bounded.

Dependabot covers npm and all Python module manifests; CodeQL covers executable Python and TypeScript. Dependency updates must preserve the exact locks and rerun all module tests.
