"""Windows DPAPI-backed storage for the optional AI API key."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _windows_api() -> tuple[object, object]:
    if os.name != "nt":
        raise RuntimeError("O armazenamento protegido de chaves está disponível apenas no Windows.")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
        wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob), wintypes.LPVOID, wintypes.LPVOID,
        wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    return crypt32, kernel32


def _blob(raw: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(raw)
    return _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect_secret(secret: str) -> bytes:
    """Encrypt text using DPAPI for the current Windows user profile."""
    if not secret:
        raise ValueError("A chave vazia não pode ser protegida.")
    crypt32, kernel32 = _windows_api()
    source, keepalive = _blob(secret.encode("utf-8"))
    encrypted = _DataBlob()
    # CRYPTPROTECT_UI_FORBIDDEN: never display an interactive OS prompt.
    if not crypt32.CryptProtectData(ctypes.byref(source), "Yggdrasil AI key", None, None, None, 0x1, ctypes.byref(encrypted)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(encrypted.pbData, encrypted.cbData)
    finally:
        kernel32.LocalFree(encrypted.pbData)
        del keepalive


def unprotect_secret(ciphertext: bytes) -> str:
    """Decrypt a DPAPI blob created by the same Windows user."""
    if not ciphertext:
        raise ValueError("O arquivo da chave protegida está vazio.")
    crypt32, kernel32 = _windows_api()
    source, keepalive = _blob(ciphertext)
    decrypted = _DataBlob()
    description = wintypes.LPWSTR()
    if not crypt32.CryptUnprotectData(ctypes.byref(source), ctypes.byref(description), None, None, None, 0x1, ctypes.byref(decrypted)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(decrypted.pbData, decrypted.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(decrypted.pbData)
        if description:
            kernel32.LocalFree(description)
        del keepalive
