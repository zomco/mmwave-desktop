# Resident fusion review service

[中文](resident_CN.md)

The review UI is optional. Radar history is kept by a background process that
binds to `127.0.0.1` ([ADR-0008](../architecture/decisions/0008-local-clip-review.md)).

```powershell
python -m tracecue_gateway.resident
```

`serve_events` in `tracecue_gateway.resident` lists stored fusion events as JSON.
It does not open an NVR timeline.

## Linux LTS

```ini
[Service]
ExecStart=/usr/bin/python -m tracecue_gateway.resident
Restart=on-failure
```

Install that unit under `systemd` and enable it.

## Windows

Register the same module with the Service Control Manager or Task Scheduler
"at startup". Do not require a logged-in desktop session.

## macOS

A `launchd` agent with `KeepAlive` true and `ProgramArguments` pointing at
`python -m tracecue_gateway.resident`. This slice does not notarize an app bundle.
