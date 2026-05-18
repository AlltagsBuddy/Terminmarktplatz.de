"""Tests für Hetzner Object Storage (services.storage)."""

from __future__ import annotations

import io
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")

from services.storage import (
    HetznerStorageConfig,
    StorageError,
    configure_storage,
    hetzner_object_storage_available,
    public_url_for_key,
    upload_logo,
)


_HETZNER_ENV_KEYS = (
    "HETZNER_ACCESS_KEY",
    "HETZNER_SECRET_KEY",
    "HETZNER_BUCKET_NAME",
    "HETZNER_ENDPOINT_URL",
    "HETZNER_PUBLIC_URL",
    "HETZNER_REGION",
)


@pytest.fixture(autouse=True)
def _reset_storage_config(monkeypatch):
    for key in _HETZNER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    configure_storage(None)
    yield
    for key in _HETZNER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    configure_storage(None)


def test_hetzner_available_reads_from_environ():
    os.environ["HETZNER_ACCESS_KEY"] = "ak"
    os.environ["HETZNER_SECRET_KEY"] = "sk"
    os.environ["HETZNER_BUCKET_NAME"] = "bucket"
    os.environ["HETZNER_ENDPOINT_URL"] = "https://nbg1.your-objectstorage.com"
    configure_storage()
    assert hetzner_object_storage_available() is True


def test_public_url_path_style():
    configure_storage(
        HetznerStorageConfig(
            access_key="ak",
            secret_key="sk",
            bucket_name="my-bucket",
            endpoint_url="https://nbg1.your-objectstorage.com",
        )
    )
    url = public_url_for_key("provider-logos/abc.jpg")
    assert url == "https://nbg1.your-objectstorage.com/my-bucket/provider-logos/abc.jpg"


def test_public_url_custom_base():
    configure_storage(
        HetznerStorageConfig(
            access_key="ak",
            secret_key="sk",
            bucket_name="my-bucket",
            endpoint_url="https://nbg1.your-objectstorage.com",
            public_base_url="https://cdn.example.com",
        )
    )
    url = public_url_for_key("provider-logos/abc.jpg")
    assert url == "https://cdn.example.com/provider-logos/abc.jpg"


def test_upload_logo_returns_public_url():
    configure_storage(
        HetznerStorageConfig(
            access_key="ak",
            secret_key="sk",
            bucket_name="b",
            endpoint_url="https://nbg1.your-objectstorage.com",
        )
    )
    mock_client = MagicMock()
    with patch("services.storage._s3_client", return_value=mock_client):
        url = upload_logo(io.BytesIO(b"jpeg-bytes"), "provider-logos/p1.jpg")
    assert url.endswith("/provider-logos/p1.jpg")
    mock_client.put_object.assert_called()
    call_kw = mock_client.put_object.call_args.kwargs
    assert call_kw["Bucket"] == "b"
    assert call_kw["Key"] == "provider-logos/p1.jpg"
    assert call_kw["ContentType"] == "image/jpeg"


def test_upload_logo_empty_file_raises():
    configure_storage(
        HetznerStorageConfig(
            access_key="ak",
            secret_key="sk",
            bucket_name="b",
            endpoint_url="https://nbg1.your-objectstorage.com",
        )
    )
    with pytest.raises(StorageError, match="Leere Datei"):
        upload_logo(io.BytesIO(b""), "provider-logos/x.jpg")


def test_boto3_client_uses_hetzner_signature_and_region():
    configure_storage(
        HetznerStorageConfig(
            access_key="ak",
            secret_key="sk",
            bucket_name="b",
            endpoint_url="https://nbg1.your-objectstorage.com",
            region_name="eu-central-1",
        )
    )
    from services.storage import _clear_s3_client_cache, _require_config, _s3_client

    _clear_s3_client_cache()
    with patch("boto3.client") as mock_client:
        mock_client.return_value = MagicMock()
        _s3_client(_require_config())
    mock_client.assert_called_once()
    kwargs = mock_client.call_args.kwargs
    assert kwargs["endpoint_url"] == "https://nbg1.your-objectstorage.com"
    assert kwargs["region_name"] == "eu-central-1"
    assert kwargs["config"].signature_version == "s3v4"
    assert kwargs["config"].s3["addressing_style"] == "path"


def test_region_defaults_to_location_from_endpoint():
    configure_storage(
        HetznerStorageConfig(
            access_key="ak",
            secret_key="sk",
            bucket_name="b",
            endpoint_url="https://fsn1.your-objectstorage.com",
        )
    )
    from services.storage import _region_name, _require_config

    assert _region_name(_require_config()) == "fsn1"
