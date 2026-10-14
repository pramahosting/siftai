import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import api
from app.api.routes_admin import router as admin_router
from app.api.routes_connections import router as connections_router
from app.api.routes_rooms import router as rooms_router
from app.core.config import settings

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s %(message)s")
app=FastAPI(title=settings.app_name,version="1.0.0",description="Meeting preparation, transcript processing and human-reviewed minutes")
@app.middleware("http")
async def keep_errors_readable(request: Request, call_next):
    # Unhandled errors would otherwise skip the CORS headers and the browser would only say "Failed to fetch".
    try:
        return await call_next(request)
    except Exception as exc:
        logging.getLogger("app").exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": f"Server error: {type(exc).__name__}: {str(exc)[:300]}"}, status_code=500)

app.add_middleware(CORSMiddleware,allow_origins=sorted({settings.frontend_origin,settings.frontend_origin.replace("//localhost","//127.0.0.1"),settings.frontend_origin.replace("//127.0.0.1","//localhost")}),allow_credentials=True,allow_methods=["GET","POST","PATCH","PUT","DELETE"],allow_headers=["Authorization","Content-Type","X-Correlation-ID"])
app.include_router(api)
app.include_router(admin_router)
app.include_router(connections_router)
app.include_router(rooms_router)

@app.on_event("startup")
async def load_saved_settings():
    from app.core.db import SessionLocal
    from app.core.runtime_settings import apply_overrides
    try:
        async with SessionLocal() as db: await apply_overrides(db)
    except Exception: logging.getLogger("meeting_platform").warning("Saved settings could not be loaded yet (database not migrated?)")

import asyncio, os
from pathlib import Path

@app.on_event("startup")
async def start_embedded_worker():
    """Single-binary mode: run the background worker inside the same process."""
    if os.environ.get("RUN_WORKER","").lower()=="true":
        from app.workers import runner
        app.state.worker=asyncio.create_task(runner.main())

_web=os.environ.get("WEB_DIR","")
if _web and (Path(_web)/"index.html").is_file():
    from fastapi.staticfiles import StaticFiles
    # Built web app is served from the same address as the API (no separate frontend server).
    app.mount("/",StaticFiles(directory=_web,html=True),name="web")
else:
    @app.get("/")
    async def root(): return {"name":settings.app_name,"version":"1.0.0","docs":"/docs"}
