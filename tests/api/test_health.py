import requests


def test_api_health(app_base_url: str) -> None:
    response = requests.get(f"{app_base_url}/api/health", timeout=20)
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
