"""Single-program entry point: starts the API, the background worker and the web app together.

Works both from source (python -m app.standalone) and as the compiled MeetingIntelligence program.
Data and logs live in a `docs` folder next to the program; nothing is written elsewhere.
"""
import logging, os, secrets, socket, sys, threading, webbrowser
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
# Folder the user sees (next to the .exe) vs. folder holding bundled read-only resources.
BASE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[2]
RES = Path(getattr(sys, "_MEIPASS", "")) if FROZEN else Path(__file__).resolve().parents[2]

def _dotenv(key: str, default: str = "") -> str:
    """Environment value, or the same key from a .env file next to the program."""
    if key in os.environ: return os.environ[key]
    try:
        for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() == key: return v.strip().strip('"').strip("'")
    except OSError: pass
    return default

def _truthy(v: str) -> bool: return v.strip().lower() in ("1", "true", "yes", "on")

def lan_addresses() -> list[str]:
    out = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET): out.add(info[4][0])
    except OSError: pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s: s.connect(("10.255.255.255", 1)); out.add(s.getsockname()[0])
    except OSError: pass
    return sorted(a for a in out if not a.startswith("127."))

def ensure_certificate(folder: Path) -> tuple[Path, Path]:
    """A self-signed certificate for https on this computer / network (browsers show a one-time warning)."""
    import datetime, ipaddress
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    folder.mkdir(parents=True, exist_ok=True); cert_p, key_p = folder / "cert.pem", folder / "key.pem"
    names = {"localhost", socket.gethostname()}; ips = {"127.0.0.1", *lan_addresses()}
    want = ",".join(sorted(names | ips)); stamp = folder / "names.txt"
    if cert_p.exists() and key_p.exists() and stamp.exists() and stamp.read_text() == want and (datetime.datetime.now().timestamp() - cert_p.stat().st_mtime) < 300 * 86400: return cert_p, key_p
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Meeting Intelligence (this computer)")])
    san = x509.SubjectAlternativeName([x509.DNSName(n) for n in sorted(names)] + [x509.IPAddress(ipaddress.ip_address(i)) for i in sorted(ips)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=365)).add_extension(san, critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True).sign(key, hashes.SHA256()))
    cert_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_p.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    stamp.write_text(want); return cert_p, key_p

def free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0: return port
    raise SystemExit(f"No free port found between {preferred} and {preferred + 19}.")

def prepare_environment(port: int) -> Path:
    docs = BASE / "docs"; data = docs / "data"; logs = docs / "logs"
    for d in (data, logs, data / "audio"): d.mkdir(parents=True, exist_ok=True)
    os.chdir(BASE)                                     # lets an optional .env next to the program be read
    # A private signing secret per installation instead of a well-known default.
    key = data / "auth.secret"
    if not key.exists(): key.write_text(secrets.token_urlsafe(48))
    web = (RES / "web") if FROZEN else (RES / "frontend" / "dist")
    # Sample data and calendar folders live in docs/ so they can be edited; copy the bundled defaults on first run.
    import shutil
    for name, bundled in (("mock-data", RES / "mock-data"), ("calendar", RES / "calendar")):
        target = docs / name
        if not target.exists() and bundled.is_dir() and FROZEN: shutil.copytree(bundled, target)
        else: target.mkdir(exist_ok=True)
    defaults = {
        "APP_ENV": "development", "AUTH_MODE": "local", "ALLOW_LOCAL_AUTH": "true",
        "DATABASE_URL": f"sqlite+aiosqlite:///{(data / 'meeting_intelligence.db').as_posix()}",
        "AUDIO_STORAGE_DIR": str(data / "audio"), "FRONTEND_ORIGIN": f"http://127.0.0.1:{port}",
        "LOCAL_AUTH_SECRET": key.read_text().strip(), "MOCK_DATA_DIR": str(docs / "mock-data"), "WEB_DIR": str(web), "RUN_WORKER": "true",
    }
    for k, v in defaults.items(): os.environ.setdefault(k, v)
    root = logging.getLogger(); root.setLevel(logging.INFO)
    fh = logging.FileHandler(logs / "app.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")); root.addHandler(fh)
    if sys.stdout: 
        sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fh.formatter); root.addHandler(sh)
    return docs

def migrate() -> None:
    from alembic import command
    from alembic.config import Config
    cfg = Config()
    cfg.set_main_option("script_location", str((RES / "backend" / "alembic") if not FROZEN else (RES / "alembic")))
    command.upgrade(cfg, "head")

def already_running(port: int) -> str | None:
    """The address of another copy of the app already answering on this port, if any."""
    import ssl, urllib.request
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    for scheme in ("http", "https"):
        try:
            with urllib.request.urlopen(f"{scheme}://127.0.0.1:{port}/api/v1/health", timeout=1.5, context=ctx) as r:
                if r.status == 200: return f"{scheme}://127.0.0.1:{port}/"
        except Exception: continue
    return None

def show_error(message: str) -> None:
    """The Windows build has no console, so problems are shown in a message box (and are always in docs/logs/app.log)."""
    try:
        if sys.platform == "win32":
            import ctypes; ctypes.windll.user32.MessageBoxW(0, message, "Meeting Intelligence", 0x10)
        else: print(message, file=sys.stderr)
    except Exception: pass

def main() -> None:
    preferred = int(os.environ.get("PORT", "8000"))
    running = already_running(preferred)
    if running:                                          # second double-click: just show the running app
        if os.environ.get("NO_BROWSER") != "1": webbrowser.open(running)
        return
    port = free_port(preferred)
    use_https = _truthy(_dotenv("MI_HTTPS")); lan = _dotenv("MI_LISTEN", "").lower() == "lan"
    if lan: use_https = use_https or _truthy(_dotenv("MI_HTTPS", "true"))      # network mode implies https unless switched off
    os.environ.setdefault("FRONTEND_ORIGIN", f"{'https' if use_https else 'http'}://127.0.0.1:{port}")
    prepare_environment(port)
    log = logging.getLogger("meeting_platform")
    if lan and not _dotenv("LOCAL_ADMIN_PASSWORD"):
        # Never expose the well-known default administrator password to the network.
        pw_file = BASE / "docs" / "data" / "admin-password.txt"
        if not pw_file.exists(): pw_file.write_text(secrets.token_urlsafe(12))
        os.environ["LOCAL_ADMIN_PASSWORD"] = pw_file.read_text().strip()
        log.warning("Network mode: the administrator password is in %s (set LOCAL_ADMIN_PASSWORD in .env to choose your own).", pw_file)
    if not (Path(os.environ["WEB_DIR"]) / "index.html").is_file():
        log.warning("Web app not found at %s - only the API will be available.", os.environ["WEB_DIR"])
    migrate()
    print("\n  Preparing data before the app starts...", flush=True)
    import asyncio
    from app import startup
    asyncio.run(startup.run())
    import uvicorn
    from app.main import app
    scheme = "https" if use_https else "http"; url = f"{scheme}://127.0.0.1:{port}/"
    kwargs = {}
    if use_https:
        cert, key = ensure_certificate(BASE / "docs" / "data" / "tls"); kwargs = {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}
    host = "127.0.0.1"; extra = ""
    if lan:
        host = "0.0.0.0"; addrs = [f"{scheme}://{a}:{port}/" for a in lan_addresses()]
        extra = "\n  Other computers on your network can open: " + ", ".join(addrs) + (" (accept the one-time certificate warning)" if use_https else "")
        log.warning("Network mode is on: other computers can reach this app. Make sure the administrator password has been changed.")
    print(f"\n  Meeting Intelligence is running at {url}{extra}\n  Sign in as admin, or use Sign up.\n  To stop it, run Stop Meeting Intelligence.cmd (or press Ctrl+C if this is a console).\n", flush=True)
    log.info("Meeting Intelligence is running at %s%s", url, extra)
    if os.environ.get("NO_BROWSER") != "1": threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_config=None, **kwargs)

if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except BaseException as exc:
        logging.getLogger("meeting_platform").exception("Meeting Intelligence could not start")
        show_error(f"Meeting Intelligence could not start.\n\n{type(exc).__name__}: {exc}\n\nDetails are in docs\\logs\\app.log next to the program.")
        sys.exit(1)
