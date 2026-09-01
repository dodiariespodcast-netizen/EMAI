from tests.helpers import bootstrap_published_schedule


def test_list_assignments_denormalized_and_filterable(client):
    ctx = bootstrap_published_schedule(client, physician_count=2)
    owner = ctx["owner_headers"]
    p0_id = ctx["physicians"][0]["id"]

    all_assignments = client.get("/assignments", headers=owner)
    assert all_assignments.status_code == 200
    assert len(all_assignments.json()) == len(ctx["run"]["assignments"])
    sample = all_assignments.json()[0]
    assert sample["site_name"] == "Main ED"
    assert sample["schedule_run_status"] == "published"
    assert "date" in sample and "shift_type_name" in sample

    mine = client.get("/assignments", params={"physician_id": p0_id}, headers=owner)
    assert mine.status_code == 200
    assert all(a["physician_id"] == p0_id for a in mine.json())

    single = client.get(f"/assignments/{sample['id']}", headers=owner)
    assert single.status_code == 200
    assert single.json()["id"] == sample["id"]


def test_get_assignment_404_for_unknown_id(client):
    ctx = bootstrap_published_schedule(client, physician_count=1)
    resp = client.get("/assignments/does-not-exist", headers=ctx["owner_headers"])
    assert resp.status_code == 404
