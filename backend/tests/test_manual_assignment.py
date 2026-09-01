"""Manual schedule editing: a scheduler overriding what the solver produced."""

from tests.helpers import bootstrap_published_schedule


def test_unassign_reassign_and_fill_a_shift(client):
    ctx = bootstrap_published_schedule(client, physician_count=3)
    owner = ctx["owner_headers"]
    assignments = ctx["run"]["assignments"]
    p0, p1 = ctx["physicians"][0]["id"], ctx["physicians"][1]["id"]

    target = next(a for a in assignments if a["physician_id"] == p0)

    # Unassign -> the shift goes open.
    removed = client.delete(f"/assignments/{target['id']}", headers=owner)
    assert removed.status_code == 204
    assert client.get(f"/assignments/{target['id']}", headers=owner).status_code == 404

    # Re-fill it by hand with someone else.
    detail = client.get("/shift-instances", headers=owner).json()
    shift_id = target["shift_instance_id"]
    assert any(s["id"] == shift_id for s in detail)

    created = client.post(
        "/assignments", json={"shift_instance_id": shift_id, "physician_id": p1}, headers=owner
    )
    assert created.status_code == 201, created.text
    assert created.json()["physician_id"] == p1
    assert created.json()["shift_type_name"] == "Day 07-19"

    # And move it again.
    moved = client.patch(f"/assignments/{created.json()['id']}", json={"physician_id": p0}, headers=owner)
    assert moved.status_code == 200, moved.text
    assert moved.json()["physician_id"] == p0


def test_manual_assignment_refuses_a_hard_conflict_unless_forced(client):
    ctx = bootstrap_published_schedule(client, physician_count=3)
    owner = ctx["owner_headers"]
    p0 = ctx["physicians"][0]["id"]
    existing = next(a for a in ctx["run"]["assignments"] if a["physician_id"] == p0)

    # Double-booking the same physician onto a shift they already hold.
    conflicted = client.post(
        "/assignments",
        json={"shift_instance_id": existing["shift_instance_id"], "physician_id": p0},
        headers=owner,
    )
    assert conflicted.status_code == 409
    assert "already on this shift" in conflicted.json()["detail"]

    forced = client.post(
        "/assignments",
        json={
            "shift_instance_id": existing["shift_instance_id"],
            "physician_id": p0,
            "force": True,
            "override_reason": "covering a double-coverage surge day",
        },
        headers=owner,
    )
    assert forced.status_code == 201, forced.text

    # The override is on the record, with its reason.
    log = client.get("/audit-log", params={"entity_type": "assignment"}, headers=owner).json()
    override = next(e for e in log if e["action"] == "assignment.create" and e["details"].get("forced_over_conflict"))
    assert override["details"]["override_reason"] == "covering a double-coverage surge day"


def test_eligible_physicians_ranks_conflict_free_first(client):
    ctx = bootstrap_published_schedule(client, physician_count=3)
    owner = ctx["owner_headers"]
    target = ctx["run"]["assignments"][0]

    resp = client.get(
        f"/shift-instances/{target['shift_instance_id']}/eligible-physicians", headers=owner
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 3

    # The physician already on this shift is reported as conflicted, and
    # conflicted rows sort last.
    on_shift = next(r for r in rows if r["physician_id"] == target["physician_id"])
    assert on_shift["conflict"] is not None
    conflicts = [r["conflict"] is not None for r in rows]
    assert conflicts == sorted(conflicts)


def test_physician_cannot_hand_edit_the_schedule(client):
    ctx = bootstrap_published_schedule(client, physician_count=2)
    from tests.helpers import auth_headers

    doc = auth_headers(ctx["physician_tokens"][0])
    target = ctx["run"]["assignments"][0]

    assert client.delete(f"/assignments/{target['id']}", headers=doc).status_code == 403
    assert (
        client.post(
            "/assignments",
            json={"shift_instance_id": target["shift_instance_id"], "physician_id": ctx["physicians"][1]["id"]},
            headers=doc,
        ).status_code
        == 403
    )
