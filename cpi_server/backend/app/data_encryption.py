"""Authenticated encryption for credit records and sensitive AI trace fields."""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from functools import lru_cache
import json
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import config


FERNET_PREFIX = "cpi-fernet:v1:"
AES_PREFIX = "cpi-aes256gcm:v2:"
RECORD_KEY = "_cpi_encrypted_record"


@lru_cache(maxsize=16)
def _ciphers(key: str) -> tuple[Fernet, AESGCM]:
    if not key:
        raise RuntimeError("Data encryption key is unavailable")
    legacy = Fernet(key)
    aes_key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=b"credit-policy-intelligence:data-encryption:aes256gcm:v2",
    ).derive(urlsafe_b64decode(key))
    return legacy, AESGCM(aes_key)


def encrypt_text(value: str | None) -> str | None:
    if value is None or not config.DATA_ENCRYPTION_KEY:
        return value
    _, cipher = _ciphers(config.DATA_ENCRYPTION_KEY)
    nonce = secrets.token_bytes(12)
    encrypted = cipher.encrypt(nonce, value.encode("utf-8"), AES_PREFIX.encode("ascii"))
    return AES_PREFIX + urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_text(value: str | None) -> str | None:
    if value is None:
        return value
    keys = (config.DATA_ENCRYPTION_KEY, *config.DATA_ENCRYPTION_PREVIOUS_KEYS)
    if value.startswith(AES_PREFIX):
        data = urlsafe_b64decode(value[len(AES_PREFIX):])
        for key in keys:
            if key:
                _, cipher = _ciphers(key)
                try:
                    return cipher.decrypt(data[:12], data[12:], AES_PREFIX.encode("ascii")).decode("utf-8")
                except InvalidTag:
                    continue
        raise InvalidTag("No configured key could authenticate the stored data")
    if value.startswith(FERNET_PREFIX):
        token = value[len(FERNET_PREFIX):].encode("ascii")
        for key in keys:
            if key:
                legacy, _ = _ciphers(key)
                try:
                    return legacy.decrypt(token).decode("utf-8")
                except InvalidToken:
                    continue
        raise InvalidToken("No configured key could authenticate the stored data")
    return value


def encode_record(record: dict) -> str:
    serialized = json.dumps(record, default=str)
    if not config.DATA_ENCRYPTION_KEY:
        return serialized
    return json.dumps({RECORD_KEY: encrypt_text(serialized)})


def decode_record(record: dict) -> dict:
    if record.keys() == {RECORD_KEY}:
        return json.loads(decrypt_text(record[RECORD_KEY]))
    return record
