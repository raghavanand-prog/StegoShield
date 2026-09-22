"""Authentication tests. Every Supabase HTTP call is mocked (via
monkeypatching `requests.request`/`requests.post`/`requests.patch`) - no
test here makes a real network call, consistent with the rest of the
suite running fully offline. See tests/conftest.py: TestingConfig sets
dummy SUPABASE_URL/ANON_KEY so the auth routes are reachable at all.
"""
from __future__ import annotations

import re

import pytest


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "csrf token not found in rendered page"
    return match.group(1)


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class TestPublicRoutesUnaffected:
    """Guests must be able to use every existing StegoShield feature with
    no login wall - the core regression check for this whole change."""

    def test_homepage_loads_for_guest(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_encode_page_loads_for_guest(self, client):
        assert client.get("/encode").status_code == 200

    def test_decode_page_loads_for_guest(self, client):
        assert client.get("/decode").status_code == 200

    def test_steganalysis_page_loads_for_guest(self, client):
        assert client.get("/steganalysis").status_code == 200

    def test_image_analysis_page_loads_for_guest(self, client):
        assert client.get("/image-analysis").status_code == 200

    def test_login_link_present_for_guest(self, client):
        resp = client.get("/")
        assert b'href="/login"' in resp.data


class TestProtectedRoutesRequireLogin:
    @pytest.mark.parametrize("path", ["/dashboard", "/account", "/history"])
    def test_redirects_anonymous_to_login(self, client, path):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_history_detail_redirects_anonymous_to_login(self, client):
        resp = client.get("/history/00000000-0000-0000-0000-000000000000", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


class TestSignupValidation:
    def _get_csrf(self, client):
        return _extract_csrf(client.get("/signup").get_data(as_text=True))

    def test_password_mismatch_rejected(self, client):
        csrf = self._get_csrf(client)
        resp = client.post("/signup", data={
            "csrf_token": csrf, "email": "a@example.com",
            "password": "goodpass1", "confirm_password": "different1",
        })
        assert resp.status_code == 400
        assert b"do not match" in resp.data

    def test_weak_password_rejected(self, client):
        csrf = self._get_csrf(client)
        resp = client.post("/signup", data={
            "csrf_token": csrf, "email": "a@example.com",
            "password": "short", "confirm_password": "short",
        })
        assert resp.status_code == 400
        assert b"8 characters" in resp.data

    def test_invalid_email_rejected(self, client):
        csrf = self._get_csrf(client)
        resp = client.post("/signup", data={
            "csrf_token": csrf, "email": "not-an-email",
            "password": "goodpass1", "confirm_password": "goodpass1",
        })
        assert resp.status_code == 400
        assert b"valid email" in resp.data

    def test_missing_csrf_rejected(self, client):
        resp = client.post("/signup", data={
            "csrf_token": "wrong-token", "email": "a@example.com",
            "password": "goodpass1", "confirm_password": "goodpass1",
        })
        assert resp.status_code == 400

    def test_duplicate_email_shows_safe_message(self, client, monkeypatch):
        csrf = self._get_csrf(client)

        def fake_request(method, url, **kwargs):
            assert "/auth/v1/signup" in url
            return _FakeResponse(422, {"msg": "User already registered"})

        monkeypatch.setattr("app.auth.supabase_client.requests.request", fake_request)
        resp = client.post("/signup", data={
            "csrf_token": csrf, "email": "dup@example.com",
            "password": "goodpass1", "confirm_password": "goodpass1",
        })
        assert resp.status_code == 400
        assert b"already exists" in resp.data
        # never leak the raw provider error string to the page
        assert b"User already registered" not in resp.data


class TestLoginFlow:
    def _get_csrf(self, client):
        return _extract_csrf(client.get("/login").get_data(as_text=True))

    def test_invalid_credentials_rejected_with_safe_message(self, client, monkeypatch):
        csrf = self._get_csrf(client)

        def fake_request(method, url, **kwargs):
            return _FakeResponse(400, {"error_description": "Invalid login credentials"})

        monkeypatch.setattr("app.auth.supabase_client.requests.request", fake_request)
        resp = client.post("/login", data={"csrf_token": csrf, "email": "a@example.com", "password": "wrong"})
        assert resp.status_code == 401
        assert b"Incorrect email or password" in resp.data

    def test_successful_login_sets_session_and_redirects(self, client, monkeypatch):
        csrf = self._get_csrf(client)

        def fake_request(method, url, **kwargs):
            return _FakeResponse(200, {
                "access_token": "fake-access-token",
                "refresh_token": "fake-refresh-token",
                "expires_in": 3600,
                "user": {"id": "11111111-1111-1111-1111-111111111111", "email": "a@example.com"},
            })

        monkeypatch.setattr("app.auth.supabase_client.requests.request", fake_request)
        monkeypatch.setattr("app.auth.supabase_client.requests.patch", lambda *a, **k: _FakeResponse(204, {}))

        resp = client.post("/login", data={"csrf_token": csrf, "email": "a@example.com", "password": "goodpass1"}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/dashboard")

    def test_logged_in_user_can_reach_dashboard(self, client, monkeypatch):
        csrf = self._get_csrf(client)

        def fake_request(method, url, **kwargs):
            if "/auth/v1/token" in url:
                return _FakeResponse(200, {
                    "access_token": "fake-access-token",
                    "refresh_token": "fake-refresh-token",
                    "expires_in": 3600,
                    "user": {"id": "11111111-1111-1111-1111-111111111111", "email": "a@example.com"},
                })
            if "/rest/v1/profiles" in url:
                return _FakeResponse(200, [])
            if "/rest/v1/analysis_history" in url:
                return _FakeResponse(200, [])
            raise AssertionError(f"unexpected URL {url}")

        monkeypatch.setattr("app.auth.supabase_client.requests.request", fake_request)
        monkeypatch.setattr("app.auth.supabase_client.requests.patch", lambda *a, **k: _FakeResponse(204, {}))

        client.post("/login", data={"csrf_token": csrf, "email": "a@example.com", "password": "goodpass1"})
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert b"a@example.com" in resp.data

    def test_logout_clears_session(self, client, monkeypatch):
        csrf = self._get_csrf(client)

        def fake_request(method, url, **kwargs):
            if "/auth/v1/token" in url:
                return _FakeResponse(200, {
                    "access_token": "fake-access-token",
                    "refresh_token": "fake-refresh-token",
                    "expires_in": 3600,
                    "user": {"id": "11111111-1111-1111-1111-111111111111", "email": "a@example.com"},
                })
            if "/rest/v1/profiles" in url or "/rest/v1/analysis_history" in url:
                return _FakeResponse(200, [])
            raise AssertionError(f"unexpected URL {url}")

        monkeypatch.setattr("app.auth.supabase_client.requests.request", fake_request)
        monkeypatch.setattr("app.auth.supabase_client.requests.patch", lambda *a, **k: _FakeResponse(204, {}))
        monkeypatch.setattr("app.auth.supabase_client.requests.post", lambda *a, **k: _FakeResponse(204, {}))

        client.post("/login", data={"csrf_token": csrf, "email": "a@example.com", "password": "goodpass1"})
        assert client.get("/dashboard").status_code == 200

        # A logout with no/wrong CSRF token must not clear the session.
        client.post("/logout", data={"csrf_token": "wrong-token"})
        assert client.get("/dashboard").status_code == 200

        client.post("/logout", data={"csrf_token": csrf})
        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


class TestHistoryIsolation:
    def test_missing_or_other_users_record_returns_404(self, client, monkeypatch):
        csrf = _extract_csrf(client.get("/login").get_data(as_text=True))

        def fake_request(method, url, **kwargs):
            if "/auth/v1/token" in url:
                return _FakeResponse(200, {
                    "access_token": "fake-access-token",
                    "refresh_token": "fake-refresh-token",
                    "expires_in": 3600,
                    "user": {"id": "11111111-1111-1111-1111-111111111111", "email": "a@example.com"},
                })
            if "/rest/v1/analysis_history" in url:
                # RLS returns zero rows for a record that isn't this
                # user's - exactly like "doesn't exist".
                return _FakeResponse(200, [])
            raise AssertionError(f"unexpected URL {url}")

        monkeypatch.setattr("app.auth.supabase_client.requests.request", fake_request)
        monkeypatch.setattr("app.auth.supabase_client.requests.patch", lambda *a, **k: _FakeResponse(204, {}))

        client.post("/login", data={"csrf_token": csrf, "email": "a@example.com", "password": "goodpass1"})
        resp = client.get("/history/99999999-9999-9999-9999-999999999999")
        assert resp.status_code == 404
