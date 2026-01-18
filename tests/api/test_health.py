from tests.api.http_client import HttpClient


def test_api_health(app_base_url: str) -> None:
    client = HttpClient()
    response = client.get(f"{app_base_url}/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
