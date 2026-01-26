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
    Also sets up periodic polling for stale sessions.
    """
    db = SessionLocal()
    try:
        stale_recordings = get_stale_sessions(db)
        logger.info(
            "Processing stale recordings on startup",
            stale_recordings=len(stale_recordings),
        )
        for recording in stale_recordings:
            # _process_session_background creates its own DB session, so don't pass db
            logger.info(
                "Processing stale recording",
                recording=recording.id,
                session_id=recording.session_id,
            )
            await asyncio.get_event_loop().run_in_executor(
                None,
                _process_session_background,
                recording.org_id,
                recording.session_id,
                False,  # force=False
            )
    except Exception as e:
        logger.error(
            "Error processing stale recordings",
            exc_info=e,
        )
    finally:
        db.close()

    # Set up periodic polling for stale sessions every 5 minutes
    async def periodic_stale_check():
        """Periodically check for stale sessions"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                db = SessionLocal()
                try:
                    stale_recordings = get_stale_sessions(db)
                    if stale_recordings:
                        logger.info(
                            "Found stale recordings in periodic check",
                            count=len(stale_recordings),
                        )
                        for recording in stale_recordings:
                            logger.info(
                                "Processing stale recording from periodic check",
                                recording=recording.id,
                                session_id=recording.session_id,
                            )
                            await asyncio.get_event_loop().run_in_executor(
                                None,
                                _process_session_background,
                                recording.org_id,
                                recording.session_id,
                                False,
                            )
                except Exception as e:
                    logger.error(
                        "Error in periodic stale check",
                        exc_info=e,
                    )
                finally:
                    db.close()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Unexpected error in periodic stale check loop",
                    exc_info=e,
                )
                await asyncio.sleep(60)  # Wait before retrying on error

    # Start periodic checking task
    asyncio.create_task(periodic_stale_check())
    logger.info("Started periodic stale session checker (every 5 minutes)")


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
