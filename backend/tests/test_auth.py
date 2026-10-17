from app.core import auth
from app.core.config import settings


def test_case_api_requires_authenticated_advocate(client) -> None:
    client.cookies.clear()

    responses = [
        client.get("/api/v1/cases"),
        client.get("/api/v1/cases/00000000-0000-0000-0000-000000000001/analysis/config"),
        client.get("/api/v1/cases/00000000-0000-0000-0000-000000000001/summary/latest"),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401]


def test_login_sets_httponly_samesite_session_and_logout_clears_it(client) -> None:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "advocate@example.test", "password": "A-Strong-Test-Password-2026!"},
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=strict" in cookie_header
    assert "max-age=3600" in cookie_header
    assert client.get("/api/v1/auth/me").json() == {"email": "advocate@example.test"}

    logout_response = client.post("/api/v1/auth/logout", headers={"Origin": "http://localhost:3000"})
    assert logout_response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_rejects_bad_credentials_and_cross_origin_requests(client) -> None:
    client.cookies.clear()
    bad_password = client.post(
        "/api/v1/auth/login",
        json={"email": "advocate@example.test", "password": "incorrect password"},
        headers={"Origin": "http://localhost:3000"},
    )
    forbidden_origin = client.post(
        "/api/v1/auth/login",
        json={"email": "advocate@example.test", "password": "A-Strong-Test-Password-2026!"},
        headers={"Origin": "https://attacker.example"},
    )

    assert bad_password.status_code == 401
    assert bad_password.json()["detail"] == "Email or password is incorrect."
    assert forbidden_origin.status_code == 403


def test_cookie_authenticated_mutations_require_an_allowed_origin(client) -> None:
    response = client.post(
        "/api/v1/cases",
        json={"title": "Blocked cross-site request"},
        headers={"Origin": "https://attacker.example"},
    )

    assert response.status_code == 403


def test_signed_sessions_expire_and_reject_tampering(client) -> None:
    token = auth.create_session("advocate@example.test", now=100)

    assert auth.session_email(token, now=101) == "advocate@example.test"
    assert auth.session_email(token, now=100 + 3600) is None
    assert auth.session_email(token + "x", now=101) is None


def test_login_rate_limit_blocks_repeated_failures(client) -> None:
    client.cookies.clear()
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "advocate@example.test", "password": "incorrect password"},
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.status_code == 401

    throttled = client.post(
        "/api/v1/auth/login",
        json={"email": "advocate@example.test", "password": "incorrect password"},
        headers={"Origin": "http://localhost:3000"},
    )

    assert throttled.status_code == 429
    assert throttled.headers["retry-after"] == "900"


def test_first_run_signup_creates_one_account_and_signs_advocate_in(client, monkeypatch) -> None:
    client.cookies.clear()
    monkeypatch.setattr(settings, "advocate_email", None)
    monkeypatch.setattr(settings, "advocate_password_hash", None)
    monkeypatch.setattr(settings, "session_secret", None)

    status_before = client.get("/api/v1/auth/setup-status")
    assert status_before.status_code == 200
    assert status_before.json()["signup_available"] is True

    created = client.post(
        "/api/v1/auth/register",
        json={"email": "first@example.test", "password": "A-Strong-First-Password-2026!"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert created.status_code == 201
    assert created.json() == {"email": "first@example.test"}
    assert client.get("/api/v1/auth/me").json() == {"email": "first@example.test"}

    status_after = client.get("/api/v1/auth/setup-status")
    assert status_after.json()["signup_available"] is False
    second_account = client.post(
        "/api/v1/auth/register",
        json={"email": "second@example.test", "password": "A-Strong-Second-Password-2026!"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert second_account.status_code == 409
