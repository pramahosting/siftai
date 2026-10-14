from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest
from app.integrations.machine_calendar import events_from_ics_text
from app.services import datasets as ds

NOW = datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc)
WIN = (NOW, NOW + timedelta(days=8))

def ics(*events): return "BEGIN:VCALENDAR\r\n" + "".join(f"BEGIN:VEVENT\r\n{e}\r\nEND:VEVENT\r\n" for e in events) + "END:VCALENDAR\r\n"

def test_single_event_and_escaped_text():
    out = events_from_ics_text(ics("UID:a\r\nDTSTART:20261014T010000Z\r\nDTEND:20261014T020000Z\r\nSUMMARY:Plan\\, review\r\nORGANIZER:mailto:boss@x.com"), *WIN)
    assert [e["subject"] for e in out] == ["Plan, review"] and out[0]["organizer"]["emailAddress"]["address"] == "boss@x.com"

def test_event_outside_window_is_ignored():
    assert events_from_ics_text(ics("UID:a\r\nDTSTART:20261001T010000Z\r\nDTEND:20261001T020000Z\r\nSUMMARY:Old"), *WIN) == []

def test_weekly_recurrence_started_long_ago_with_exdate():
    e = ics("UID:w\r\nDTSTART:20260105T020000Z\r\nDTEND:20260105T030000Z\r\nRRULE:FREQ=WEEKLY;BYDAY=MO,WE\r\nEXDATE:20261014T020000Z\r\nSUMMARY:Sync")
    days = sorted(x["start"]["dateTime"][:10] for x in events_from_ics_text(e, *WIN))
    assert days == ["2026-10-19", "2026-10-21"]          # Wed 14th excluded; Mon 19th and Wed 21st

def test_count_limits_occurrences():
    e = ics("UID:c\r\nDTSTART:20261013T020000Z\r\nDTEND:20261013T030000Z\r\nRRULE:FREQ=DAILY;COUNT=3\r\nSUMMARY:Three")
    assert len(events_from_ics_text(e, *WIN)) == 2        # 13th is before the window; 14th and 15th remain

def test_private_cancelled_and_all_day_are_flagged_for_the_policy_filter():
    from app.services.policy import eligible
    e = ics("UID:p\r\nDTSTART:20261014T010000Z\r\nDTEND:20261014T020000Z\r\nCLASS:PRIVATE\r\nSUMMARY:P",
            "UID:x\r\nDTSTART:20261014T030000Z\r\nDTEND:20261014T040000Z\r\nSTATUS:CANCELLED\r\nSUMMARY:X",
            "UID:d\r\nDTSTART;VALUE=DATE:20261014\r\nSUMMARY:D",
            "UID:ok\r\nDTSTART:20261014T050000Z\r\nDTEND:20261014T060000Z\r\nSUMMARY:OK")
    assert [x["subject"] for x in events_from_ics_text(e, *WIN) if eligible(x)] == ["OK"]

def test_timezone_id_is_honoured():
    e = ics("UID:t\r\nDTSTART;TZID=Australia/Sydney:20261014T090000\r\nDTEND;TZID=Australia/Sydney:20261014T100000\r\nSUMMARY:Sydney")
    assert events_from_ics_text(e, NOW - timedelta(days=1), NOW + timedelta(days=2))[0]["start"]["dateTime"].startswith("2026-10-13T22:00:00")   # UTC+11 in October

SYD = ZoneInfo("Australia/Sydney")
def test_relative_and_iso_dates():
    today = datetime.now(SYD).date()
    assert ds.parse_when("today 09:30", SYD).astimezone(SYD).date() == today
    assert ds.parse_when("+2d 10:00", SYD).astimezone(SYD).date() == today + timedelta(days=2)
    assert ds.parse_when("2026-12-01 10:00", SYD).astimezone(SYD).hour == 10
    assert ds.parse_day("tomorrow", SYD) == (today + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError): ds.parse_when("someday", SYD)

def test_csv_header_validation_and_blank_rows():
    with pytest.raises(ds.ImportError_): ds.read_csv(b"a,b\n1,2\n", "meetings")
    rows = ds.read_csv("external_id,title,start_at\nm1,Hello,today 09:00\n,,\n".encode(), "meetings")
    assert len(rows) == 1 and rows[0]["title"] == "Hello"

def test_every_table_has_a_mock_csv_with_matching_columns():
    for table, spec in ds.TABLES.items():
        f = ds.mock_dir() / f"{table}.csv"
        assert f.is_file(), table
        rows = ds.read_csv(f.read_bytes(), table)
        assert rows and set(rows[0]) <= set(spec["columns"]), table


def test_scan_finds_nested_real_calendars_only(tmp_path):
    from app.integrations import machine_calendar as mc
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "mine.ics").write_text("BEGIN:VCALENDAR\nBEGIN:VEVENT\nEND:VEVENT\nEND:VCALENDAR\n")
    (tmp_path / "fake.ics").write_text("hello")
    found = mc._scan(tmp_path)
    assert [f.name for f in found] == ["mine.ics"]
