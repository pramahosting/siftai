from datetime import datetime, timezone
import httpx
import re
from html import unescape
from app.core.config import settings

GRAPH="https://graph.microsoft.com/v1.0"

class GraphUnavailable(RuntimeError): pass

def mailbox_for(email: str) -> str | None:
    """Each person is read from their own mailbox. The built-in demo admin uses the configured calendar user."""
    if email.lower() == "admin@example.test": return settings.graph_user_id or None
    return email or None

class GraphClient:
    async def _token(self) -> str:
        if not all([settings.entra_tenant_id, settings.graph_client_id, settings.graph_client_secret]):
            raise GraphUnavailable("Microsoft Graph integration is not configured")
        url=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/oauth2/v2.0/token"
        data={"client_id":settings.graph_client_id,"client_secret":settings.graph_client_secret,"grant_type":"client_credentials","scope":"https://graph.microsoft.com/.default"}
        async with httpx.AsyncClient(timeout=15) as c:
            r=await c.post(url,data=data)
            if r.status_code>=400: raise GraphUnavailable(f"Microsoft token request failed ({r.status_code})")
            return r.json()["access_token"]

    async def get(self, path: str, params: dict | None=None):
        token=await self._token(); url=path if path.startswith("https://") else GRAPH+path
        async with httpx.AsyncClient(timeout=25) as c:
            r=await c.get(url,params=params,headers={"Authorization":f"Bearer {token}","Prefer":"outlook.timezone=\"UTC\""})
            if r.status_code==429: raise GraphUnavailable("Microsoft Graph is throttling requests")
            if r.status_code>=400: raise GraphUnavailable(f"Microsoft Graph request failed ({r.status_code})")
            return r.json()

    async def calendar(self,start: datetime,end: datetime,mailbox: str|None=None) -> list[dict]:
        mailbox=mailbox or settings.graph_user_id
        if not mailbox: raise GraphUnavailable("Calendar principal is not configured")
        url=f"{GRAPH}/users/{mailbox}/calendarView"
        params={"startDateTime":start.astimezone(timezone.utc).isoformat(),"endDateTime":end.astimezone(timezone.utc).isoformat(),"$top":"100","$select":"id,subject,organizer,start,end,isCancelled,isAllDay,sensitivity,responseStatus,onlineMeeting,onlineMeetingUrl,webLink"}
        events=[]
        while url:
            data=await self.get(url,params); events.extend(data.get("value",[])); url=data.get("@odata.nextLink"); params=None
        return events

    async def transcript_text(self, meeting_id: str, online_meeting_id: str, transcript_id: str, mailbox: str|None=None) -> str:
        if not settings.graph_transcript_enabled: raise GraphUnavailable("Teams transcript access is disabled")
        user=mailbox or settings.graph_user_id
        path=f"/users/{user}/onlineMeetings/{online_meeting_id}/transcripts/{transcript_id}/content"
        token=await self._token()
        async with httpx.AsyncClient(timeout=30) as c:
            r=await c.get(GRAPH+path,headers={"Authorization":f"Bearer {token}","Accept":"text/vtt"})
            if r.status_code==404: raise GraphUnavailable("Official Teams transcript is not available")
            if r.status_code>=400: raise GraphUnavailable(f"Transcript request failed ({r.status_code})")
            return r.text

    async def transcript_for_calendar_event(self, event_id: str, mailbox: str|None=None) -> tuple[str, str]:
        """Return (transcript id, VTT content) for an event only when Graph confirms it exists."""
        if not settings.graph_transcript_enabled: raise GraphUnavailable("Teams transcript access is disabled")
        user=mailbox or settings.graph_user_id
        event=await self.get(f"/users/{user}/events/{event_id}",{"$select":"onlineMeeting,onlineMeetingUrl"})
        join_url=((event.get("onlineMeeting") or {}).get("joinUrl") or event.get("onlineMeetingUrl"))
        if not join_url: raise GraphUnavailable("Calendar event does not reference an online meeting")
        escaped=join_url.replace("'","''")
        meetings=await self.get(f"/users/{user}/onlineMeetings",{"$filter":f"JoinWebUrl eq '{escaped}'","$select":"id"})
        candidates=meetings.get("value",[])
        if not candidates: raise GraphUnavailable("No supported online meeting matched the calendar event")
        online_id=candidates[0]["id"]
        transcripts=await self.get(f"/users/{user}/onlineMeetings/{online_id}/transcripts")
        items=transcripts.get("value",[])
        if not items: raise GraphUnavailable("Official Teams transcript is not available yet")
        transcript_id=items[0]["id"]
        return transcript_id, await self.transcript_text(event_id,online_id,transcript_id,mailbox)

    async def related_context(self, events: list[dict], since: datetime, mailbox: str|None=None) -> dict[str,list[str]]:
        """Fetch bounded recent message previews, match in memory, and do not persist them."""
        if not settings.graph_context_enabled: return {}
        user=mailbox or settings.graph_user_id
        since_iso=since.astimezone(timezone.utc).isoformat()
        mail=await self.get(f"/users/{user}/messages",{"$filter":f"receivedDateTime ge {since_iso}","$select":"subject,bodyPreview,receivedDateTime,from,webLink","$top":"100","$orderby":"receivedDateTime desc"})
        chats=await self.get(f"/users/{user}/chats/getAllMessages",{"$filter":f"lastModifiedDateTime ge {since_iso}","$top":"100"})
        sources=[]
        for item in mail.get("value",[]):
            source=" ".join([item.get("subject", ""),item.get("bodyPreview", ""),((item.get("from") or {}).get("emailAddress") or {}).get("address", "")])
            sources.append(source)
        for item in chats.get("value",[]):
            source=re.sub(r"<[^>]+>"," ",item.get("body",{}).get("content", ""))
            sources.append(unescape(source))
        result={}
        for event in events:
            title=(event.get("subject") or "").lower()
            words={w for w in re.findall(r"[a-z0-9]{4,}",title) if w not in {"meeting","catchup","catch-up"}}
            matched=[]
            for source in sources:
                clean=" ".join(source.split())
                if words and any(w in clean.lower() for w in words): matched.append(clean[:350])
                if len(matched)>=3: break
            result[event.get("id","")]=matched
        return result

graph=GraphClient()
