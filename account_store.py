import hashlib
import hmac
import json
import os

import asyncpg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DATABASE_URL = os.environ.get("DATABASE_URL")
ENCRYPTION_SECRET = os.environ.get("ENCRYPTION_SECRET")

DATABASE_CONFIGURED = bool(DATABASE_URL and ENCRYPTION_SECRET)


class AccountStoreError(RuntimeError):
    pass


def _derive_keys() -> tuple[bytes, bytes]:
    """Derive the AES-GCM key and HMAC key from ENCRYPTION_SECRET.

    AES key = SHA256(secret || 0x01); HMAC key = SHA256(secret || 0x02).
    """
    if not ENCRYPTION_SECRET:
        raise AccountStoreError("ENCRYPTION_SECRET is not set.")
    try:
        secret_bytes = bytes.fromhex(ENCRYPTION_SECRET)
    except ValueError as exc:
        raise AccountStoreError("ENCRYPTION_SECRET must be a hex-encoded 256-bit value.") from exc
    if len(secret_bytes) != 32:
        raise AccountStoreError("ENCRYPTION_SECRET must decode to exactly 32 bytes (256 bits).")

    aes_key = hashlib.sha256(secret_bytes + b"\x01").digest()
    hmac_key = hashlib.sha256(secret_bytes + b"\x02").digest()
    return aes_key, hmac_key


def _hmac_email(email: str, hmac_key: bytes) -> bytes:
    normalized = email.strip().lower().encode("utf-8")
    return hmac.new(hmac_key, normalized, hashlib.sha256).digest()


async def _connect() -> asyncpg.Connection:
    if not DATABASE_URL:
        raise AccountStoreError("DATABASE_URL is not set.")
    try:
        # statement_cache_size=0: required for Neon's pooled (pgbouncer, transaction-mode)
        # connection string, which doesn't support server-side prepared statements.
        return await asyncpg.connect(dsn=DATABASE_URL, statement_cache_size=0)
    except (OSError, asyncpg.PostgresError) as exc:
        raise AccountStoreError(f"Could not connect to the database: {exc}") from exc


async def ensure_schema() -> None:
    if not DATABASE_CONFIGURED:
        return
    conn = await _connect()
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                email_hmac BYTEA NOT NULL UNIQUE,
                account_type_ciphertext BYTEA NOT NULL,
                account_type_iv BYTEA NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS brand_profiles (
                email_hmac BYTEA PRIMARY KEY,
                data BYTEA NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    finally:
        await conn.close()


async def save_account_type(email: str, account_type: str) -> None:
    aes_key, hmac_key = _derive_keys()
    email_hmac = _hmac_email(email, hmac_key)

    iv = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(iv, account_type.encode("utf-8"), None)

    conn = await _connect()
    try:
        await conn.execute(
            """
            INSERT INTO users (email_hmac, account_type_ciphertext, account_type_iv)
            VALUES ($1, $2, $3)
            ON CONFLICT (email_hmac)
            DO UPDATE SET
                account_type_ciphertext = EXCLUDED.account_type_ciphertext,
                account_type_iv = EXCLUDED.account_type_iv,
                updated_at = now()
            """,
            email_hmac,
            ciphertext,
            iv,
        )
    except asyncpg.PostgresError as exc:
        raise AccountStoreError(f"Failed to save account type: {exc}") from exc
    finally:
        await conn.close()


async def get_account_type(email: str) -> str | None:
    aes_key, hmac_key = _derive_keys()
    email_hmac = _hmac_email(email, hmac_key)

    conn = await _connect()
    try:
        row = await conn.fetchrow(
            "SELECT account_type_ciphertext, account_type_iv FROM users WHERE email_hmac = $1",
            email_hmac,
        )
    except asyncpg.PostgresError as exc:
        raise AccountStoreError(f"Failed to look up account type: {exc}") from exc
    finally:
        await conn.close()

    if row is None:
        return None

    try:
        plaintext = AESGCM(aes_key).decrypt(row["account_type_iv"], row["account_type_ciphertext"], None)
    except Exception as exc:
        raise AccountStoreError(f"Failed to decrypt account type: {exc}") from exc
    return plaintext.decode("utf-8")


async def save_brand_profile(email: str, profile: dict) -> None:
    """Save an arbitrary dict of brand profile fields as a single encrypted blob.

    Encoded as JSON before encryption, so new fields can be added later without
    a schema change or migration — old rows simply won't have the new keys.
    """
    aes_key, hmac_key = _derive_keys()
    email_hmac = _hmac_email(email, hmac_key)

    iv = os.urandom(12)
    plaintext = json.dumps(profile).encode("utf-8")
    ciphertext = AESGCM(aes_key).encrypt(iv, plaintext, None)
    blob = iv + ciphertext

    conn = await _connect()
    try:
        await conn.execute(
            """
            INSERT INTO brand_profiles (email_hmac, data)
            VALUES ($1, $2)
            ON CONFLICT (email_hmac)
            DO UPDATE SET data = EXCLUDED.data, updated_at = now()
            """,
            email_hmac,
            blob,
        )
    except asyncpg.PostgresError as exc:
        raise AccountStoreError(f"Failed to save brand profile: {exc}") from exc
    finally:
        await conn.close()


async def get_brand_profile(email: str) -> dict | None:
    aes_key, hmac_key = _derive_keys()
    email_hmac = _hmac_email(email, hmac_key)

    conn = await _connect()
    try:
        row = await conn.fetchrow("SELECT data FROM brand_profiles WHERE email_hmac = $1", email_hmac)
    except asyncpg.PostgresError as exc:
        raise AccountStoreError(f"Failed to look up brand profile: {exc}") from exc
    finally:
        await conn.close()

    if row is None:
        return None

    blob = bytes(row["data"])
    iv, ciphertext = blob[:12], blob[12:]
    try:
        plaintext = AESGCM(aes_key).decrypt(iv, ciphertext, None)
        return json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise AccountStoreError(f"Failed to decrypt brand profile: {exc}") from exc
