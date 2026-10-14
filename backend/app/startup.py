"""First-start preparation, run BEFORE the app begins serving requests.

  1. Loads the mock data CSV files (all tables) - once, the first time the app starts.
  2. Picks up the calendar on this computer for the built-in administrator (the person starting the app)
     and does a first sync, so Today, at a glance is filled in from the very first screen.

Both steps can be switched off in Admin settings (Startup) or .env (LOAD_MOCK_ON_START, CALENDAR_ON_START).
Run on its own with:  python -m app.startup
"""
import asyncio, logging
from sqlalchemy import select
from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.models import User, IntegrationSetting
from app.integrations import machine_calendar as machine
from app.services import calendar_sync as cal
from app.services import datasets as ds

log = logging.getLogger("meeting_platform")
ADMIN_EMAIL, ADMIN_SUBJECT = "admin@example.test", "local-admin"
DONE_KEY = "startup_mock_loaded"

def say(msg: str) -> None:
    log.info(msg)

async def _admin(db) -> User:
    u = (await db.execute(select(User).where(User.entra_subject == ADMIN_SUBJECT))).scalar_one_or_none()
    if not u:
        u = User(entra_subject=ADMIN_SUBJECT, email=ADMIN_EMAIL, display_name="Local Demo Administrator", role="admin", role_override="admin")
        db.add(u); await db.commit(); await db.refresh(u)
    return u

async def run() -> None:
    if not settings.is_local_demo: return           # sample data and computer calendar are local-demo features
    from app.core.runtime_settings import apply_overrides
    async with SessionLocal() as db:
        try: await apply_overrides(db)
        except Exception: pass
        admin = await _admin(db)
        # 1. mock data from the CSV files
        if settings.mock_data_enabled and settings.load_mock_on_start:
            done = await db.get(IntegrationSetting, DONE_KEY)
            if done: say("Sample data: already loaded on an earlier start.")
            else:
                say("Sample data: loading the CSV files from " + str(ds.mock_dir()) + " ...")
                try:
                    result = await ds.load_mock(db, admin)
                    say("Sample data: " + ds.summarize(result))
                    bad = sum(len(t["errors"]) for t in result.values())
                    if not bad:
                        db.add(IntegrationSetting(key=DONE_KEY, value={"loaded": True})); await db.commit()
                except ds.ImportError_ as exc: say(f"Sample data: skipped ({exc})")
                except Exception: log.exception("Sample data load failed"); say("Sample data: could not be loaded (see the log).")
        # 2. calendar on this computer
        if settings.calendar_on_start:
            info = machine.detect()
            if settings.machine_calendar_allowed and info["available"]:
                if await cal.get_consent(db, admin.id) is None:
                    await cal.set_consent(db, admin.id, True)
                    say(f"Calendar: found {info['source']} - reading it for the administrator.")
                elif await cal.get_consent(db, admin.id) == "denied": say("Calendar: found, but the administrator chose not to use it.")
            elif not info["available"] and not cal.graph_configured(): say("Calendar: none found on this computer (add a .ics file to docs/calendar, or connect Microsoft 365).")
            if cal.graph_configured() or await cal.machine_usable(db, admin.id):
                r = await cal.sync_one_safely(admin.id)
                say("Calendar: " + (f"synced {r['eligible']} meeting(s) from {r['source']}." if r else "first sync did not complete (see Admin settings > Calendar)."))

    await engine.dispose()      # the app serves from a fresh event loop; do not carry connections across

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="  %(message)s")
    asyncio.run(run())
