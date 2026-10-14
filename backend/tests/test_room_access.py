import os, tempfile
import pytest
from starlette.testclient import TestClient

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "room_default_waiting", False)
    monkeypatch.setattr(settings, "room_default_access", "open")
    from app.main import app
    from app.core.db import engine
    from app.models import Base
    import asyncio
    async def mk():
        async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
    asyncio.run(mk())
    with TestClient(app) as c:
        yield c

def login(c):
    r = c.post("/api/v1/auth/local-login", json={"username": "admin", "password": "Meeting$1"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}, r.json()["access_token"]

def make(c, h, **kw):
    r = c.post("/api/v1/rooms", json={"base_url": "http://t/", **kw}, headers=h); assert r.status_code == 200, r.text
    return r.json()

def join(c, code, **kw):
    ws = c.websocket_connect(f"/api/v1/ws/rooms/{code}"); w = ws.__enter__()
    w.send_json({"type": "join", **kw}); return ws, w

def test_open_room_guest_joins(client):
    h, tok = login(client); r = make(client, h, access="open", waiting_room=False)
    ws, w = join(client, r["code"], name="Gina")
    assert w.receive_json()["type"] == "welcome"; ws.__exit__(None, None, None)

def test_passcode_required_and_host_bypasses(client):
    h, tok = login(client); r = make(client, h, access="passcode", waiting_room=False)
    assert len(r["passcode"]) >= 4
    info = client.get(f"/api/v1/rooms/{r['code']}").json()
    assert info["access"] == "passcode" and "passcode" not in info
    ws, w = join(client, r["code"], name="X", passcode="wrong"); m = w.receive_json()
    assert m["type"] == "error" and m["code"] == "passcode"; ws.__exit__(None, None, None)
    ws, w = join(client, r["code"], name="X", passcode=r["passcode"]); assert w.receive_json()["type"] == "welcome"; ws.__exit__(None, None, None)
    ws, w = join(client, r["code"], name="Host", token=tok); assert w.receive_json()["host"] is True; ws.__exit__(None, None, None)

def test_signed_in_only_blocks_guests(client):
    h, tok = login(client); r = make(client, h, access="signed_in", waiting_room=False)
    ws, w = join(client, r["code"], name="Gina"); m = w.receive_json()
    assert m["type"] == "error" and m["code"] == "signin"; ws.__exit__(None, None, None)
    ws, w = join(client, r["code"], token=tok); assert w.receive_json()["type"] == "welcome"; ws.__exit__(None, None, None)

def test_waiting_room_admit_and_deny(client):
    h, tok = login(client); r = make(client, h, access="open", waiting_room=True)
    hs, host = join(client, r["code"], token=tok); assert host.receive_json()["type"] == "welcome"
    gs, guest = join(client, r["code"], name="Gina")
    assert guest.receive_json()["type"] == "waiting"
    wl = host.receive_json(); assert wl["type"] == "waiting-list" and wl["list"][0]["name"] == "Gina"
    guest.send_json({"type": "chat", "text": "let me in"})          # ignored while waiting
    host.send_json({"type": "admit", "id": wl["list"][0]["id"]})
    assert guest.receive_json()["type"] == "welcome"
    gs.__exit__(None, None, None)
    g2, guest2 = join(client, r["code"], name="Bob"); assert guest2.receive_json()["type"] == "waiting"
    wl = host.receive_json()
    while wl["type"] != "waiting-list" or not wl["list"]: wl = host.receive_json()
    host.send_json({"type": "deny", "id": wl["list"][0]["id"]})
    assert guest2.receive_json()["type"] == "denied"
    g2.__exit__(None, None, None); hs.__exit__(None, None, None)

def test_host_can_change_access(client):
    h, tok = login(client); r = make(client, h, access="open")
    v = client.patch(f"/api/v1/rooms/{r['code']}", json={"access": "passcode"}, headers=h).json()
    assert v["access"] == "passcode" and v["passcode"]
    assert client.get(f"/api/v1/rooms/{r['code']}/host", headers=h).json()["passcode"] == v["passcode"]
    assert client.get(f"/api/v1/rooms/{r['code']}/host").status_code in (401, 403)
