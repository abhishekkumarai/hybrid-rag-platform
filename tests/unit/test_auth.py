"""Local accounts, the auth cookie, the login throttle and the CSRF header check (IRA-33)."""

import pytest
from fastapi.testclient import TestClient

from services.gateway import api
from services.identity.auth import AUTH_COOKIE, LoginRateLimiter
from services.identity.passwords import hash_password, verify_password

H = {"X-RI-Client": "web"}


@pytest.fixture
def client(real_auth):
    return TestClient(api.app)


def _signup(client, email="ana@example.com", password="correct horse"):
    return client.post("/api/v1/auth/signup", json={"email": email, "password": password}, headers=H)


def test_password_hash_round_trip():
    encoded = hash_password("s3cret-pass")
    assert encoded.startswith("scrypt$") and "s3cret-pass" not in encoded
    assert verify_password("s3cret-pass", encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password("s3cret-pass", "garbage")


def test_signup_sets_httponly_cookie_and_me_works(client):
    r = _signup(client)
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "ana@example.com"
    assert r.json()["user"]["is_admin"] is False
    set_cookie = r.headers["set-cookie"]
    assert AUTH_COOKIE in set_cookie and "HttpOnly" in set_cookie and "samesite=lax" in set_cookie.lower()

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["user"]["email"] == "ana@example.com"


def test_token_is_stored_hashed(client, identity):
    _signup(client)
    token = client.cookies.get(AUTH_COOKIE)
    assert token and token not in identity.auth_sessions


def test_logout_ends_the_session(client):
    _signup(client)
    assert client.post("/api/v1/auth/logout", headers=H).status_code == 200
    client.cookies.clear()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_duplicate_signup_is_rejected_case_insensitively(client):
    assert _signup(client).status_code == 200
    assert _signup(client, email="ANA@example.com").status_code == 409


def test_login_accepts_right_password_only(client):
    _signup(client)
    client.cookies.clear()
    bad = client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "nope"}, headers=H)
    assert bad.status_code == 401
    unknown = client.post("/api/v1/auth/login", json={"email": "who@example.com", "password": "nope"}, headers=H)
    assert unknown.status_code == 401 and unknown.json()["detail"] == bad.json()["detail"]
    ok = client.post("/api/v1/auth/login", json={"email": "Ana@Example.com", "password": "correct horse"}, headers=H)
    assert ok.status_code == 200 and client.get("/api/v1/auth/me").status_code == 200


def test_login_is_throttled_after_repeated_failures(client, monkeypatch):
    monkeypatch.setattr(api, "login_limiter", LoginRateLimiter(max_attempts=3, window_s=60))
    _signup(client)
    body = {"email": "ana@example.com", "password": "nope"}
    codes = [client.post("/api/v1/auth/login", json=body, headers=H).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    # Even the right password is refused while the window lasts
    body["password"] = "correct horse"
    assert client.post("/api/v1/auth/login", json=body, headers=H).status_code == 429


def test_signup_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(api.settings.auth, "allow_signup", False)
    assert _signup(client).status_code == 403


def test_private_routes_need_sign_in_public_ones_dont(client):
    assert client.get("/api/v1/sessions").status_code == 401
    assert client.get("/api/v1/documents").status_code == 401
    assert client.get("/api/v1/preview?doc_id=x").status_code == 401
    assert client.get("/").status_code == 200
    assert client.get("/s/some-token").status_code == 200
    assert client.get("/api/v1/public/shares/unknown-token").status_code == 404


def test_state_changing_requests_need_the_client_header_or_same_origin(client):
    _signup(client)
    assert client.post("/api/v1/sessions", json={}).status_code == 403
    assert client.post("/api/v1/sessions", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/v1/sessions", json={}, headers={"Origin": "http://testserver"}).status_code == 200
    assert client.post("/api/v1/sessions", json={}, headers=H).status_code == 200


def test_admin_endpoints_refuse_regular_users(client):
    _signup(client)
    assert client.post("/api/v1/web/sync", json={}, headers=H).status_code == 403
    assert client.post("/api/v1/eval/run", headers=H).status_code == 403
    assert client.get("/api/v1/queue/dlq").status_code == 403
    assert client.get("/api/v1/metrics").status_code == 403
