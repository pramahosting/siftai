import asyncio, logging, os, re, smtplib
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
import httpx
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.models import Base, Job, Meeting, Transcript, TranscriptSegment, Minutes, ActionItem, WorkflowRun, IntegrationSetting
from app.integrations.graph import graph, GraphUnavailable
from app.services.ai import generate_minutes
from app.services.transcript_utils import parse_vtt

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s %(message)s")
log=logging.getLogger("meeting_platform.worker")

async def transcribe_audio(path:str,filename:str)->dict:
    from app.services.llm import transcribe, AIUnavailable
    with open(path,"rb") as source:
        data=source.read()
    try: return await transcribe(filename,data)
    except AIUnavailable as exc: raise RuntimeError(str(exc))

def notify_failure(workflow:str,error:str):
    if not all([settings.smtp_host,settings.smtp_from,settings.error_email_to]): return
    try:
        msg=EmailMessage(); msg["Subject"]=f"Meeting Intelligence workflow failed: {workflow}"; msg["From"]=settings.smtp_from; msg["To"]=settings.error_email_to
        msg.set_content(f"The {workflow} workflow failed. Safe error: {error[:300]}. No meeting content is included.")
        with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=15) as smtp:
            smtp.starttls()
            if settings.smtp_user: smtp.login(settings.smtp_user,settings.smtp_password)
            smtp.send_message(msg)
    except Exception: log.exception("Failure notification could not be sent")

async def handle(job:Job):
    async with SessionLocal() as db:
        meeting=(await db.execute(select(Meeting).where(Meeting.id==job.payload["meeting_id"]))).scalar_one_or_none()
        if not meeting: raise RuntimeError("Meeting record no longer exists")
        if job.kind=="fetch_graph_transcript":
            meeting.transcript_status="processing"; await db.commit()
            from app.models import User
            from app.integrations.graph import mailbox_for
            owner=await db.get(User,meeting.owner_id)
            transcript_id,vtt=await graph.transcript_for_calendar_event(meeting.external_id,mailbox_for(owner.email) if owner else None)
            existing=(await db.execute(select(Transcript).where(Transcript.meeting_id==meeting.id,Transcript.source_reference==transcript_id))).scalar_one_or_none()
            if existing:
                meeting.transcript_status="ready"; await db.commit(); return
            segs=parse_vtt(vtt); text="\n".join(s["text"] for s in segs)
            if not text: raise RuntimeError("Graph returned an empty transcript")
            t=Transcript(meeting_id=meeting.id,source_type="teams_official",status="ready",full_text=text,source_reference=transcript_id)
            db.add(t); await db.flush()
            for i,s in enumerate(segs): db.add(TranscriptSegment(transcript_id=t.id,sequence=i,start_seconds=s["start"],end_seconds=s["end"],speaker=s.get("speaker"),text=s["text"]))
            meeting.transcript_status="ready"; await db.commit()
        elif job.kind=="fetch_zoom_transcript":
            from app.integrations import zoom
            from app.services.meeting_links import zoom_meeting_id
            meeting.transcript_status="processing"; await db.commit()
            zid=meeting.external_id.split(":",1)[1] if meeting.external_id.startswith("zoom:") else zoom_meeting_id(meeting.join_url)
            if not zid: raise RuntimeError("This meeting has no Zoom meeting number")
            ref,vtt=await zoom.transcript_for_meeting(zid)
            existing=(await db.execute(select(Transcript).where(Transcript.meeting_id==meeting.id,Transcript.source_reference==ref))).scalar_one_or_none()
            if existing:
                meeting.transcript_status="ready"; await db.commit(); return
            segs=parse_vtt(vtt); text="\n".join(s["text"] for s in segs)
            if not text: raise RuntimeError("Zoom returned an empty transcript")
            t=Transcript(meeting_id=meeting.id,source_type="zoom_official",status="ready",full_text=text,source_reference=ref)
            db.add(t); await db.flush()
            for i,sg in enumerate(segs): db.add(TranscriptSegment(transcript_id=t.id,sequence=i,start_seconds=sg["start"],end_seconds=sg["end"],speaker=sg.get("speaker"),text=sg["text"]))
            meeting.transcript_status="ready"; await db.commit()
        elif job.kind=="transcribe_audio":
            meeting.transcript_status="processing"; await db.commit()
            try:
                result=await transcribe_audio(job.payload["path"],job.payload["filename"])
                existing=(await db.execute(select(Transcript).where(Transcript.meeting_id==meeting.id,Transcript.source_reference==f"upload:{job.id}"))).scalar_one_or_none()
                if existing:
                    meeting.transcript_status="ready"; await db.commit()
                    if settings.audio_retention_days==0:
                        try: os.unlink(job.payload["path"])
                        except FileNotFoundError: pass
                    return
                t=Transcript(meeting_id=meeting.id,source_type="authorized_audio_upload",status="ready",language=result.get("language") or "en",full_text=result.get("text") or "")
                t.source_reference=f"upload:{job.id}"
                db.add(t); await db.flush()
                for i,s in enumerate(result.get("segments",[])):
                    db.add(TranscriptSegment(transcript_id=t.id,sequence=i,start_seconds=s.get("start"),end_seconds=s.get("end"),speaker=s.get("speaker_id"),text=s.get("text", "")))
                meeting.transcript_status="ready"; await db.commit()
            except Exception:
                raise
            else:
                if settings.audio_retention_days==0: os.unlink(job.payload["path"])
        elif job.kind=="generate_minutes":
            transcript=await db.get(Transcript,job.payload["transcript_id"])
            if not transcript: raise RuntimeError("Transcript no longer exists")
            existing=(await db.execute(select(Minutes).where(Minutes.source_job_id==job.id))).scalar_one_or_none()
            if existing: meeting.minutes_status="draft_ready"; await db.commit(); return
            meeting.minutes_status="processing"; await db.commit()
            content=await generate_minutes(transcript.full_text,meeting.title)
            version=(await db.execute(select(Minutes.version).where(Minutes.meeting_id==meeting.id).order_by(Minutes.version.desc()).limit(1))).scalar_one_or_none() or 0
            row=Minutes(meeting_id=meeting.id,source_job_id=job.id,version=version+1,content=content,review_status="draft")
            db.add(row); await db.flush()
            for a in content.get("action_items",[]):
                db.add(ActionItem(meeting_id=meeting.id,description=a["description"],owner=a.get("owner"),due_date=a.get("due_date"),priority=a.get("priority","normal"),status="needs_review",evidence=a.get("evidence")))
            meeting.minutes_status="draft_ready"; await db.commit()
        else: raise RuntimeError(f"Unsupported job type: {job.kind}")

async def claim_job():
    """Claim one job atomically: the UPDATE only succeeds for one worker even when several run at once."""
    from sqlalchemy import update
    async with SessionLocal() as db:
        for _ in range(5):
            now=datetime.now(timezone.utc)
            claimable=((Job.status=="queued") & (Job.available_at<=now)) | ((Job.status=="running") & (Job.locked_at<now-timedelta(minutes=5)))
            row=(await db.execute(select(Job.id,Job.status,Job.locked_at,Job.attempts).where(claimable).order_by(Job.created_at).limit(1))).first()
            if not row: return None
            guard=(Job.id==row.id)&(Job.status==row.status)&(Job.attempts==row.attempts)
            res=await db.execute(update(Job).where(guard).values(status="running",locked_at=now,attempts=Job.attempts+1))
            await db.commit()
            if res.rowcount==1:
                j=await db.get(Job,row.id); await db.refresh(j)
                return j.id,j.kind,dict(j.payload),j.attempts,j.max_attempts
        return None

async def process_one():
    claimed=await claim_job()
    if not claimed: return False
    job_id,kind,payload,attempts,max_attempts=claimed
    try:
        async with SessionLocal() as db: job=await db.get(Job,job_id)
        await handle(job)
        async with SessionLocal() as db:
            row=await db.get(Job,job_id); row.status="completed"; row.locked_at=None
            run_id=payload.get("workflow_run_id")
            if run_id:
                run=await db.get(WorkflowRun,run_id)
                if run: run.status="completed"; run.updated_at=datetime.now(timezone.utc)
            await db.commit()
        log.info("job completed id=%s kind=%s",job_id,kind)
    except Exception as exc:
        safe=str(exc)[:300]; log.warning("job failed id=%s kind=%s error=%s",job_id,kind,safe)
        async with SessionLocal() as db:
            row=await db.get(Job,job_id); row.last_error=safe; row.locked_at=None
            run_id=payload.get("workflow_run_id")
            run=await db.get(WorkflowRun,run_id) if run_id else None
            if run: run.retry_count=attempts; run.failure_stage=kind; run.safe_error=safe; run.updated_at=datetime.now(timezone.utc)
            if attempts>=max_attempts:
                row.status="failed"
                if run: run.status="failed"
                meeting=await db.get(Meeting,payload.get("meeting_id"))
                if meeting:
                    if kind.startswith(("transcribe","fetch_")): meeting.transcript_status="failed"
                    if kind=="generate_minutes": meeting.minutes_status="failed"
                await db.commit(); notify_failure(kind,safe)
                if kind=="transcribe_audio" and payload.get("path"):
                    try: os.unlink(payload["path"])
                    except FileNotFoundError: pass
            else:
                row.status="queued"; row.available_at=datetime.now(timezone.utc)+timedelta(seconds=min(600,2**attempts*5))
                if run: run.status="retrying"
                await db.commit()
    return True

async def retention_sweep():
    async with SessionLocal() as db:
        prefs=await db.get(IntegrationSetting,"preferences")
        transcript_days=(prefs.value.get("transcript_retention_days",365) if prefs else 365)
        minutes_days=(prefs.value.get("minutes_retention_days",365) if prefs else 365)
        cutoff=datetime.now(timezone.utc)-timedelta(days=transcript_days)
        await db.execute(delete(Transcript).where(Transcript.created_at<cutoff))
        minutes_cutoff=datetime.now(timezone.utc)-timedelta(days=minutes_days)
        await db.execute(delete(Minutes).where(Minutes.generated_at<minutes_cutoff))
        await db.commit()
    if settings.audio_retention_days>0 and os.path.isdir(settings.audio_storage_dir):
        audio_cutoff=datetime.now(timezone.utc).timestamp()-timedelta(days=settings.audio_retention_days).total_seconds()
        for name in os.listdir(settings.audio_storage_dir):
            path=os.path.join(settings.audio_storage_dir,name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path)<audio_cutoff: os.unlink(path)
            except OSError: log.exception("Audio retention cleanup failed for an artifact")

async def main():
    last_sweep=0; last_settings=0; last_cal=0.0; last_cal_date=None; sync_task=None
    from app.core.runtime_settings import apply_overrides
    from app.services.calendar_sync import auto_sync, user_timezone
    while True:
        try:
            if datetime.now(timezone.utc).timestamp()-last_settings>10:
                async with SessionLocal() as sdb: await apply_overrides(sdb)
                last_settings=datetime.now(timezone.utc).timestamp()
            minutes=settings.calendar_sync_minutes
            if minutes>0:
                nowts=datetime.now(timezone.utc).timestamp()
                async with SessionLocal() as cdb: today=datetime.now(await user_timezone(cdb)).date()
                if nowts-last_cal>=minutes*60 or today!=last_cal_date:
                    if not (sync_task and not sync_task.done()):
                        async def _sync():
                            async with SessionLocal() as cdb: await auto_sync(cdb)
                        sync_task=asyncio.create_task(_sync())
                    last_cal=nowts; last_cal_date=today
            worked=await process_one()
            if datetime.now(timezone.utc).timestamp()-last_sweep>3600:
                await retention_sweep(); last_sweep=datetime.now(timezone.utc).timestamp()
            if not worked: await asyncio.sleep(2)
        except SQLAlchemyError: log.exception("Database error in worker"); await asyncio.sleep(5)
        except Exception: log.exception("Worker loop error"); await asyncio.sleep(5)

if __name__=="__main__": asyncio.run(main())
