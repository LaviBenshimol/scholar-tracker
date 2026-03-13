from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from scholar_tracker.config import settings
from scholar_tracker.models.database import get_total_citations, get_tracked_papers, init_db
from scholar_tracker.routes.chat import router as ui_router
from scholar_tracker.routes.webhook import router as webhook_router
from scholar_tracker.services.scheduler import scheduler
from scholar_tracker.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB (creates sqlite tables if they don't exist)
    init_db()

    # Validate configuration
    settings.validate_startup()

    # Start the APScheduler for routine checks
    logger.info("Starting background scheduler...")
    scheduler.start()

    yield

    # Shutdown routines
    logger.info("Shutting down background scheduler...")
    scheduler.shutdown()

app = FastAPI(title="Scholar Citation Tracker", lifespan=lifespan)

# Include real webhook routers (port 8000/webhook) for Meta
app.include_router(webhook_router)

# Include local development simulator UI router (port 8000/ui-api/...)
app.include_router(ui_router)

# Serve the vanilla HTML UI from root '/ui'
app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")


@app.get("/")
def root():
    """Health check endpoint with real system status."""
    try:
        papers = get_tracked_papers()
        total = get_total_citations()
        db_ok = True
    except Exception:
        papers = []
        total = 0
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "Scholar Citation Tracker",
        "database": {
            "connected": db_ok,
            "tracked_papers": len(papers),
            "total_citations": total,
        },
        "scheduler": {
            "running": scheduler.running,
            "interval_hours": settings.check_interval_hours,
        },
        "config": {
            "whatsapp_configured": bool(settings.whatsapp_token),
            "scholar_author_set": bool(settings.scholar_author_id),
            "whitelisted_numbers": len(settings.whitelisted_numbers),
        },
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
