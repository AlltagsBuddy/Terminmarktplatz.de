import requests


def test_robots_txt(app_base_url: str) -> None:
    response = requests.get(f"{app_base_url}/robots.txt", timeout=20)
    assert response.status_code == 200
    body = response.text.lower()
    assert "user-agent" in body


def test_sitemap_xml(app_base_url: str) -> None:
    response = requests.get(f"{app_base_url}/sitemap.xml", timeout=20)
    assert response.status_code == 200
    body = response.text.lower()
    assert "<urlset" in body


def test_main_stylesheet_is_reachable(app_base_url: str) -> None:
    response = requests.get(f"{app_base_url}/static/style.css", timeout=20)
    assert response.status_code == 200
    assert "body" in response.text.lower()
