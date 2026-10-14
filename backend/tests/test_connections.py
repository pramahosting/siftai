import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from app.services import meeting_links as ml
from app.integrations import machine_calendar as mc, ics_feed, zoom


def test_provider_detection():
    assert ml.provider_for("https://us02web.zoom.us/j/81234567890?pwd=abc") == "zoom"
    assert ml.provider_for("https://teams.microsoft.com/l/meetup-join/xyz") == "teams"
    assert ml.provider_for("https://meet.google.com/abc-defg-hij") == "meet"
    assert ml.provider_for("https://evilzoom.us.example.com/j/1") is None
    assert ml.provider_for("https://notzoom.us/j/1") is None
    assert ml.zoom_meeting_id("https://us02web.zoom.us/j/81234567890?pwd=abc") == "81234567890"


def test_join_link_found_in_ics_description():
    ics = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:z1\nDTSTART:20300101T010000Z\nDTEND:20300101T020000Z\nSUMMARY:Sync\n"
           "DESCRIPTION:Join Zoom Meeting\\nhttps://us02web.zoom.us/j/81234567890?pwd=abc\\nMeeting ID: 812\nEND:VEVENT\nEND:VCALENDAR\n")
    s = datetime(2029, 12, 31, tzinfo=timezone.utc)
    ev = mc.events_from_ics_text(ics, s, s + timedelta(days=3))
    assert ev and ev[0]["onlineMeetingUrl"] == "https://us02web.zoom.us/j/81234567890?pwd=abc"


def test_feed_url_rules():
    assert ics_feed.normalize("webcal://x.example.com/a.ics") == "https://x.example.com/a.ics"
    for bad in ("http://example.com/a.ics", "https://127.0.0.1/a.ics", "https://localhost/a.ics", "ftp://x/y", "https://10.0.0.5/x.ics"):
        with pytest.raises(ics_feed.FeedError): ics_feed.validate(bad)


def test_zoom_transcript_picks_newest(monkeypatch):
    class R:
        def __init__(s, code, j=None, text=""): s.status_code, s._j, s.text = code, j, text
        def json(s): return s._j
    async def fake(method, path, **kw):
        if path.endswith("/recordings"):
            return R(200, {"recording_files": [{"id": "a", "file_type": "MP4"}, {"id": "t1", "file_type": "TRANSCRIPT", "recording_end": "2030-01-01T00:00:00Z", "download_url": "https://zoom.us/rec/dl/1"}]})
        return R(200, text="WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nAlex: hello\n")
    monkeypatch.setattr(zoom, "_req", fake)
    ref, vtt = asyncio.run(zoom.transcript_for_meeting("81234567890"))
    assert ref == "t1" and "hello" in vtt


def test_zoom_no_recording_message(monkeypatch):
    class R:
        status_code = 404
    async def fake(*a, **k): return R()
    monkeypatch.setattr(zoom, "_req", fake)
    with pytest.raises(zoom.ZoomUnavailable) as e: asyncio.run(zoom.transcript_for_meeting("81234567890"))
    assert "cloud recording" in str(e.value)
