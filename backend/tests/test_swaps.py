from tests.helpers import auth_headers, bootstrap_published_schedule


def test_offer_claim_and_approve_swap(client):
    ctx = bootstrap_published_schedule(client, physician_count=3)
    owner = ctx["owner_headers"]
    physicians = ctx["physicians"]
    tokens = ctx["physician_tokens"]
    assignments = ctx["run"]["assignments"]

    # Find a shift assigned to physician 0.
    p0_id = physicians[0]["id"]
    p1_id = physicians[1]["id"]
    offered = next(a for a in assignments if a["physician_id"] == p0_id)

    p0_headers = auth_headers(tokens[0])
    p1_headers = auth_headers(tokens[1])

    offer = client.post("/shift-swaps", json={"assignment_id": offered["id"], "note": "need this covered"}, headers=p0_headers)
    assert offer.status_code == 201, offer.text
    swap = offer.json()
    assert swap["status"] == "open"

    # p1 claims it
    claim = client.post(f"/shift-swaps/{swap['id']}/claim", json={"physician_id": p1_id}, headers=p1_headers)
    assert claim.status_code == 200, claim.text
    assert claim.json()["status"] == "claimed"

    # scheduler approves
    approve = client.post(f"/shift-swaps/{swap['id']}/approve", headers=owner)
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "approved"

    updated_run = client.get(f"/schedule-runs/{ctx['run']['id']}", headers=owner).json()
    reassigned = next(a for a in updated_run["assignments"] if a["id"] == offered["id"])
    assert reassigned["physician_id"] == p1_id
    assert reassigned["status"] == "swapped"


def test_cannot_claim_own_offered_shift(client):
    ctx = bootstrap_published_schedule(client, physician_count=2)
    physicians = ctx["physicians"]
    tokens = ctx["physician_tokens"]
    assignments = ctx["run"]["assignments"]

    p0_id = physicians[0]["id"]
    offered = next(a for a in assignments if a["physician_id"] == p0_id)
    p0_headers = auth_headers(tokens[0])

    offer = client.post("/shift-swaps", json={"assignment_id": offered["id"]}, headers=p0_headers)
    swap = offer.json()

    claim = client.post(f"/shift-swaps/{swap['id']}/claim", json={"physician_id": p0_id}, headers=p0_headers)
    assert claim.status_code == 400


def test_approve_rejects_conflicting_swap(client):
    """Constructs a deterministic conflict: a day shift and an immediately-
    adjacent night shift (0-hour gap) on the same date, with preferences
    strong enough to force the solver to split them predictably -- p0 gets
    the day shift, p1 (who loves nights, and whom p0 strongly avoids) gets
    the night shift. Claiming p0's day shift then means p1 would be working
    both back-to-back, which the swap approval must refuse."""
    signup = client.post(
        "/auth/signup",
        json={"org_name": "Conflict EM", "org_slug": "conflict-em", "email": "owner@conflict.example.com", "password": "supersecret1"},
    )
    owner = auth_headers(signup.json()["access_token"])
    site_id = client.post("/sites", json={"name": "Main ED"}, headers=owner).json()["id"]

    day_type = client.post(
        "/shift-types",
        json={"site_id": site_id, "name": "Day", "category": "day", "start_time": "07:00:00", "end_time": "19:00:00", "duration_hours": 12, "required_physicians": 1},
        headers=owner,
    ).json()
    night_type = client.post(
        "/shift-types",
        json={"site_id": site_id, "name": "Night", "category": "night", "start_time": "19:00:00", "end_time": "07:00:00", "duration_hours": 12, "required_physicians": 1},
        headers=owner,
    ).json()

    p0 = client.post(
        "/physicians",
        json={"first_name": "Dana", "last_name": "Lee", "email": "dana@conflict.example.com", "night_preference": -2, "site_ids": [site_id]},
        headers=owner,
    ).json()
    p1 = client.post(
        "/physicians",
        json={"first_name": "Sam", "last_name": "Kim", "email": "sam@conflict.example.com", "night_preference": 2, "site_ids": [site_id]},
        headers=owner,
    ).json()

    client.post("/auth/users", json={"email": p0["email"], "password": "supersecret1", "role": "physician", "physician_id": p0["id"]}, headers=owner)
    client.post("/auth/users", json={"email": p1["email"], "password": "supersecret1", "role": "physician", "physician_id": p1["id"]}, headers=owner)
    p0_token = client.post("/auth/login", data={"username": p0["email"], "password": "supersecret1"}).json()["access_token"]

    the_date = "2026-05-04"
    client.post("/shift-instances", json={"shift_type_id": day_type["id"], "date": the_date}, headers=owner)
    client.post("/shift-instances", json={"shift_type_id": night_type["id"], "date": the_date}, headers=owner)

    generated = client.post(
        "/schedule-runs/generate",
        json={"site_id": site_id, "period_start": the_date, "period_end": the_date, "generate_ai_summary": False},
        headers=owner,
    ).json()
    client.post(f"/schedule-runs/{generated['id']}/publish", headers=owner)
    detail = client.get(f"/schedule-runs/{generated['id']}", headers=owner).json()

    day_assignment = next(a for a in detail["assignments"] if a["physician_id"] == p0["id"])

    offer = client.post("/shift-swaps", json={"assignment_id": day_assignment["id"]}, headers=auth_headers(p0_token))
    assert offer.status_code == 201, offer.text
    swap = offer.json()

    claim = client.post(f"/shift-swaps/{swap['id']}/claim", json={"physician_id": p1["id"]}, headers=owner)
    assert claim.status_code == 200, claim.text

    approve = client.post(f"/shift-swaps/{swap['id']}/approve", headers=owner)
    assert approve.status_code == 409, approve.text


def test_cancel_open_swap(client):
    ctx = bootstrap_published_schedule(client, physician_count=2)
    physicians = ctx["physicians"]
    tokens = ctx["physician_tokens"]
    assignments = ctx["run"]["assignments"]

    p0_id = physicians[0]["id"]
    offered = next(a for a in assignments if a["physician_id"] == p0_id)
    p0_headers = auth_headers(tokens[0])

    offer = client.post("/shift-swaps", json={"assignment_id": offered["id"]}, headers=p0_headers)
    swap = offer.json()

    cancel = client.post(f"/shift-swaps/{swap['id']}/cancel", headers=p0_headers)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
