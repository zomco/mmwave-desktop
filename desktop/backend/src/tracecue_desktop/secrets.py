"""Secret references backed by Windows DPAPI, never SQLite plaintext."""

from __future__ import annotations

import base64
import ctypes
import json
import os
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Protocol


class SecretStore(Protocol):
    def put(self, reference: str, username: str, password: str) -> None: ...
    def get(self, reference: str) -> tuple[str, str]: ...
    def delete(self, reference: str) -> None: ...


class InMemorySecretStore:
    def __init__(self) -> None:
        self._values: dict[str, tuple[str, str]] = {}

    def put(self, reference: str, username: str, password: str) -> None:
        self._values[reference] = (username, password)

    def get(self, reference: str) -> tuple[str, str]:
        return self._values[reference]

    def delete(self, reference: str) -> None:
        self._values.pop(reference, None)


if os.name == "nt":
    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def _protect(value: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("TraceCue production credential storage requires Windows DPAPI")
    source_buffer = ctypes.create_string_buffer(value)
    source = _DataBlob(len(value), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    output = _DataBlob()
    if not _crypt32.CryptProtectData(
        ctypes.byref(source), "TraceCue credential", None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def _unprotect(value: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("TraceCue production credential storage requires Windows DPAPI")
    source_buffer = ctypes.create_string_buffer(value)
    source = _DataBlob(len(value), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    output = _DataBlob()
    if not _crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


class WindowsDpapiSecretStore:
    def __init__(self, path: Path):
        if os.name != "nt":
            raise RuntimeError("Windows DPAPI secret store is only available on Windows")
        self.path = path
        self._lock = threading.RLock()

    def put(self, reference: str, username: str, password: str) -> None:
        if not reference or not username or not password:
            raise ValueError("reference, username and password must be non-empty")
        with self._lock:
            values = self._read()
            plaintext = json.dumps({"username": username, "password": password}, ensure_ascii=False).encode("utf-8")
            values[reference] = base64.b64encode(_protect(plaintext)).decode("ascii")
            self._write(values)

    def get(self, reference: str) -> tuple[str, str]:
        with self._lock:
            encrypted = base64.b64decode(self._read()[reference])
            value = json.loads(_unprotect(encrypted))
            return value["username"], value["password"]

    def delete(self, reference: str) -> None:
        with self._lock:
            values = self._read()
            if reference in values:
                del values[reference]
                self._write(values)

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            raise RuntimeError("Credential store is malformed")
        return value

    def _write(self, value: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_suffix(self.path.suffix + ".partial")
        partial.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        partial.replace(self.path)
