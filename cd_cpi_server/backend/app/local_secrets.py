"""Windows-local encrypted secret storage with DPAPI-protected AES key versions."""

from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
import secrets
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Mapping

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ROTATION_DAYS = 90
AAD_PREFIX = b"credit-dossier/local-secret/v1\0"
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / ".data"
KEYRING_PATH = DEFAULT_DATA_DIR / "secret-keyring.dpapi"
SECRETS_PATH = DEFAULT_DATA_DIR / "secrets.aesgcm.json"
_store_lock = threading.RLock()


class LocalSecretError(RuntimeError):
    """Raised when the encrypted local secret store cannot be used safely."""


def _serialized(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        with _store_lock:
            return function(*args, **kwargs)
    return wrapper


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _dpapi(data: bytes, protect: bool, *, machine_scope: bool = True) -> bytes:
    if os.name != "nt":
        raise LocalSecretError("The local secret keyring requires Windows DPAPI.")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    def blob(value: bytes) -> tuple[Blob, object]:
        buffer = ctypes.create_string_buffer(value)
        return Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    source, source_buffer = blob(data)
    entropy, entropy_buffer = blob(b"credit-dossier/local-secrets/v1")
    output = Blob()
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    # Local-machine scope allows the backend to run under a service identity.
    # Access is still constrained by the ACL on backend/.data. The scope flag
    # is relevant only while protecting; Windows reads the scope from the blob
    # while unprotecting.
    flags = 0x01 | (0x04 if protect and machine_scope else 0x00)
    ok = function(
        ctypes.byref(source), None, ctypes.byref(entropy), None, None,
        flags, ctypes.byref(output),
    )
    _ = source_buffer, entropy_buffer
    if not ok:
        raise LocalSecretError(f"DPAPI failed with Windows error {ctypes.get_last_error()}.")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel32.LocalFree(output.data)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _read_keyring() -> dict:
    if not KEYRING_PATH.exists():
        now = _utcnow()
        ring = {
            "active_version": 1,
            "last_rotated_at": _iso(now),
            "keys": {"1": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")},
        }
        _write_keyring(ring)
        return ring
    try:
        return json.loads(_dpapi(KEYRING_PATH.read_bytes(), protect=False))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise LocalSecretError("The DPAPI-protected secret keyring is invalid.") from exc


def _write_keyring(ring: dict) -> None:
    encoded = json.dumps(ring, sort_keys=True, separators=(",", ":")).encode("utf-8")
    _atomic_write(KEYRING_PATH, _dpapi(encoded, protect=True))


def rewrap_keyring_for_local_machine() -> None:
    """Re-protect an accessible legacy user-scoped keyring for service use."""
    ring = _read_keyring()
    _write_keyring(ring)


def _read_document() -> dict:
    if not SECRETS_PATH.exists():
        return {"format": 1, "secrets": {}}
    try:
        document = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalSecretError("The AES-GCM secret document is invalid.") from exc
    if document.get("format") != 1 or not isinstance(document.get("secrets"), dict):
        raise LocalSecretError("Unsupported encrypted secret document format.")
    return document


def _write_document(document: dict) -> None:
    data = json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    _atomic_write(SECRETS_PATH, data)


def _encrypt(name: str, value: str, version: int, key: bytes) -> dict:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, value.encode("utf-8"), AAD_PREFIX + name.encode("utf-8"))
    return {
        "key_version": version,
        "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
        "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
    }


def _decrypt(name: str, record: dict, ring: dict) -> str:
    try:
        key = base64.urlsafe_b64decode(ring["keys"][str(record["key_version"])])
        nonce = base64.urlsafe_b64decode(record["nonce"])
        ciphertext = base64.urlsafe_b64decode(record["ciphertext"])
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, AAD_PREFIX + name.encode("utf-8"))
        return plaintext.decode("utf-8")
    except Exception as exc:
        raise LocalSecretError(f"Unable to authenticate or decrypt secret {name!r}.") from exc


@_serialized
def store_secrets(namespace: str, values: Mapping[str, str]) -> int:
    """Encrypt values under a namespace and return the active key version."""
    ring = _read_keyring()
    document = _read_document()
    version = int(ring["active_version"])
    key = base64.urlsafe_b64decode(ring["keys"][str(version)])
    for variable, value in values.items():
        name = f"{namespace}.{variable}"
        document["secrets"][name] = _encrypt(name, value, version, key)
    _write_document(document)
    return version


@_serialized
def load_secrets(namespace: str) -> dict[str, str]:
    if not SECRETS_PATH.exists():
        return {}
    ring = _read_keyring()
    prefix = namespace + "."
    return {
        name[len(prefix):]: _decrypt(name, record, ring)
        for name, record in _read_document()["secrets"].items()
        if name.startswith(prefix)
    }


def load_into_environment(namespace: str, *, overwrite: bool = True) -> int:
    values = load_secrets(namespace)
    for name, value in values.items():
        if overwrite or name not in os.environ:
            os.environ[name] = value
    return len(values)


@_serialized
def rotation_status() -> dict[str, object]:
    ring = _read_keyring()
    rotated_at = _parse_time(ring["last_rotated_at"])
    due_at = rotated_at + timedelta(days=ROTATION_DAYS)
    return {
        "active_version": int(ring["active_version"]),
        "last_rotated_at": rotated_at,
        "next_rotation_at": due_at,
        "rotation_due": _utcnow() >= due_at,
    }


@_serialized
def rotate_if_due(*, force: bool = False) -> dict[str, object]:
    """Atomically re-encrypt every local secret and then retire the old keys."""
    ring = _read_keyring()
    previous_version = int(ring["active_version"])
    previous_time = _parse_time(ring["last_rotated_at"])
    if not force and _utcnow() < previous_time + timedelta(days=ROTATION_DAYS):
        return {**rotation_status(), "rotated": False, "secret_count": 0}

    document = _read_document()
    plaintext = {
        name: _decrypt(name, record, ring)
        for name, record in document["secrets"].items()
    }
    new_version = previous_version + 1
    new_key = secrets.token_bytes(32)
    replacement = {
        "format": 1,
        "secrets": {
            name: _encrypt(name, value, new_version, new_key)
            for name, value in plaintext.items()
        },
    }
    # Keep both key versions until the fully re-encrypted document is durable.
    staged_ring = dict(ring)
    staged_ring["keys"] = dict(ring["keys"])
    staged_ring["keys"][str(new_version)] = base64.urlsafe_b64encode(new_key).decode("ascii")
    _write_keyring(staged_ring)
    _write_document(replacement)
    rotated_at = _utcnow()
    final_ring = {
        "active_version": new_version,
        "last_rotated_at": _iso(rotated_at),
        "keys": {str(new_version): staged_ring["keys"][str(new_version)]},
    }
    _write_keyring(final_ring)
    return {
        "rotated": True,
        "active_version": new_version,
        "last_rotated_at": rotated_at,
        "next_rotation_at": rotated_at + timedelta(days=ROTATION_DAYS),
        "rotation_due": False,
        "secret_count": len(plaintext),
    }


def _parse_env(path: Path, names: set[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() in names and value:
            values[name.strip()] = value.strip()
    return values


def migrate_env_file(path: Path, namespace: str, names: set[str]) -> int:
    """Encrypt selected variables and remove their plaintext values from an env file."""
    values = _parse_env(path, names)
    if not values:
        return 0
    store_secrets(namespace, values)
    output: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        name = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if name in values and not stripped.startswith("#"):
            output.append(f"# {name} is stored in backend/.data/secrets.aesgcm.json")
        else:
            output.append(line)
    _atomic_write(path, ("\n".join(output) + "\n").encode("utf-8"))
    return len(values)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("env_file", type=Path)
    parser.add_argument("namespace")
    parser.add_argument("names", nargs="+")
    args = parser.parse_args()
    count = migrate_env_file(args.env_file.resolve(), args.namespace, set(args.names))
    print(f"Migrated {count} secret(s) into the DPAPI/AES-256-GCM store.")


if __name__ == "__main__":
    main()
