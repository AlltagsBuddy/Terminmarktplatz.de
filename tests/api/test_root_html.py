from tests.api.http_client import HttpClient


def test_root_is_reachable(app_base_url: str) -> None:
    client = HttpClient()
    response = client.get(app_base_url)
    assert response.status_code == 200
    assert "Terminmarktplatz" in response.text
