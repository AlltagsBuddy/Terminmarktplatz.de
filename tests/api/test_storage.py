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


@pytest.fixture(autouse=True)
def _reset_storage_config():
    configure_storage(None)
    yield
    configure_storage(None)


def test_hetzner_available_reads_from_environ():
    os.environ["HETZNER_ACCESS_KEY"] = "ak"
    os.environ["HETZNER_SECRET_KEY"] = "sk"
    os.environ["HETZNER_BUCKET_NAME"] = "bucket"
    os.environ["HETZNER_ENDPOINT_URL"] = "https://nbg1.your-objectstorage.com"
    configure_storage()
    assert hetzner_object_storage_available() is True


def test_public_url_virtual_hosted_style():
    configure_storage(
        HetznerStorageConfig(
            access_key="ak",
            secret_key="sk",
            bucket_name="my-bucket",
            endpoint_url="https://nbg1.your-objectstorage.com",
        )
    )
    url = public_url_for_key("provider-logos/abc.jpg")
    assert url == "https://my-bucket.nbg1.your-objectstorage.com/provider-logos/abc.jpg"


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
