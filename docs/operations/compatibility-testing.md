# Compatibility testing

[中文](compatibility-testing_CN.md)

## Probe before promises

The first hardware deliverable is a read-only probe and compatibility record, not a universal adapter claim. Test only devices the owner controls or is authorized to access.

## Test sequence

1. Record model, firmware, device timezone and test-network topology.
2. Probe identity/time and measure skew without changing device settings.
3. Enumerate channels and preserve redacted raw fixtures.
4. Search a bounded known recording window, including pagination.
5. Resolve playback using returned URI and/or channel/time method.
6. Run FFprobe; attempt H.264 remux or documented transcode profile.
7. Compare requested versus actual clip coverage and browser playback.
8. Repeat after process restart and with invalid credentials/time gaps.

## Evidence artifact

Each compatibility entry contains anonymized fixture hashes, command/application version, expected capability states, codecs, latency observations and known failures. Never commit credentials or customer images.

## Support levels

- **Supported:** repeated probe/search/export passes on recorded model/firmware.
- **Experimental:** partial success or insufficient repetition.
- **Unknown:** not tested.
- **Unsupported:** reproduced protocol/capability absence with valid authentication.

One device's result never upgrades an entire brand or series automatically.
