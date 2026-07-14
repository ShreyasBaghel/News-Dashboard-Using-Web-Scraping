import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.pipeline import run_pipeline
from app.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def scheduled_pipeline_run():
    """Trigger the scheduled pipeline run in the background (every 12 hours)."""
    logger.info("Executing scheduled news dashboard refresh...")
    try:
        await run_pipeline(keyword=None, force_refresh=True)
        logger.info("Scheduled news dashboard refresh completed successfully.")
    except Exception as e:
        logger.error(f"Scheduled pipeline run failed: {str(e)}")

def start_scheduler():
    """Initialize and start the background scheduler."""
    if not scheduler.running:
        # Schedule the pipeline to run periodically
        scheduler.add_job(
            scheduled_pipeline_run,
            'interval',
            hours=settings.REFRESH_INTERVAL_HOURS,
            id='default_pipeline_job',
            replace_existing=True
        )
        
        # Trigger an initial run immediately on startup if there is no cache
        scheduler.add_job(
            scheduled_pipeline_run,
            id='startup_pipeline_job'
        )
        
        scheduler.start()
        logger.info("Background news pipeline scheduler started.")

def shutdown_scheduler():
    """Shut down the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background news pipeline scheduler shut down.")
