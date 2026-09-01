from tests.helpers import auth_headers


def test_audit_log_records_key_actions(client):
    signup = client.post(
        "/auth/signup",
        json={"org_name": "Audit EM", "org_slug": "audit-em", "email": "owner@audit.example.com", "password": "supersecret1"},
    )
    owner = auth_headers(signup.json()["access_token"])

    client.post(
        "/physicians", json={"first_name": "A", "last_name": "B", "email": "ab@audit.example.com"}, headers=owner
    )

    log = client.get("/audit-log", headers=owner)
    assert log.status_code == 200
    actions = [entry["action"] for entry in log.json()]
    assert "org.signup" in actions


def test_audit_log_requires_scheduler_role(client):
    signup = client.post(
        "/auth/signup",
        json={"org_name": "Audit2 EM", "org_slug": "audit2-em", "email": "owner@audit2.example.com", "password": "supersecret1"},
    )
    owner = auth_headers(signup.json()["access_token"])
    client.post(
        "/auth/users", json={"email": "doc@audit2.example.com", "password": "supersecret1", "role": "physician"}, headers=owner
    )
    login = client.post("/auth/login", data={"username": "doc@audit2.example.com", "password": "supersecret1"})
    doc_headers = auth_headers(login.json()["access_token"])

    resp = client.get("/audit-log", headers=doc_headers)
    assert resp.status_code == 403
