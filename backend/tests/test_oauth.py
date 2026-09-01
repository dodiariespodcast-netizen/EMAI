import pytest

from app.services.auth.oauth import OAuthIdentityInfo, OAuthVerificationError
from tests.helpers import auth_headers


def _patch_verify(monkeypatch, info: OAuthIdentityInfo | Exception):
    def fake_verify(provider: str, id_token: str):
        if isinstance(info, Exception):
            raise info
        return info

    monkeypatch.setattr("app.api.routes.auth.verify_id_token", fake_verify)


def test_oauth_signup_creates_org_and_links_identity(client, monkeypatch):
    _patch_verify(
        monkeypatch,
        OAuthIdentityInfo(provider="google", subject="google-sub-1", email="new.doc@gmail.com", email_verified=True, name="New Doc"),
    )
    resp = client.post(
        "/auth/oauth/signup",
        json={"provider": "google", "id_token": "fake", "org_name": "Gmail EM", "org_slug": "gmail-em"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["email"] == "new.doc@gmail.com"
    assert body["user"]["role"] == "owner"

    identities = client.get("/auth/oauth/identities", headers=auth_headers(body["access_token"]))
    assert identities.status_code == 200
    assert identities.json()[0]["provider"] == "google"


def test_oauth_login_with_linked_identity(client, monkeypatch):
    identity = OAuthIdentityInfo(provider="google", subject="google-sub-2", email="returning.doc@gmail.com", email_verified=True, name="Returning Doc")
    _patch_verify(monkeypatch, identity)

    signup = client.post(
        "/auth/oauth/signup",
        json={"provider": "google", "id_token": "fake", "org_name": "Return EM", "org_slug": "return-em"},
    )
    assert signup.status_code == 201

    login = client.post("/auth/oauth/login", json={"provider": "google", "id_token": "fake"})
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "returning.doc@gmail.com"


def test_oauth_login_auto_links_existing_password_account_by_verified_email(client, monkeypatch):
    signup = client.post(
        "/auth/signup",
        json={"org_name": "Linkable EM", "org_slug": "linkable-em", "email": "linkme@gmail.com", "password": "supersecret1"},
    )
    assert signup.status_code == 201

    _patch_verify(
        monkeypatch,
        OAuthIdentityInfo(provider="google", subject="google-sub-3", email="linkme@gmail.com", email_verified=True, name="Link Me"),
    )
    login = client.post("/auth/oauth/login", json={"provider": "google", "id_token": "fake"})
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "linkme@gmail.com"

    identities = client.get("/auth/oauth/identities", headers=auth_headers(login.json()["access_token"]))
    assert len(identities.json()) == 1


def test_oauth_login_unknown_identity_404s(client, monkeypatch):
    _patch_verify(
        monkeypatch,
        OAuthIdentityInfo(provider="microsoft", subject="ms-sub-1", email="nobody@outlook.com", email_verified=True, name="Nobody"),
    )
    resp = client.post("/auth/oauth/login", json={"provider": "microsoft", "id_token": "fake"})
    assert resp.status_code == 404


def test_oauth_verification_failure_returns_400(client, monkeypatch):
    _patch_verify(monkeypatch, OAuthVerificationError("bad signature"))
    resp = client.post("/auth/oauth/login", json={"provider": "google", "id_token": "garbage"})
    assert resp.status_code == 400


def test_link_and_unlink_oauth_identity(client, monkeypatch):
    signup = client.post(
        "/auth/signup",
        json={"org_name": "LinkFlow EM", "org_slug": "linkflow-em", "email": "flow@example.com", "password": "supersecret1"},
    )
    headers = auth_headers(signup.json()["access_token"])

    _patch_verify(
        monkeypatch,
        OAuthIdentityInfo(provider="microsoft", subject="ms-sub-2", email="flow@example.com", email_verified=True, name="Flow"),
    )
    link = client.post("/auth/oauth/link", json={"provider": "microsoft", "id_token": "fake"}, headers=headers)
    assert link.status_code == 201, link.text
    identity_id = link.json()["id"]

    # Has a password AND the linked identity -> unlink is allowed.
    unlink = client.delete(f"/auth/oauth/identities/{identity_id}", headers=headers)
    assert unlink.status_code == 204


def test_cannot_unlink_only_sign_in_method(client, monkeypatch):
    _patch_verify(
        monkeypatch,
        OAuthIdentityInfo(provider="google", subject="google-sub-4", email="onlyoauth@gmail.com", email_verified=True, name="Only OAuth"),
    )
    signup = client.post(
        "/auth/oauth/signup",
        json={"provider": "google", "id_token": "fake", "org_name": "OnlyOAuth EM", "org_slug": "onlyoauth-em"},
    )
    headers = auth_headers(signup.json()["access_token"])
    identities = client.get("/auth/oauth/identities", headers=headers).json()
    assert len(identities) == 1

    resp = client.delete(f"/auth/oauth/identities/{identities[0]['id']}", headers=headers)
    assert resp.status_code == 400


def test_change_password_for_oauth_only_account(client, monkeypatch):
    _patch_verify(
        monkeypatch,
        OAuthIdentityInfo(provider="google", subject="google-sub-5", email="setpw@gmail.com", email_verified=True, name="Set PW"),
    )
    signup = client.post(
        "/auth/oauth/signup",
        json={"provider": "google", "id_token": "fake", "org_name": "SetPW EM", "org_slug": "setpw-em"},
    )
    headers = auth_headers(signup.json()["access_token"])

    change = client.post("/auth/change-password", json={"new_password": "brandnewpassword1"}, headers=headers)
    assert change.status_code == 200

    login = client.post("/auth/login", data={"username": "setpw@gmail.com", "password": "brandnewpassword1"})
    assert login.status_code == 200
