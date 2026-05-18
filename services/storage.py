"""Hetzner Object Storage (S3-kompatibel) für öffentliche Assets wie Anbieter-Logos."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import BinaryIO
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

HETZNER_ACCESS_KEY = os.environ.get("HETZNER_ACCESS_KEY", "").strip()
HETZNER_SECRET_KEY = os.environ.get("HETZNER_SECRET_KEY", "").strip()
HETZNER_BUCKET_NAME = os.environ.get("HETZNER_BUCKET_NAME", "").strip()
HETZNER_ENDPOINT_URL = os.environ.get("HETZNER_ENDPOINT_URL", "").strip().rstrip("/")


def hetzner_object_storage_available() -> bool:
    """True, wenn alle Zugangsdaten gesetzt sind (ohne Netzwerkcheck)."""
    return bool(
        HETZNER_ACCESS_KEY
        and HETZNER_SECRET_KEY
        and HETZNER_BUCKET_NAME
        and HETZNER_ENDPOINT_URL
    )


def _public_url_prefix() -> str | None:
    if not hetzner_object_storage_available():
        return None
    parsed = urlparse(HETZNER_ENDPOINT_URL)
    scheme = parsed.scheme or "https"
    host = parsed.netloc
    if not host:
        return None
    return f"{scheme}://{HETZNER_BUCKET_NAME}.{host}/"


def _guess_content_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".png"):
        return "image/png"
    return "image/jpeg"


@lru_cache(maxsize=1)
def _s3_client():
    import boto3
    from botocore.config import Config

    cfg = Config(signature_version="s3v4")
    return boto3.client(
        "s3",
        endpoint_url=HETZNER_ENDPOINT_URL,
        aws_access_key_id=HETZNER_ACCESS_KEY,
        aws_secret_access_key=HETZNER_SECRET_KEY,
        config=cfg,
    )


def upload_logo(file: BinaryIO, filename: str) -> str:
    """Lädt eine Bilddatei unter ``filename`` (Object-Key, z. B. ``provider-logos/<id>.jpg``).

    Gibt die öffentliche URL zurück (virtual-hosted-style: ``https://<bucket>.<endpoint-host>/<key>``).
    """
    prefix = _public_url_prefix()
    if not prefix:
        raise RuntimeError("Hetzner Object Storage ist nicht konfiguriert")

    key = filename.lstrip("/")
    body = file.read()
    client = _s3_client()
    extra = {
        "Bucket": HETZNER_BUCKET_NAME,
        "Key": key,
        "Body": body,
        "ContentType": _guess_content_type(key),
    }
    try:
        client.put_object(**extra, ACL="public-read")
    except Exception as first:
        logger.warning("put_object mit ACL public-read fehlgeschlagen, erneuter Versuch ohne ACL: %r", first)
        client.put_object(**extra)

    return f"{prefix}{key}"


def delete_logo(filename: str) -> None:
    """Entfernt das Objekt mit Key ``filename`` (z. B. ``provider-logos/uuid.jpg``)."""
    if not hetzner_object_storage_available():
        return
    key = filename.lstrip("/")
    if not key:
        return
    try:
        _s3_client().delete_object(Bucket=HETZNER_BUCKET_NAME, Key=key)
    except Exception:
        logger.exception("delete_logo fehlgeschlagen key=%s", key)


def delete_managed_logo_by_public_url(url: str | None) -> None:
    """Löscht das Objekt nur, wenn ``url`` zum konfigurierten Bucket passt."""
    if not url or not hetzner_object_storage_available():
        return
    prefix = _public_url_prefix()
    if not prefix:
        return
    clean = url.split("?", 1)[0].strip()
    if not clean.startswith(prefix):
        return
    key = clean[len(prefix) :].lstrip("/")
    if key:
        delete_logo(key)
