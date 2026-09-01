"""End-to-end smoke test: sign up an org, build a roster and a week of
shifts, submit a time-off request (including via the free-text AI intake
path, which runs the deterministic fallback parser since no API key is
configured in tests), generate a schedule, and check the results."""

from datetime import date, timedelta


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_end_to_end_scheduling_workflow(client):
    signup = client.post(
        "/auth/signup",
        json={
            "org_name": "Riverside Emergency Group",
            "org_slug": "riverside-eg",
            "email": "director@riverside.example.com",
            "password": "supersecret1",
        },
    )
    assert signup.status_code == 201, signup.text
    token = signup.json()["access_token"]
    headers = _auth_headers(token)

    site = client.post("/sites", json={"name": "Main ED", "timezone": "America/New_York"}, headers=headers)
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
    )
    assert day_type.status_code == 201, day_type.text
    night_type = client.post(
        "/shift-types",
        json={
            "site_id": site_id,
            "name": "Night 19-07",
            "category": "night",
            "start_time": "19:00:00",
            "end_time": "07:00:00",
            "duration_hours": 12,
            "required_physicians": 1,
        },
        headers=headers,
    )
    assert night_type.status_code == 201, night_type.text

    physicians = []
    for i in range(3):
        resp = client.post(
            "/physicians",
            json={
                "first_name": f"Alex{i}",
                "last_name": "Rivera",
                "email": f"alex{i}@riverside.example.com",
                "fte": 1.0,
                "night_preference": 1 if i == 0 else -1,
                "site_ids": [site_id],
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        physicians.append(resp.json())

    start = date(2026, 3, 2)  # a Monday
    end = start + timedelta(days=6)
    for shift_type_id in (day_type.json()["id"], night_type.json()["id"]):
        gen = client.post(
            "/shift-instances/generate",
            json={
                "shift_type_id": shift_type_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
            headers=headers,
        )
        assert gen.status_code == 201, gen.text
        assert len(gen.json()) == 7

    # Structured time-off request (hard, approved)
    time_off = client.post(
        "/time-off-requests",
        json={
            "physician_id": physicians[1]["id"],
            "start_date": start.isoformat(),
            "end_date": start.isoformat(),
            "request_type": "vacation",
            "priority": "must",
        },
        headers=headers,
    )
    assert time_off.status_code == 201, time_off.text
    approve = client.patch(
        f"/time-off-requests/{time_off.json()['id']}", json={"status": "approved"}, headers=headers
    )
    assert approve.status_code == 200

    # Free-text AI intake path (falls back to rule-based parsing without an API key)
    from_text = client.post(
        "/time-off-requests/from-text",
        json={
            "physician_id": physicians[2]["id"],
            "text": f"I need {start.isoformat()} off, it's important for a family event",
        },
        headers=headers,
    )
    assert from_text.status_code == 201, from_text.text
    assert from_text.json()["priority"] == "must"

    generated = client.post(
        "/schedule-runs/generate",
        json={
            "site_id": site_id,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "generate_ai_summary": True,
        },
        headers=headers,
    )
    assert generated.status_code == 201, generated.text
    run = generated.json()
    assert run["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert run["ai_summary"]

    # physician[1] had an approved MUST-off day -> never assigned that day
    blocked_shift_ids = {
        s["id"]
        for s in client.get(
            "/shift-instances",
            params={"site_id": site_id, "start_date": start.isoformat(), "end_date": start.isoformat()},
            headers=headers,
        ).json()
    }
    violating = [
        a
        for a in run["assignments"]
        if a["physician_id"] == physicians[1]["id"] and a["shift_instance_id"] in blocked_shift_ids
    ]
    assert violating == []

    fairness = client.get(f"/schedule-runs/{run['id']}/fairness", headers=headers)
    assert fairness.status_code == 200
    assert len(fairness.json()) == 3

    publish = client.post(f"/schedule-runs/{run['id']}/publish", headers=headers)
    assert publish.status_code == 200
    assert publish.json()["status"] == "published"


def test_physician_role_cannot_manage_roster(client):
    signup = client.post(
        "/auth/signup",
        json={
            "org_name": "Lakeside EM",
            "org_slug": "lakeside-em",
            "email": "owner@lakeside.example.com",
            "password": "supersecret1",
        },
    )
    owner_headers = _auth_headers(signup.json()["access_token"])

    new_user = client.post(
        "/auth/users",
        json={"email": "doc@lakeside.example.com", "password": "supersecret1", "role": "physician"},
        headers=owner_headers,
    )
    assert new_user.status_code == 201, new_user.text

    login = client.post(
        "/auth/login",
        data={"username": "doc@lakeside.example.com", "password": "supersecret1"},
    )
    assert login.status_code == 200
    doc_headers = _auth_headers(login.json()["access_token"])

    resp = client.post(
        "/physicians",
        json={"first_name": "A", "last_name": "B", "email": "ab@lakeside.example.com"},
        headers=doc_headers,
    )
    assert resp.status_code == 403


def test_physician_can_self_edit_preferences_but_nothing_else(client):
    signup = client.post(
        "/auth/signup",
        json={"org_name": "Prefs EM", "org_slug": "prefs-em", "email": "owner@prefs.example.com", "password": "supersecret1"},
    )
    owner_headers = _auth_headers(signup.json()["access_token"])

    physician = client.post(
        "/physicians",
        json={"first_name": "Sam", "last_name": "Lee", "email": "sam@prefs.example.com"},
        headers=owner_headers,
    ).json()
    client.post(
        "/auth/users",
        json={"email": physician["email"], "password": "supersecret1", "role": "physician", "physician_id": physician["id"]},
        headers=owner_headers,
    )
    login = client.post("/auth/login", data={"username": physician["email"], "password": "supersecret1"})
    doc_headers = _auth_headers(login.json()["access_token"])

    own_prefs = client.patch(
        f"/physicians/{physician['id']}/preferences", json={"night_preference": 2}, headers=doc_headers
    )
    assert own_prefs.status_code == 200, own_prefs.text
    assert own_prefs.json()["night_preference"] == 2

    # Can't touch fields outside the preferences endpoint's scope, and can't
    # use the full physician PATCH at all without scheduler privileges.
    full_patch = client.patch(f"/physicians/{physician['id']}", json={"fte": 0.2}, headers=doc_headers)
    assert full_patch.status_code == 403

    other = client.post(
        "/physicians", json={"first_name": "Other", "last_name": "Doc", "email": "other@prefs.example.com"}, headers=owner_headers
    ).json()
    cross_edit = client.patch(f"/physicians/{other['id']}/preferences", json={"night_preference": -2}, headers=doc_headers)
    assert cross_edit.status_code == 403


def test_user_management(client):
    signup = client.post(
        "/auth/signup",
        json={"org_name": "Users EM", "org_slug": "users-em", "email": "owner@users.example.com", "password": "supersecret1"},
    )
    owner_headers = _auth_headers(signup.json()["access_token"])

    created = client.post(
        "/auth/users",
        json={"email": "sched@users.example.com", "password": "supersecret1", "role": "scheduler"},
        headers=owner_headers,
    )
    assert created.status_code == 201, created.text

    listing = client.get("/auth/users", headers=owner_headers)
    assert listing.status_code == 200
    emails = {u["email"] for u in listing.json()}
    assert {"owner@users.example.com", "sched@users.example.com"} <= emails

    updated = client.patch(f"/auth/users/{created.json()['user_id']}", json={"role": "admin"}, headers=owner_headers)
    assert updated.status_code == 200
    assert updated.json()["role"] == "admin"

    owner_id = signup.json()["user"]["id"]
    self_deactivate = client.patch(f"/auth/users/{owner_id}", json={"is_active": False}, headers=owner_headers)
    assert self_deactivate.status_code == 400
