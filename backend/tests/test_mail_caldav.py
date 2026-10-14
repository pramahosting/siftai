import asyncio, email
from datetime import datetime, timedelta, timezone
import pytest
from app.integrations import mail as mailer, caldav
from app.services import invites


def test_recipients_validation():
    assert invites.parse_recipients("A@x.com; b@y.org, a@x.com") == ["a@x.com", "b@y.org"]
    with pytest.raises(ValueError): invites.parse_recipients("not-an-email")
    with pytest.raises(ValueError): invites.parse_recipients(",".join(f"u{i}@x.com" for i in range(60)))


def test_invitation_ics_is_valid_and_parsed_back():
    from app.integrations.machine_calendar import events_from_ics_text
    s = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1)
    ics = invites.build_ics("abc", "Plan, review; Q4", s, s + timedelta(hours=1), "me@x.com", ["a@x.com"], "https://us02web.zoom.us/j/81234567890", "Agenda line")
    text = ics.decode()
    assert "METHOD:REQUEST" in text and "ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:a@x.com" in text and text.endswith("\r\n")
    assert all(len(l.encode()) <= 75 for l in text.split("\r\n"))
    ev = events_from_ics_text(text, s - timedelta(hours=1), s + timedelta(days=1))
    assert ev and ev[0]["subject"] == "Plan, review; Q4" and "zoom.us" in ev[0]["onlineMeetingUrl"]


def test_calendar_parts_extracted_from_mail():
    m = email.message.EmailMessage(); m["Subject"] = "Invitation"; m.set_content("hi")
    m.add_attachment(b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:1\r\nDTSTART:20300101T010000Z\r\nSUMMARY:X\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n", maintype="text", subtype="calendar", filename="i.ics")
    assert len(mailer._calendar_parts(m.as_bytes())) == 1
    plain = email.message.EmailMessage(); plain.set_content("just text")
    assert mailer._calendar_parts(plain.as_bytes()) == []


def test_inbox_search_uses_peek_and_readonly(monkeypatch):
    calls = []
    raw = email.message.EmailMessage(); raw.set_content("x")
    raw.add_attachment(b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:1\r\nDTSTART:20300101T010000Z\r\nSUMMARY:X\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n", maintype="text", subtype="calendar")
    class Fake:
        def select(self, box, readonly=False): calls.append(("select", readonly)); return "OK", [b"1"]
        def search(self, *a): calls.append(("search",) + a); return "OK", [b"1 2"]
        def fetch(self, i, what): calls.append(("fetch", what)); return "OK", [(b"1", raw.as_bytes())]
        def logout(self): pass
    monkeypatch.setattr(mailer, "_imap_connect", lambda acct: Fake())
    out = mailer._find_invites_sync({})
    assert len(out) == 2 and ("select", True) in calls and all(c[1] == "(BODY.PEEK[])" for c in calls if c[0] == "fetch")


def test_ports_and_private_hosts_refused():
    with pytest.raises(mailer.MailError): mailer._check("smtp.example.com", 22)
    with pytest.raises(mailer.MailError): mailer._check("127.0.0.1", 587)


def test_caldav_rejects_xml_entities():
    with pytest.raises(caldav.CalDavError): caldav._xml('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x/>')
