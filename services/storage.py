"""Hetzner Object Storage (S3-kompatibel) für öffentliche Assets wie Anbieter-Logos."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import BinaryIO
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# True, wenn configure_storage() mit explizitem HetznerStorageConfig aufgerufen wurde (Tests).
_config_explicit: bool = False


class StorageError(RuntimeError):
    """Fehler beim Upload/Löschen in Object Storage."""


@dataclass(frozen=True)
class HetznerStorageConfig:
    access_key: str
    secret_key: str
    bucket_name: str
    endpoint_url: str
    public_base_url: str | None = None
    region_name: str | None = None


_config: HetznerStorageConfig | None = None


def _read_config_from_environ() -> HetznerStorageConfig | None:
    access_key = os.environ.get("HETZNER_ACCESS_KEY", "").strip()
    secret_key = os.environ.get("HETZNER_SECRET_KEY", "").strip()
    bucket_name = os.environ.get("HETZNER_BUCKET_NAME", "").strip()
    endpoint_url = os.environ.get("HETZNER_ENDPOINT_URL", "").strip().rstrip("/")
    public_base = (os.environ.get("HETZNER_PUBLIC_URL") or "").strip().rstrip("/") or None
    region_name = (os.environ.get("HETZNER_REGION") or "").strip() or None

    missing = [
        name
        for name, val in (
            ("HETZNER_ACCESS_KEY", access_key),
            ("HETZNER_SECRET_KEY", secret_key),
            ("HETZNER_BUCKET_NAME", bucket_name),
            ("HETZNER_ENDPOINT_URL", endpoint_url),
        )
        if not val
    ]
    if missing:
        print(f"[storage] Hetzner nicht konfiguriert – fehlend: {', '.join(missing)}")
        return None

    print(
        "[storage] Konfiguration aus Umgebung geladen "
        f"(access_key=gesetzt, bucket={bucket_name}, endpoint={endpoint_url})"
    )
    return HetznerStorageConfig(
        access_key=access_key,
        secret_key=secret_key,
        bucket_name=bucket_name,
        endpoint_url=endpoint_url,
        public_base_url=public_base,
        region_name=region_name,
    )


def configure_storage(cfg: HetznerStorageConfig | None = None) -> None:
    """Konfiguration aus ``cfg`` oder aktueller Umgebung (nach ``load_dotenv()``)."""
    global _config, _config_explicit
    if cfg is not None:
        _config = cfg
        _config_explicit = True
    else:
        _config_explicit = False
        _config = _read_config_from_environ()
    _clear_s3_client_cache()


def _refresh_config_from_environ_if_needed() -> None:
    if not _config_explicit:
        configure_storage()


def _require_config() -> HetznerStorageConfig:
    _refresh_config_from_environ_if_needed()
    if _config is None:
        raise StorageError("Hetzner Object Storage ist nicht konfiguriert")
    return _config


def hetzner_object_storage_available() -> bool:
    """True, wenn alle Zugangsdaten gesetzt sind (ohne Netzwerkcheck)."""
    _refresh_config_from_environ_if_needed()
    available = _config is not None
    if not available:
        print("[storage] hetzner_object_storage_available() -> False")
    return available


def _public_url_prefix(cfg: HetznerStorageConfig) -> str:
    if cfg.public_base_url:
        return f"{cfg.public_base_url}/"
    parsed = urlparse(cfg.endpoint_url)
    scheme = parsed.scheme or "https"
    host = parsed.netloc
    if not host:
        raise StorageError("HETZNER_ENDPOINT_URL ist ungültig")
    base = cfg.endpoint_url.rstrip("/")
    return f"{base}/{cfg.bucket_name}/"


def _region_name(cfg: HetznerStorageConfig) -> str:
    if cfg.region_name:
        return cfg.region_name
    host = urlparse(cfg.endpoint_url).netloc
    if host.endswith(".your-objectstorage.com"):
        return host.split(".", 1)[0]
    return "eu-central-1"


def _guess_content_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".png"):
        return "image/png"
    return "image/jpeg"


def _clear_s3_client_cache() -> None:
    _s3_client_cached.cache_clear()


@lru_cache(maxsize=8)
def _s3_client_cached(
    access_key: str,
    secret_key: str,
    endpoint_url: str,
    region_name: str,
):
    import boto3
    from botocore.config import Config

    print(
        f"[storage] boto3-Client: endpoint={endpoint_url}, region={region_name}, "
        "signature=s3v4, addressing=path"
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region_name,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def _s3_client(cfg: HetznerStorageConfig):
    try:
        return _s3_client_cached(
            cfg.access_key,
            cfg.secret_key,
            cfg.endpoint_url,
            _region_name(cfg),
        )
    except Exception as e:
        print(f"[storage] ERROR S3-Client: {e}")
        logger.exception("S3-Client konnte nicht erstellt werden")
        raise StorageError(f"S3-Client konnte nicht erstellt werden: {e}") from e


def public_url_for_key(object_key: str) -> str:
    """Öffentliche URL für einen Object-Key (ohne Upload)."""
    cfg = _require_config()
    key = object_key.lstrip("/")
    return f"{_public_url_prefix(cfg)}{key}"


def upload_logo(file: BinaryIO, filename: str) -> str:
    """Lädt eine Bilddatei hoch und gibt die öffentliche URL zurück.

    Wirft ``StorageError`` bei Fehlern – kein unbehandelter Crash im Worker.
    """
    try:
        cfg = _require_config()
        key = filename.lstrip("/")
        if not key:
            raise StorageError("Object-Key fehlt")

        print(f"[storage] Uploading to Hetzner: {key}")
        print(f"[storage] Bucket: {cfg.bucket_name}")
        print(f"[storage] Endpoint: {cfg.endpoint_url}")
        print(f"[storage] Region: {_region_name(cfg)}")

        body = file.read()
        if not body:
            raise StorageError("Leere Datei – Upload abgebrochen")

        client = _s3_client(cfg)
        put_args = {
            "Bucket": cfg.bucket_name,
            "Key": key,
            "Body": body,
            "ContentType": _guess_content_type(key),
        }

        from botocore.exceptions import BotoCoreError, ClientError

        try:
            client.put_object(**put_args, ACL="public-read")
        except (ClientError, BotoCoreError) as acl_err:
            print(f"[storage] ACL public-read fehlgeschlagen, Retry ohne ACL: {acl_err}")
            logger.warning(
                "put_object mit ACL public-read fehlgeschlagen, erneuter Versuch ohne ACL: %r",
                acl_err,
            )
            client.put_object(**put_args)

        public_url = public_url_for_key(key)
        print(f"[storage] OK: {public_url}")
        return public_url
    except StorageError:
        raise
    except Exception as e:
        print(f"[storage] ERROR: {e}")
        logger.exception("upload_logo fehlgeschlagen filename=%s", filename)
        raise StorageError(f"Upload fehlgeschlagen: {e}") from e


def delete_logo(filename: str) -> None:
    """Entfernt das Objekt mit Key ``filename`` (z. B. ``provider-logos/uuid.jpg``)."""
    if not hetzner_object_storage_available():
        return
    cfg = _require_config()
    key = filename.lstrip("/")
    if not key:
        return
    try:
        _s3_client(cfg).delete_object(Bucket=cfg.bucket_name, Key=key)
        print(f"[storage] Gelöscht: {key}")
    except Exception as e:
        print(f"[storage] ERROR delete: {e}")
        logger.exception("delete_logo fehlgeschlagen key=%s", key)


def delete_managed_logo_by_public_url(url: str | None) -> None:
    """Löscht das Objekt nur, wenn ``url`` zum konfigurierten Bucket passt."""
    if not url or not hetzner_object_storage_available():
        return
    cfg = _require_config()
    prefix = _public_url_prefix(cfg)
    clean = url.split("?", 1)[0].strip()
    if not clean.startswith(prefix):
        return
    key = clean[len(prefix) :].lstrip("/")
    if key:
        delete_logo(key)
