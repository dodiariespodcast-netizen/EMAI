"""The demo seed. This is what a new install and every sales demo starts
from, so it needs to keep producing a schedule that actually solves."""

import pytest

from app.models.physician import Credential, Physician
from app.models.requests import TimeOffRequest
from app.models.schedule import Assignment, ScheduleRun
from app.models.tenancy import Organization, User


@pytest.fixture()
def seeded(client):
    """`client` is what points the app at a temp database; seed into it."""
    from app.seed import seed

    return seed(slug="test-demo", admin_email="admin@test-demo.example.com", password="demo1234")


def _session():
    import app.database as database_module

    return database_module.SessionLocal()


def test_seed_builds_a_working_demo_org(seeded):
    assert seeded["physicians"] == 14
    assert len(seeded["sites"]) == 2

    with _session() as db:
        org = db.query(Organization).filter(Organization.slug == "test-demo").one()
        assert db.query(Physician).filter(Physician.org_id == org.id).count() == 14
        # Admin + the three physician logins.
        assert db.query(User).filter(User.org_id == org.id).count() == 4
        assert db.query(TimeOffRequest).filter(TimeOffRequest.org_id == org.id).count() == 6
        assert db.query(Credential).filter(Credential.org_id == org.id).count() > 14


def test_seeded_schedule_solves_and_is_published(seeded):
    """A demo that opens on a half-empty schedule is worse than no demo."""
    for run in seeded["runs"]:
        assert run["status"] in ("OPTIMAL", "FEASIBLE"), run
        assert run["unfilled"] == 0, f"{run['site']} left {run['unfilled']} shifts unfilled"

    with _session() as db:
        org = db.query(Organization).filter(Organization.slug == "test-demo").one()
        runs = db.query(ScheduleRun).filter(ScheduleRun.org_id == org.id).all()
        assert len(runs) == 2
        assert all(r.status.value == "published" for r in runs)
        assert db.query(Assignment).filter(Assignment.org_id == org.id).count() > 100


def test_seeded_logins_work_and_land_on_populated_screens(client, seeded):
    admin = client.post(
        "/auth/login", data={"username": seeded["admin_email"], "password": "demo1234"}
    )
    assert admin.status_code == 200
    headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}

    # The screens a new user opens first should all have content.
    assert len(client.get("/physicians", headers=headers).json()) == 14
    assert len(client.get("/sites", headers=headers).json()) == 2
    assert client.get("/credentials/expiring", params={"within_days": 60}, headers=headers).json()
    assert client.get("/time-off-requests", params={"status_filter": "pending"}, headers=headers).json()

    physician_login = client.post(
        "/auth/login", data={"username": seeded["physician_logins"][0], "password": "demo1234"}
    )
    assert physician_login.status_code == 200
    doc_headers = {"Authorization": f"Bearer {physician_login.json()['access_token']}"}
    me = client.get("/auth/me", headers=doc_headers).json()
    assert me["physician_id"], "seeded physician logins must be linked to their physician record"
    assert client.get("/assignments", params={"physician_id": me["physician_id"]}, headers=doc_headers).json()


def test_seed_refuses_to_clobber_an_existing_org(seeded):
    from app.seed import seed

    with pytest.raises(SystemExit):
        seed(slug="test-demo")


def test_wipe_removes_everything_it_created(client, seeded):
    from app.seed import wipe

    with _session() as db:
        org_id = db.query(Organization).filter(Organization.slug == "test-demo").one().id
        wipe(db, "test-demo")

    with _session() as db:
        assert db.query(Organization).filter(Organization.slug == "test-demo").first() is None
        assert db.query(Physician).filter(Physician.org_id == org_id).count() == 0
        assert db.query(Assignment).filter(Assignment.org_id == org_id).count() == 0
        assert db.query(User).filter(User.org_id == org_id).count() == 0
