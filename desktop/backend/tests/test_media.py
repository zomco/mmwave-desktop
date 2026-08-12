from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tracecue_desktop.errors import MediaError
from tracecue_desktop.media import FFmpegRunner, _with_credentials


def test_credentials_are_percent_encoded_only_at_subprocess_boundary() -> None:
    value = _with_credentials("rtsp://192.0.2.10:554/track", "user@example", "p:a ss")
    expected = "rtsp://" + "user%40example" + ":" + "p%3Aa%20ss" + "@192.0.2.10:554/track"
    assert value == expected


def test_credential_bearing_upstream_locator_is_rejected() -> None:
    unsafe = "rtsp://" + "upstream" + ":" + "secret" + "@192.0.2.10/track"
    with pytest.raises(MediaError) as raised:
        _with_credentials(unsafe, "user", "password")
    assert raised.value.code == "MEDIA_LOCATOR_UNSAFE"


def test_running_subprocess_can_be_cancelled(tmp_path: Path) -> None:
    runner = FFmpegRunner(Path("unused"), Path("unused"), tmp_path)
    checks = 0

    def cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 2

    with pytest.raises(MediaError) as raised:
        runner._run([sys.executable, "-c", "import time; time.sleep(30)"], cancelled)
    assert raised.value.code == "JOB_CANCELLED"
