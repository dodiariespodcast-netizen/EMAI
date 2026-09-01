from datetime import date, timedelta

from tests.helpers import auth_headers


def _bootstrap_physician(client):
    signup = client.post(
        "/auth/signup",
        json={"org_name": "Compliance EM", "org_slug": "compliance-em", "email": "owner@compliance.example.com", "password": "supersecret1"},
    )
    owner = auth_headers(signup.json()["access_token"])
    physician = client.post(
        "/physicians",
        json={"first_name": "Riley", "last_name": "Chen", "email": "riley@compliance.example.com", "employment_type": "locums", "hourly_rate": 225.5},
        headers=owner,
    ).json()
    return owner, physician


def test_credential_crud_and_expiring_query(client):
    owner, physician = _bootstrap_physician(client)

    soon = (date.today() + timedelta(days=10)).isoformat()
    far = (date.today() + timedelta(days=400)).isoformat()

    expiring_soon = client.post(
        "/credentials",
        json={
            "physician_id": physician["id"],
            "credential_type": "state_license",
            "issuing_state": "CA",
            "identifier": "A123456",
            "expires_on": soon,
        },
        headers=owner,
    )
    assert expiring_soon.status_code == 201, expiring_soon.text

    not_soon = client.post(
        "/credentials",
        json={"physician_id": physician["id"], "credential_type": "dea", "expires_on": far},
        headers=owner,
    )
    assert not_soon.status_code == 201

    listing = client.get("/credentials", params={"physician_id": physician["id"]}, headers=owner)
    assert listing.status_code == 200
    assert len(listing.json()) == 2

    expiring = client.get("/credentials/expiring", params={"within_days": 60}, headers=owner)
    assert expiring.status_code == 200
    ids = [c["id"] for c in expiring.json()]
    assert expiring_soon.json()["id"] in ids
    assert not_soon.json()["id"] not in ids

    updated = client.patch(
        f"/credentials/{expiring_soon.json()['id']}", json={"note": "renewal submitted"}, headers=owner
    )
    assert updated.status_code == 200
    assert updated.json()["note"] == "renewal submitted"

    deleted = client.delete(f"/credentials/{not_soon.json()['id']}", headers=owner)
    assert deleted.status_code == 204
    listing_after = client.get("/credentials", params={"physician_id": physician["id"]}, headers=owner)
    assert len(listing_after.json()) == 1


def test_physician_locums_fields_round_trip(client):
    _owner, physician = _bootstrap_physician(client)
    assert physician["employment_type"] == "locums"
    assert physician["hourly_rate"] == 225.5
    assert physician["calendar_token"]
