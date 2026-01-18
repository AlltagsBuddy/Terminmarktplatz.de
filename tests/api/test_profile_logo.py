import io
import os
import tempfile

import pytest
from PIL import Image
from sqlalchemy.orm import Session


_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("FRONTEND_URL", "http://testserver")

import app as app_module
from models import Base, Provider


@pytest.fixture(scope="module")
def test_client():
    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    return app_module.app.test_client()


@pytest.fixture(scope="module")
def provider_id():
    with Session(app_module.engine) as s:
        provider = Provider(
            email="logo-test@example.com",
            pw_hash="test",
            company_name="Logo GmbH",
            branch="Friseur",
            street="Teststrasse 1",
            zip="12345",
            city="Teststadt",
            phone="1234567",
            status="approved",
        )
        s.add(provider)
        s.commit()
        return provider.id


def _auth_headers(provider_id: str) -> dict[str, str]:
    access, _ = app_module.issue_tokens(provider_id, False)
    return {"Authorization": f"Bearer {access}"}


def _jpeg_under_limit() -> bytes:
    img = Image.new("RGB", (app_module.LOGO_SIZE_PX, app_module.LOGO_SIZE_PX), color=(120, 140, 160))
    for quality in (60, 50, 40, 30, 20, 10):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= app_module.LOGO_MAX_BYTES:
            return data
    return data


def test_logo_upload_requires_consent(test_client, provider_id):
    payload = {"consent_logo_display": True}
    res = test_client.put("/me", json=payload, headers=_auth_headers(provider_id))
    assert res.status_code == 200

    data = _jpeg_under_limit()
    res = test_client.post(
        "/me/logo",
        data={"logo": (io.BytesIO(data), "logo.jpg")},
        content_type="multipart/form-data",
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "logo_consent_required"


def test_logo_upload_and_delete_flow(test_client, provider_id):
    data = _jpeg_under_limit()
    res = test_client.post(
        "/me/logo",
        data={"logo": (io.BytesIO(data), "logo.jpg"), "consent_logo_display": "true"},
        content_type="multipart/form-data",
        headers=_auth_headers(provider_id),
    )
    assert res.status_code == 200
    body = res.get_json()
    assert "logo_url" in body and "/static/uploads/provider-logos/" in body["logo_url"]

    res_me = test_client.get("/me", headers=_auth_headers(provider_id))
    assert res_me.status_code == 200
    me = res_me.get_json()
    assert me["consent_logo_display"] is True
    assert me["logo_url"] is not None

    res_del = test_client.delete("/me/logo", headers=_auth_headers(provider_id))
    assert res_del.status_code == 200

    res_me2 = test_client.get("/me", headers=_auth_headers(provider_id))
    me2 = res_me2.get_json()
    assert me2["consent_logo_display"] is False
    assert me2["logo_url"] is None
