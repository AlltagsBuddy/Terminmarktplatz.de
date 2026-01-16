import pytest
import requests


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/agb",
        "/anbieter",
        "/hilfe",
        "/impressum",
        "/kontakt",
        "/login",
        "/suchende",
        "/preise",
        "/datenschutz",
        "/widerruf",
        "/cookie-einstellungen",
    ],
)
def test_pages_are_reachable(app_base_url: str, path: str) -> None:
    response = requests.get(f"{app_base_url}{path}", timeout=20)
    assert response.status_code == 200
    assert "<html" in response.text.lower()
