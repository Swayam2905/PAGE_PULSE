"""
Tests for Page Pulse's /api/audit endpoint.

httpx.AsyncClient is mocked throughout, so these tests never touch the
network. That keeps them fast and deterministic (no flakiness from a
real site being slow, down, or changing its markup).

Run with:
    pytest -v
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def make_mock_response(status_code=200, content_type="text/html", text=""):
    """Build a fake httpx.Response-like object for mocking client.get()."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.headers = {"content-type": content_type}
    mock_response.text = text
    return mock_response


def mock_async_client(get_return_value=None, get_side_effect=None):
    """
    Build a mock that stands in for `async with httpx.AsyncClient(...) as client`.
    Patches main.httpx.AsyncClient so audit_url() never hits the real network.
    """
    mock_client_instance = AsyncMock()
    if get_side_effect is not None:
        mock_client_instance.get.side_effect = get_side_effect
    else:
        mock_client_instance.get.return_value = get_return_value

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client_instance
    mock_client_cm.__aexit__.return_value = False

    mock_client_class = MagicMock(return_value=mock_client_cm)
    return mock_client_class


# ---------- Happy path ----------

def test_audit_happy_path_returns_full_report():
    """A normal HTML page should return every field, no error."""
    html = """
    <html>
      <head>
        <title>Test Page</title>
        <meta name="description" content="A page for testing.">
      </head>
      <body>
        <h1>Welcome</h1>
        <p>Some sample text with a handful of words in it.</p>
        <img src="a.png" alt="described image">
        <img src="b.png">
      </body>
    </html>
    """
    mock_response = make_mock_response(status_code=200, content_type="text/html; charset=utf-8", text=html)

    with patch("main.httpx.AsyncClient", mock_async_client(get_return_value=mock_response)):
        res = client.post("/api/audit", json={"url": "example.com"})

    assert res.status_code == 200
    data = res.json()
    assert data["url"] == "https://example.com"
    assert data["status_code"] == 200
    assert data["title"] == "Test Page"
    assert data["meta_description"] == "A page for testing."
    assert data["h1_count"] == 1
    assert data["total_images"] == 2
    assert data["images_missing_alt"] == 1
    assert data["word_count"] > 0
    assert data["error"] is None


def test_audit_adds_https_scheme_when_missing():
    """A bare domain like 'example.com' should be normalized to https://."""
    mock_response = make_mock_response(text="<html><title>X</title></html>")

    with patch("main.httpx.AsyncClient", mock_async_client(get_return_value=mock_response)):
        res = client.post("/api/audit", json={"url": "example.com"})

    assert res.status_code == 200
    assert res.json()["url"] == "https://example.com"


# ---------- Failure case 1: connection failure ----------

def test_audit_connection_error_returns_502():
    """An unreachable domain should return a clean 502, not a crash."""
    with patch("main.httpx.AsyncClient", mock_async_client(get_side_effect=httpx.ConnectError("boom"))):
        res = client.post("/api/audit", json={"url": "https://nonexistent-domain-xyz123.com"})

    assert res.status_code == 502
    assert "Could not connect" in res.json()["detail"]


# ---------- Failure case 2: timeout ----------

def test_audit_timeout_returns_408():
    """A slow/hanging server should return a clean 408, not hang forever."""
    with patch("main.httpx.AsyncClient", mock_async_client(get_side_effect=httpx.TimeoutException("boom"))):
        res = client.post("/api/audit", json={"url": "https://slow-site.com"})

    assert res.status_code == 408
    assert "timed out" in res.json()["detail"]


# ---------- Additional edge cases ----------

def test_audit_empty_url_returns_422():
    """An empty/whitespace URL should fail validation before any request is made."""
    res = client.post("/api/audit", json={"url": "   "})
    assert res.status_code == 422


def test_audit_non_html_response_returns_error_field_not_crash():
    """A JSON/plaintext response should come back as a 200 with `error` set."""
    mock_response = make_mock_response(status_code=200, content_type="application/json", text='{"a": 1}')

    with patch("main.httpx.AsyncClient", mock_async_client(get_return_value=mock_response)):
        res = client.post("/api/audit", json={"url": "https://api.example.com/data"})

    assert res.status_code == 200
    data = res.json()
    assert data["error"] is not None
    assert "not HTML" in data["error"]
    assert data["title"] is None


def test_audit_upstream_4xx_returns_error_field_with_status_and_time():
    """A page that itself 404s/403s should surface that status, not crash."""
    mock_response = make_mock_response(status_code=404, content_type="text/html", text="<html>Not Found</html>")

    with patch("main.httpx.AsyncClient", mock_async_client(get_return_value=mock_response)):
        res = client.post("/api/audit", json={"url": "https://example.com/missing"})

    assert res.status_code == 200
    data = res.json()
    assert data["status_code"] == 404
    assert data["error"] is not None


def test_health_check():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}