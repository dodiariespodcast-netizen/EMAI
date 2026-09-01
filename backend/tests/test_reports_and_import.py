"""Reporting/exports and bulk roster import."""

import io

from tests.helpers import auth_headers, bootstrap_published_schedule


def test_hours_report_totals_and_missing_rate_flagging(client):
    ctx = bootstrap_published_schedule(client, physician_count=3)
    owner = ctx["owner_headers"]

    # Put a rate on one physician only, so the report has to distinguish
    # "cost known" from "hours known but cost unknown".
    paid = ctx["physicians"][0]
    client.patch(f"/physicians/{paid['id']}", json={"hourly_rate": 200.0}, headers=owner)

    report = client.get(
        "/reports/hours",
        params={"start_date": str(ctx["start"]), "end_date": str(ctx["end"])},
        headers=owner,
    )
    assert report.status_code == 200, report.text
    body = report.json()

    assert body["total_shifts"] == len(ctx["run"]["assignments"])
    # Bootstrap builds 12-hour day shifts.
    assert body["total_hours"] == body["total_shifts"] * 12

    paid_row = next(r for r in body["rows"] if r["physician_id"] == paid["id"])
    assert paid_row["estimated_cost"] == paid_row["hours"] * 200.0
    assert body["total_estimated_cost"] == paid_row["estimated_cost"]

    unpaid = [r for r in body["rows"] if r["hourly_rate"] is None]
    assert unpaid, "expected physicians without a rate on file"
    assert set(body["physicians_missing_rate"]) == {r["physician_name"] for r in unpaid}


def test_hours_csv_export(client):
    ctx = bootstrap_published_schedule(client, physician_count=2)
    resp = client.get(
        "/reports/hours.csv",
        params={"start_date": str(ctx["start"]), "end_date": str(ctx["end"])},
        headers=ctx["owner_headers"],
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in resp.headers["content-disposition"]
    assert "Physician,Employment type,Shifts,Hours" in resp.text
    assert "TOTAL" in resp.text


def test_coverage_report_reports_gaps(client):
    ctx = bootstrap_published_schedule(client, physician_count=3)
    owner = ctx["owner_headers"]
    params = {"start_date": str(ctx["start"]), "end_date": str(ctx["end"])}

    full = client.get("/reports/coverage", params=params, headers=owner).json()
    assert full["coverage_rate"] == 1.0
    assert full["gaps"] == []

    # Drop a shift; it should show up as a specific, named gap.
    dropped = ctx["run"]["assignments"][0]
    client.delete(f"/assignments/{dropped['id']}", headers=owner)

    after = client.get("/reports/coverage", params=params, headers=owner).json()
    assert after["staffed_slots"] == full["staffed_slots"] - 1
    assert after["coverage_rate"] < 1.0
    assert [g["shift_instance_id"] for g in after["gaps"]] == [dropped["shift_instance_id"]]
    assert after["gaps"][0]["short_by"] == 1


def test_schedule_csv_export_includes_unfilled_shifts(client):
    ctx = bootstrap_published_schedule(client, physician_count=2)
    owner = ctx["owner_headers"]
    client.delete(f"/assignments/{ctx['run']['assignments'][0]['id']}", headers=owner)

    resp = client.get(f"/schedule-runs/{ctx['run']['id']}/export.csv", headers=owner)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "Date,Day,Shift,Start,End,Category,Physician,Status" in resp.text
    assert "UNFILLED" in resp.text


def _csv_upload(content: str, name: str = "roster.csv"):
    return {"file": (name, io.BytesIO(content.encode("utf-8")), "text/csv")}


def test_physician_csv_import(client):
    signup = client.post(
        "/auth/signup",
        json={"org_name": "Import EM", "org_slug": "import-em", "email": "owner@import.example.com", "password": "supersecret1"},
    )
    owner = auth_headers(signup.json()["access_token"])
    site_id = client.post("/sites", json={"name": "Main ED"}, headers=owner).json()["id"]

    csv_text = (
        "first_name,last_name,email,credentials,fte,seniority_years,employment_type,hourly_rate,night_preference,weekend_preference,holiday_preference\n"
        "Dana,Reyes,dana@import.example.com,MD,1.0,7,employed,,-1,0,0\n"
        "Sam,Cole,sam@import.example.com,DO,0.5,2,locums,$225.50,2,1,0\n"
    )
    resp = client.post(
        "/physicians/import", files=_csv_upload(csv_text), data={"site_ids": site_id}, headers=owner
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created_count"] == 2
    assert body["error_count"] == 0

    roster = client.get("/physicians", headers=owner).json()
    assert len(roster) == 2
    locum = next(p for p in roster if p["email"] == "sam@import.example.com")
    assert locum["employment_type"] == "locums"
    assert locum["hourly_rate"] == 225.5  # "$225.50" parsed
    assert locum["fte"] == 0.5
    assert locum["night_preference"] == 2
    assert locum["site_ids"] == [site_id]


def test_physician_csv_import_reports_bad_rows_without_failing_the_file(client):
    signup = client.post(
        "/auth/signup",
        json={"org_name": "Partial EM", "org_slug": "partial-em", "email": "owner@partial.example.com", "password": "supersecret1"},
    )
    owner = auth_headers(signup.json()["access_token"])

    csv_text = (
        "first_name,last_name,email,fte\n"
        "Good,Row,good@partial.example.com,1.0\n"
        "Missing,Email,,1.0\n"
        "Bad,Fte,badfte@partial.example.com,not-a-number\n"
        "Out,Ofrange,outofrange@partial.example.com,4.0\n"
        "\n"
        "Another,Good,good2@partial.example.com,0.8\n"
    )
    body = client.post("/physicians/import", files=_csv_upload(csv_text), headers=owner).json()

    assert body["created_count"] == 2
    assert body["error_count"] == 3
    lines = {e["line"] for e in body["errors"]}
    assert lines == {3, 4, 5}  # header is line 1; the blank row is skipped silently
    assert any("must be a number" in e["error"] for e in body["errors"])
    assert any("between 0 and 1" in e["error"] for e in body["errors"])

    assert len(client.get("/physicians", headers=owner).json()) == 2


def test_physician_csv_import_dry_run_writes_nothing(client):
    signup = client.post(
        "/auth/signup",
        json={"org_name": "Dry EM", "org_slug": "dry-em", "email": "owner@dry.example.com", "password": "supersecret1"},
    )
    owner = auth_headers(signup.json()["access_token"])
    csv_text = "first_name,last_name,email\nTest,Run,test@dry.example.com\n"

    body = client.post(
        "/physicians/import", files=_csv_upload(csv_text), data={"dry_run": "true"}, headers=owner
    ).json()
    assert body["dry_run"] is True
    assert body["created_count"] == 1
    assert client.get("/physicians", headers=owner).json() == []


def test_import_rejects_a_file_without_the_required_header(client):
    signup = client.post(
        "/auth/signup",
        json={"org_name": "Bad Header EM", "org_slug": "badheader-em", "email": "owner@badheader.example.com", "password": "supersecret1"},
    )
    owner = auth_headers(signup.json()["access_token"])
    resp = client.post("/physicians/import", files=_csv_upload("name,rate\nDana,200\n"), headers=owner)
    assert resp.status_code == 400
    assert "header row" in resp.json()["detail"]


def test_import_template_is_downloadable_and_round_trips(client):
    signup = client.post(
        "/auth/signup",
        json={"org_name": "Template EM", "org_slug": "template-em", "email": "owner@template.example.com", "password": "supersecret1"},
    )
    owner = auth_headers(signup.json()["access_token"])

    template = client.get("/physicians/import/template.csv", headers=owner)
    assert template.status_code == 200
    assert template.headers["content-type"].startswith("text/csv")

    # The template we hand out must itself import cleanly.
    result = client.post("/physicians/import", files=_csv_upload(template.text), headers=owner).json()
    assert result["created_count"] == 1
    assert result["error_count"] == 0
