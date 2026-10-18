"""Windows-protected storage for the model API key.

The key is encrypted for the current Windows user with DPAPI. It is never
returned to the browser and the settings JSON only contains provider metadata.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _protect(data: bytes, decrypt: bool = False) -> bytes:
    if not data:
        return b""
    if __import__("os").name != "nt":
        raise RuntimeError("API Key 安全保存只支持 Windows DPAPI")
    source = ctypes.create_string_buffer(data)
    input_blob = _Blob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    output_blob = _Blob()
    crypt = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    ok = crypt(ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob))
    if not ok:
        raise OSError(ctypes.get_last_error(), "Windows DPAPI 操作失败")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def save(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = _protect(value.encode("utf-8"))
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encrypted)
    temporary.replace(path)


def load(path: Path) -> str:
    try:
        encrypted = path.read_bytes()
    except FileNotFoundError:
        return ""
    return _protect(encrypted, decrypt=True).decode("utf-8")
