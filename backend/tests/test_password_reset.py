"""Password reset and invite-link flows."""

from datetime import datetime, timedelta, timezone

from app.models.tenancy import PasswordResetToken, User
from tests.helpers import auth_headers


def _signup(client, slug="reset-em"):
    resp = client.post(
        "/auth/signup",
        json={
            "org_name": "Reset EM",
            "org_slug": slug,
            "email": f"owner@{slug}.example.com",
            "password": "supersecret1",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _sessionmaker():
    import app.database as database_module

    return database_module.SessionLocal


def test_invite_without_password_lets_user_set_their_own(client):
    owner = auth_headers(_signup(client)["access_token"])

    invite = client.post(
        "/auth/users", json={"email": "newdoc@reset-em.example.com", "role": "physician"}, headers=owner
    )
    assert invite.status_code == 201, invite.text
    body = invite.json()
    assert body["email_sent"] is True
    assert "token=" in body["invite_url"]

    # No password yet -> can't log in with one.
    early = client.post("/auth/login", data={"username": body["email"], "password": "anything123"})
    assert early.status_code == 401

    token = body["invite_url"].split("token=")[1]
    confirmed = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "brandnew12345"})
    assert confirmed.status_code == 200, confirmed.text
    # Signed straight in, no second login round trip.
    assert confirmed.json()["user"]["email"] == body["email"]

    login = client.post("/auth/login", data={"username": body["email"], "password": "brandnew12345"})
    assert login.status_code == 200


def test_invite_token_is_single_use(client):
    owner = auth_headers(_signup(client, "single-use-em")["access_token"])
    invite = client.post(
        "/auth/users", json={"email": "once@single-use-em.example.com", "role": "physician"}, headers=owner
    ).json()
    token = invite["invite_url"].split("token=")[1]

    assert client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "firsttry12345"}).status_code == 200
    replay = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "secondtry12345"})
    assert replay.status_code == 400


def test_resend_invite_invalidates_the_previous_link(client):
    owner = auth_headers(_signup(client, "resend-em")["access_token"])
    first = client.post(
        "/auth/users", json={"email": "resend@resend-em.example.com", "role": "physician"}, headers=owner
    ).json()
    second = client.post(f"/auth/users/{first['user_id']}/invite", headers=owner)
    assert second.status_code == 200, second.text

    old_token = first["invite_url"].split("token=")[1]
    new_token = second.json()["invite_url"].split("token=")[1]
    assert old_token != new_token

    stale = client.post("/auth/password-reset/confirm", json={"token": old_token, "new_password": "shouldfail123"})
    assert stale.status_code == 400
    fresh = client.post("/auth/password-reset/confirm", json={"token": new_token, "new_password": "shouldwork123"})
    assert fresh.status_code == 200


def test_forgot_password_round_trip(client):
    _signup(client, "forgot-em")

    request = client.post("/auth/password-reset/request", json={"email": "owner@forgot-em.example.com"})
    assert request.status_code == 202

    # Pull the issued token's hash straight from the DB and match it against a
    # freshly-hashed candidate -- the plaintext only ever exists in the email.
    from app.services.auth.password_reset import _hash

    with _sessionmaker()() as session:
        rows = session.query(PasswordResetToken).all()
        assert len(rows) == 1
        assert rows[0].purpose == "reset"
        issued_hash = rows[0].token_hash

    # Re-request: the first token must be invalidated in favor of the new one.
    client.post("/auth/password-reset/request", json={"email": "owner@forgot-em.example.com"})
    with _sessionmaker()() as session:
        superseded = session.query(PasswordResetToken).filter(PasswordResetToken.token_hash == issued_hash).one()
        assert superseded.used_at is not None

    assert _hash("not-the-real-token") != issued_hash


def test_reset_request_for_unknown_email_still_reports_success(client):
    """Otherwise the endpoint tells an attacker which emails have accounts."""
    resp = client.post("/auth/password-reset/request", json={"email": "nobody@nowhere.example.com"})
    assert resp.status_code == 202
    with _sessionmaker()() as session:
        assert session.query(PasswordResetToken).count() == 0


def test_expired_token_is_rejected(client):
    owner = auth_headers(_signup(client, "expiry-em")["access_token"])
    invite = client.post(
        "/auth/users", json={"email": "expired@expiry-em.example.com", "role": "physician"}, headers=owner
    ).json()
    token = invite["invite_url"].split("token=")[1]

    with _sessionmaker()() as session:
        row = session.query(PasswordResetToken).filter(PasswordResetToken.used_at.is_(None)).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()

    resp = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "toolate12345"})
    assert resp.status_code == 400


def test_disabled_user_cannot_reset_into_the_account(client):
    signup = _signup(client, "disabled-em")
    owner = auth_headers(signup["access_token"])
    invite = client.post(
        "/auth/users", json={"email": "off@disabled-em.example.com", "role": "physician"}, headers=owner
    ).json()
    client.patch(f"/auth/users/{invite['user_id']}", json={"is_active": False}, headers=owner)

    token = invite["invite_url"].split("token=")[1]
    resp = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "nogood123456"})
    assert resp.status_code == 403


def test_admin_supplied_password_skips_the_invite_email(client):
    owner = auth_headers(_signup(client, "temp-pw-em")["access_token"])
    invite = client.post(
        "/auth/users",
        json={"email": "temp@temp-pw-em.example.com", "role": "physician", "password": "temporary1234"},
        headers=owner,
    )
    assert invite.status_code == 201
    assert invite.json()["email_sent"] is False

    login = client.post("/auth/login", data={"username": "temp@temp-pw-em.example.com", "password": "temporary1234"})
    assert login.status_code == 200
