"""A person's own mailbox (Gmail, Yahoo, Outlook.com, iCloud or any SMTP/IMAP server), used for two things only:
sending meeting invitations on their behalf, and picking up calendar invitations (iCalendar attachments) from the inbox.
Message text is never stored: only the calendar data inside invitations is read.
"""
import asyncio, email, imaplib, smtplib, ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email import policy
from app.integrations import ics_feed
from app.core.config import settings

class MailError(RuntimeError): pass

PRESETS = {
    "gmail": {"label": "Gmail", "smtp": ("smtp.gmail.com", 587), "imap": ("imap.gmail.com", 993), "how": "Google Account > Security > 2-Step Verification > App passwords. Use your full Gmail address and the 16-letter app password."},
    "yahoo": {"label": "Yahoo Mail", "smtp": ("smtp.mail.yahoo.com", 587), "imap": ("imap.mail.yahoo.com", 993), "how": "Yahoo Account Security > Generate app password."},
    "outlook": {"label": "Outlook.com / Hotmail", "smtp": ("smtp-mail.outlook.com", 587), "imap": ("outlook.office365.com", 993), "how": "account.microsoft.com > Security > Advanced security options > App passwords (needs two-step verification). Work/school Microsoft 365 accounts usually block this; ask your administrator."},
    "icloud": {"label": "Apple iCloud Mail", "smtp": ("smtp.mail.me.com", 587), "imap": ("imap.mail.me.com", 993), "how": "appleid.apple.com > App-Specific Passwords."},
    "other": {"label": "Other (SMTP / IMAP)", "smtp": ("", 587), "imap": ("", 993), "how": "Your mail provider's SMTP (sending) and IMAP (reading) server names and ports."},
}
ALLOWED_PORTS = {25, 465, 587, 2525, 143, 993}

def _check(host: str, port: int):
    if not host or port not in ALLOWED_PORTS: raise MailError("That mail server address or port is not allowed.")
    if not settings.calendar_feed_allow_private and not ics_feed._public(host): raise MailError("That mail server is not a public address, so it was refused.")

def _smtp_connect(acct: dict):
    host, port = acct["smtp_host"], int(acct["smtp_port"]); _check(host, port)
    try:
        if port == 465: s = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(host, port, timeout=20); s.ehlo()
            if s.has_extn("starttls"): s.starttls(context=ssl.create_default_context()); s.ehlo()   # encrypt whenever the server offers it
        if acct.get("username"): s.login(acct["username"], acct["password"])
        return s
    except smtplib.SMTPAuthenticationError: raise MailError("The mail server refused the sign-in. Use an app password and your full address.")
    except (smtplib.SMTPException, OSError) as exc: raise MailError(f"Could not use the sending server ({type(exc).__name__}).")

def _send_sync(acct: dict, to: list[str], subject: str, body: str, ics: bytes | None = None, method: str = "REQUEST"):
    msg = EmailMessage(); msg["From"] = acct["address"]; msg["To"] = ", ".join(to); msg["Subject"] = subject; msg.set_content(body)
    if ics: msg.add_attachment(ics, maintype="text", subtype="calendar", filename="invite.ics", params={"method": method})
    s = _smtp_connect(acct)
    try: s.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc: raise MailError(f"The message could not be sent ({type(exc).__name__}).")
    finally:
        try: s.quit()
        except Exception: pass

async def send(acct: dict, to: list[str], subject: str, body: str, ics: bytes | None = None):
    await asyncio.to_thread(_send_sync, acct, to, subject, body, ics)

def _imap_connect(acct: dict):
    host, port = acct["imap_host"], int(acct["imap_port"]); _check(host, port)
    try:
        m = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=25) if port != 143 else imaplib.IMAP4(host, port, timeout=25)
        m.login(acct["username"], acct["password"]); return m
    except imaplib.IMAP4.error: raise MailError("The mailbox refused the sign-in. Use an app password and your full address.")
    except OSError as exc: raise MailError(f"Could not reach the mailbox ({type(exc).__name__}).")

def _calendar_parts(raw: bytes) -> list[str]:
    msg = email.message_from_bytes(raw, policy=policy.default); out = []
    for part in msg.walk():
        name = (part.get_filename() or "").lower()
        if part.get_content_type() == "text/calendar" or name.endswith(".ics"):
            try: txt = part.get_content() if part.get_content_maintype() == "text" else part.get_payload(decode=True).decode("utf-8", "ignore")
            except Exception: continue
            if isinstance(txt, str) and "BEGIN:VEVENT" in txt.upper(): out.append(txt)
    return out

def _find_invites_sync(acct: dict, days: int = 30, limit: int = 60) -> list[str]:
    m = _imap_connect(acct); out = []
    try:
        m.select("INBOX", readonly=True)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = m.search(None, "SINCE", since, "TEXT", "BEGIN:VCALENDAR")
        ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-limit:]
        for i in ids:
            typ, parts = m.fetch(i, "(BODY.PEEK[])")          # PEEK: never marks mail as read
            if typ != "OK": continue
            for p in parts:
                if isinstance(p, tuple) and len(p[1]) < 3_000_000: out += _calendar_parts(p[1])
    except imaplib.IMAP4.error as exc: raise MailError(f"The mailbox could not be searched ({exc}).")
    finally:
        try: m.logout()
        except Exception: pass
    return out

async def find_invites(acct: dict, days: int = 30) -> str:
    texts = await asyncio.to_thread(_find_invites_sync, acct, days)
    return "\n".join(texts) if texts else "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"

def _test_sync(acct: dict):
    s = _smtp_connect(acct)
    try: s.quit()
    except Exception: pass
    if acct.get("imap_host"):
        m = _imap_connect(acct)
        try: m.logout()
        except Exception: pass

async def test(acct: dict): await asyncio.to_thread(_test_sync, acct)
