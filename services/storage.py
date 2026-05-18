"""Hetzner Object Storage (S3-kompatibel) für öffentliche Assets wie Anbieter-Logos."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import BinaryIO
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    """Fehler beim Upload/Löschen in Object Storage."""


@dataclass(frozen=True)
class HetznerStorageConfig:
    access_key: str
    secret_key: str
    bucket_name: str
    endpoint_url: str
    public_base_url: str | None = None


_config: HetznerStorageConfig | None = None


def _read_config_from_environ() -> HetznerStorageConfig | None:
    access_key = os.environ.get("HETZNER_ACCESS_KEY", "").strip()
    secret_key = os.environ.get("HETZNER_SECRET_KEY", "").strip()
    bucket_name = os.environ.get("HETZNER_BUCKET_NAME", "").strip()
    endpoint_url = os.environ.get("HETZNER_ENDPOINT_URL", "").strip().rstrip("/")
    public_base = (os.environ.get("HETZNER_PUBLIC_URL") or "").strip().rstrip("/") or None
    if not (access_key and secret_key and bucket_name and endpoint_url):
        return None
    return HetznerStorageConfig(
        access_key=access_key,
        secret_key=secret_key,
        bucket_name=bucket_name,
        endpoint_url=endpoint_url,
        public_base_url=public_base,
    )


def configure_storage(cfg: HetznerStorageConfig | None = None) -> None:
    """Konfiguration aus ``cfg`` oder aktueller Umgebung (nach ``load_dotenv()``)."""
    global _config
    _config = cfg if cfg is not None else _read_config_from_environ()


def _require_config() -> HetznerStorageConfig:
    if _config is None:
        configure_storage()
    if _config is None:
        raise StorageError("Hetzner Object Storage ist nicht konfiguriert")
    return _config


def hetzner_object_storage_available() -> bool:
    """True, wenn alle Zugangsdaten gesetzt sind (ohne Netzwerkcheck)."""
    if _config is None:
        configure_storage()
    return _config is not None


def _public_url_prefix(cfg: HetznerStorageConfig) -> str:
    if cfg.public_base_url:
        return f"{cfg.public_base_url}/"
    parsed = urlparse(cfg.endpoint_url)
    scheme = parsed.scheme or "https"
    host = parsed.netloc
    if not host:
        raise StorageError("HETZNER_ENDPOINT_URL ist ungültig")
    return f"{scheme}://{cfg.bucket_name}.{host}/"


def _region_from_endpoint(endpoint_url: str) -> str:
    host = urlparse(endpoint_url).netloc
    if host.endswith(".your-objectstorage.com"):
        return host.split(".", 1)[0]
    return "us-east-1"


def _guess_content_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".png"):
        return "image/png"
    return "image/jpeg"


@lru_cache(maxsize=1)
def _s3_client_cached(access_key: str, secret_key: str, endpoint_url: str):
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=_region_from_endpoint(endpoint_url),
        config=Config(signature_version="s3v4"),
    )


def _s3_client(cfg: HetznerStorageConfig):
    return _s3_client_cached(cfg.access_key, cfg.secret_key, cfg.endpoint_url)


def public_url_for_key(object_key: str) -> str:
    """Öffentliche URL für einen Object-Key (ohne Upload)."""
    cfg = _require_config()
    key = object_key.lstrip("/")
    return f"{_public_url_prefix(cfg)}{key}"


def upload_logo(file: BinaryIO, filename: str) -> str:
    """Lädt eine Bilddatei hoch und gibt die öffentliche URL zurück."""
    cfg = _require_config()
    key = filename.lstrip("/")
    if not key:
        raise StorageError("Object-Key fehlt")

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

    try:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            client.put_object(**put_args, ACL="public-read")
        except (ClientError, BotoCoreError) as acl_err:
            logger.warning(
                "put_object mit ACL public-read fehlgeschlagen, erneuter Versuch ohne ACL: %r",
                acl_err,
            )
            client.put_object(**put_args)
    except Exception as e:
        logger.exception("upload_logo fehlgeschlagen key=%s", key)
        raise StorageError(f"Upload fehlgeschlagen: {e}") from e

    return public_url_for_key(key)


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
    except Exception:
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
