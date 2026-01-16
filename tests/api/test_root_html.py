import requests


def test_root_is_reachable(app_base_url: str) -> None:
    response = requests.get(app_base_url, timeout=20)
    assert response.status_code == 200
    assert "Terminmarktplatz" in response.text
