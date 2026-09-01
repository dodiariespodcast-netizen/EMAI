from tests.helpers import bootstrap_published_schedule


def test_ics_feed_lists_published_shifts(client):
    ctx = bootstrap_published_schedule(client, physician_count=2)
    physician = ctx["physicians"][0]

    resp = client.get(f"/calendar/{physician['calendar_token']}.ics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    body = resp.text
    assert "BEGIN:VCALENDAR" in body
    assert "END:VCALENDAR" in body

    own_shift_count = sum(1 for a in ctx["run"]["assignments"] if a["physician_id"] == physician["id"])
    assert body.count("BEGIN:VEVENT") == own_shift_count


def test_ics_feed_unknown_token_404s(client):
    resp = client.get("/calendar/not-a-real-token.ics")
    assert resp.status_code == 404
