"""Shared setup used by several test modules: stands up an org with a
roster, a week of shifts, a generated + published schedule."""

from __future__ import annotations

from datetime import date, timedelta


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def bootstrap_published_schedule(client, physician_count: int = 3) -> dict:
    signup = client.post(
        "/auth/signup",
        json={
            "org_name": "Bootstrap EM Group",
            "org_slug": "bootstrap-em",
            "email": "owner@bootstrap.example.com",
            "password": "supersecret1",
        },
    )
    assert signup.status_code == 201, signup.text
    owner_token = signup.json()["access_token"]
    headers = auth_headers(owner_token)

    site = client.post("/sites", json={"name": "Main ED"}, headers=headers)
    assert site.status_code == 201, site.text
    site_id = site.json()["id"]

    day_type = client.post(
        "/shift-types",
        json={
            "site_id": site_id,
            "name": "Day 07-19",
            "category": "day",
            "start_time": "07:00:00",
            "end_time": "19:00:00",
            "duration_hours": 12,
            "required_physicians": 1,
        },
        headers=headers,
    ).json()

    physicians = []
    for i in range(physician_count):
        resp = client.post(
            "/physicians",
            json={
                "first_name": f"Alex{i}",
                "last_name": "Rivera",
                "email": f"alex{i}@bootstrap.example.com",
                "fte": 1.0,
                "site_ids": [site_id],
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        physicians.append(resp.json())

    # Give each physician a login so we can act as them.
    physician_tokens = []
    for physician in physicians:
        create_user = client.post(
            "/auth/users",
            json={"email": physician["email"], "password": "supersecret1", "role": "physician", "physician_id": physician["id"]},
            headers=headers,
        )
        assert create_user.status_code == 201, create_user.text
        login = client.post("/auth/login", data={"username": physician["email"], "password": "supersecret1"})
        assert login.status_code == 200, login.text
        physician_tokens.append(login.json()["access_token"])

    start = date(2026, 4, 6)  # a Monday
    end = start + timedelta(days=6)
    gen = client.post(
        "/shift-instances/generate",
        json={"shift_type_id": day_type["id"], "start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=headers,
    )
    assert gen.status_code == 201, gen.text

    generated = client.post(
        "/schedule-runs/generate",
        json={
            "site_id": site_id,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "generate_ai_summary": False,
        },
        headers=headers,
    )
    assert generated.status_code == 201, generated.text
    run = generated.json()

    publish = client.post(f"/schedule-runs/{run['id']}/publish", headers=headers)
    assert publish.status_code == 200, publish.text
    run = publish.json()

    detail = client.get(f"/schedule-runs/{run['id']}", headers=headers).json()

    return {
        "owner_headers": headers,
        "site_id": site_id,
        "physicians": physicians,
        "physician_tokens": physician_tokens,
        "run": detail,
        "start": start,
        "end": end,
    }
