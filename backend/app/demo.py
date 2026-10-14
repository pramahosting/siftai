import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, delete
from app.core.db import SessionLocal
from app.core.config import settings
from app.models import User, Meeting, Transcript, TranscriptSegment, Minutes, ActionItem, Briefing, WorkflowRun, Job

_locks:dict={}

async def seed_demo(user:User, reset:bool=False)->dict:
    # One seed at a time per person (a double click must not collide); other people are never blocked.
    async with _locks.setdefault(user.id,asyncio.Lock()):
        return await _seed_demo(user,reset)

async def _seed_demo(user:User, reset:bool=False)->dict:
    if not settings.is_local_demo: raise RuntimeError("Mock data is available only in local development mode")
    tz=ZoneInfo("Australia/Sydney"); today=datetime.now(tz).date()
    async with SessionLocal() as db:
        existing=(await db.execute(select(Meeting).where(Meeting.owner_id==user.id,Meeting.external_id.like("demo-%")))).scalars().all()
        if existing and not reset: return {"seeded":False,"meetings":len(existing),"message":"Mock data is already present"}
        if existing:
            ids=[m.id for m in existing]
            await db.execute(delete(ActionItem).where(ActionItem.meeting_id.in_(ids)))
            await db.execute(delete(Minutes).where(Minutes.meeting_id.in_(ids)))
            await db.execute(delete(Transcript).where(Transcript.meeting_id.in_(ids)))
            await db.execute(delete(Meeting).where(Meeting.id.in_(ids)))
        specs=[
            ("demo-product","Product planning and customer priorities",9,30,60,"normal"),
            ("demo-security","Security review and release readiness",11,0,45,"normal"),
        ]
        meetings=[]
        for external,title,hour,minute,duration,sensitivity in specs:
            start=datetime.combine(today,datetime.min.time(),tzinfo=tz).replace(hour=hour,minute=minute)
            meeting=Meeting(owner_id=user.id,external_id=external,title=title,organizer="Alex Morgan",start_at=start.astimezone(timezone.utc),end_at=(start+timedelta(minutes=duration)).astimezone(timezone.utc),timezone="Australia/Sydney",sensitivity=sensitivity,status="scheduled",transcript_status="ready" if external=="demo-product" else "not_available",minutes_status="draft_ready" if external=="demo-product" else "not_started")
            db.add(meeting); meetings.append(meeting)
        await db.flush()
        transcript_text=("Alex: We reviewed the onboarding launch and agreed to publish the revised checklist on Friday. "
            "Priya: I will update the customer setup guide by Thursday afternoon. "
            "Jordan: I can validate the deployment checklist tomorrow. "
            "Alex: The analytics question is still open; we need Finance to confirm the reporting definition. "
            "The team discussed options for launch support, but made no decision to change the release date.")
        tx=Transcript(meeting_id=meetings[0].id,source_type="mock_fixture",status="ready",language="en",full_text=transcript_text)
        db.add(tx); await db.flush()
        db.add_all([
            TranscriptSegment(transcript_id=tx.id,sequence=0,start_seconds=0,end_seconds=8,speaker="Alex",text="We reviewed the onboarding launch and agreed to publish the revised checklist on Friday."),
            TranscriptSegment(transcript_id=tx.id,sequence=1,start_seconds=8,end_seconds=16,speaker="Priya",text="I will update the customer setup guide by Thursday afternoon."),
            TranscriptSegment(transcript_id=tx.id,sequence=2,start_seconds=16,end_seconds=23,speaker="Jordan",text="I can validate the deployment checklist tomorrow."),
            TranscriptSegment(transcript_id=tx.id,sequence=3,start_seconds=23,end_seconds=32,speaker="Alex",text="The analytics question is still open; we need Finance to confirm the reporting definition."),
        ])
        content={"executive_summary":"The team reviewed onboarding launch readiness and follow-up work. The release date was not changed.","agenda":["Launch readiness","Customer onboarding"],"discussion_points":["The setup guide needs an update.","The analytics reporting definition is awaiting Finance."],"decisions":[{"statement":"Publish the revised checklist on Friday.","evidence":"agreed to publish the revised checklist on Friday","owner":"Not specified"}],"action_items":[{"description":"Update the customer setup guide","owner":"Priya","due_date":"Thursday (confirm calendar date)","priority":"normal","evidence":"I will update the customer setup guide by Thursday afternoon."},{"description":"Validate the deployment checklist","owner":"Jordan","due_date":"Tomorrow (confirm calendar date)","priority":"normal","evidence":"I can validate the deployment checklist tomorrow."}],"risks_and_blockers":["Analytics reporting definition awaits Finance confirmation."],"open_questions":["What reporting definition will Finance confirm?"],"next_steps":["Confirm exact calendar dates for relative deadlines."]}
        db.add(Minutes(meeting_id=meetings[0].id,version=1,content=content,review_status="draft"))
        db.add_all([
            ActionItem(meeting_id=meetings[0].id,description="Update the customer setup guide",owner="Priya",due_date="Thursday (confirm)",priority="normal",status="needs_review",evidence="I will update the customer setup guide by Thursday afternoon."),
            ActionItem(meeting_id=meetings[0].id,description="Validate the deployment checklist",owner="Jordan",due_date="Tomorrow (confirm)",priority="normal",status="needs_review",evidence="I can validate the deployment checklist tomorrow."),
        ])
        local_date=today.isoformat(); text="Morning briefing · Mock fixture\n• 9:30 AM — Product planning and customer priorities\n  Prepare: Review launch checklist and confirm Thursday follow-ups.\n• 11:00 AM — Security review and release readiness\n  Prepare: Bring the deployment checklist.\nMy take:\n• Confirm Finance's reporting definition before the launch review."
        await db.execute(delete(Briefing).where(Briefing.user_id==user.id,Briefing.local_date==local_date,Briefing.run_type=="demo"))
        db.add(Briefing(user_id=user.id,local_date=local_date,run_type="demo",payload={"fixture":True},rendered_text=text,word_count=len(text.split()),generation_status="generated",delivery_status="mock_not_delivered"))
        db.add(WorkflowRun(correlation_id="demo-phase6-run",workflow_name="minutes_generation",status="completed"))
        await db.commit()
        return {"seeded":True,"meetings":2,"transcripts":1,"minutes":1,"action_items":2,"message":"Mock data loaded. A separate private-event fixture is covered by the policy tests; no private event was persisted."}
