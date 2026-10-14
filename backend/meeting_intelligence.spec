# PyInstaller recipe: one folder (onedir) containing MeetingIntelligence(.exe) and its libraries.
# Run through build.cmd / build.sh - not directly.
import os, sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

web = os.environ["WEB_SRC"]                     # built frontend (frontend/dist)
hidden = []
for pkg in ("uvicorn", "alembic", "app", "langchain_core", "sqlalchemy.dialects.sqlite", "sqlalchemy.dialects.postgresql"):
    hidden += collect_submodules(pkg)
hidden += collect_submodules("websockets") + ["aiosqlite", "email_validator", "multipart", "jwt", "cryptography", "tzdata"]
import importlib.util
if importlib.util.find_spec("asyncpg"): hidden += ["asyncpg"] + collect_submodules("asyncpg")      # optional (PostgreSQL only)
datas = [("alembic", "alembic"), (web, "web"), ("../docs/mock-data", "mock-data"), ("../docs/calendar", "calendar")]
for pkg in ("tzdata", "certifi", "langchain_core"):
    datas += collect_data_files(pkg)

a = Analysis(["app/standalone.py"], pathex=["."], datas=datas, hiddenimports=hidden, excludes=["pytest", "pytest_asyncio", "tkinter"])
pyz = PYZ(a.pure)
# Windows: no black console window (messages go to docs/logs/app.log); other systems keep the terminal.
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MeetingIntelligence", console=(sys.platform != "win32"), icon=None)
coll = COLLECT(exe, a.binaries, a.datas, name="MeetingIntelligence")
