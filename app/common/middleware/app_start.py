import asyncio
from contextlib import asynccontextmanager

from api.v1.per.service import _process_session_background
from api.v1.recording.service import get_stale_sessions
from common.services.logger import logger
from common.services.sqs_listener import get_sqs_listener
from database import SessionLocal
from fastapi import FastAPI


async def process_stale_sessions_once():
    """
    On startup, check for stale recordings and process them once.
    """
    db = SessionLocal()
    try:
        stale_recordings = get_stale_sessions(db)
        logger.info(
            "Processing stale recordings",
            stale_recordings=len(stale_recordings),
        )
        for recording in stale_recordings:
            # _process_session_background is a sync function, so run in threadpool
            logger.info(
                "Processing stale recording",
                recording=recording.id,
            )
            await asyncio.get_event_loop().run_in_executor(
                None,
                _process_session_background,
                db,
                recording.org_id,
                recording.session_id,
            )
    except Exception as e:
        logger.error(
            "Error processing stale recordings",
            exc_info=e,
        )
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: process stale recordings once in a coroutine
    task = asyncio.create_task(process_stale_sessions_once())
    sqs_listener = get_sqs_listener()
    # await sqs_listener.start()
    # logger.info("SQS listener service started successfully")
    try:
        yield
    finally:
        # Shutdown: cancel the background task if still running
        task.cancel()
        try:
            sqs_listener = get_sqs_listener()
            # await sqs_listener.stop()
            # logger.info("SQS listener service stopped successfully")
            await task
        except Exception as e:
            logger.error(
                "Error while stopping SQS listener service",
                exc_info=e,
                service="sqs_listener",
                action="shutdown",
            )
        except asyncio.CancelledError:
            pass
