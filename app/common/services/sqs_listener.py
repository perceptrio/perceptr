import asyncio
import json
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, AsyncGenerator, Dict, Optional

import boto3
from botocore.exceptions import ClientError
from common.services.logger import logger
from core.constants import SQSQueueConfig
from fastapi import FastAPI
from settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    try:
        sqs_listener = get_sqs_listener()
        # await sqs_listener.start()
        # logger.info("SQS listener service started successfully")
    except Exception as e:
        logger.error(
            "Failed to start SQS listener service",
            exc_info=e,
            service="sqs_listener",
            action="startup",
        )

    try:
        yield
    finally:
        # Ensure cleanup happens in finally block
        try:
            sqs_listener = get_sqs_listener()
            # await sqs_listener.stop()
            # logger.info("SQS listener service stopped successfully")
        except Exception as e:
            logger.error(
                "Error while stopping SQS listener service",
                exc_info=e,
                service="sqs_listener",
                action="shutdown",
            )


class SQSListener:
    def __init__(self) -> None:
        self._initialize_client()
        self.is_running = False
        self._thread: Optional[Future[None]] = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._main_loop = asyncio.get_event_loop()

    def _initialize_client(self) -> None:
        """Initialize or reinitialize the SQS client."""
        self.sqs_client = boto3.client(
            "sqs",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        self.queue_url = settings.SQS_QUEUE_URL

    def _handle_messages_sync(self) -> None:
        """Synchronous message handling loop running in separate thread."""
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            while self.is_running:
                try:
                    response = self.sqs_client.receive_message(
                        QueueUrl=self.queue_url,
                        MaxNumberOfMessages=SQSQueueConfig.MAX_MESSAGES,
                        WaitTimeSeconds=SQSQueueConfig.WAIT_TIME_SECONDS,
                        VisibilityTimeout=SQSQueueConfig.VISIBILITY_TIMEOUT,
                    )

                    messages = response.get("Messages", [])
                    for message in messages:
                        if not self.is_running:
                            break
                        try:
                            # Run the coroutine in this thread's event loop
                            success = loop.run_until_complete(
                                self.process_message(message)
                            )
                            if success:
                                self.sqs_client.delete_message(
                                    QueueUrl=self.queue_url,
                                    ReceiptHandle=message["ReceiptHandle"],
                                )
                        except ClientError as e:
                            logger.error(f"AWS error processing message", exc_info=e)

                except ClientError as e:
                    logger.error(f"AWS error receiving messages", exc_info=e)
                    if not self.is_running:
                        break
                except Exception as e:
                    logger.error(
                        f"Unexpected error in message handling thread", exc_info=e
                    )
                    if not self.is_running:
                        break
        finally:
            loop.close()

    async def process_message(self, message: Dict[str, Any]) -> bool:
        """
        Process a single SQS message containing S3 event notification.
        Returns True if processing was successful, False otherwise.
        """
        try:
            # Parse the message body which contains the S3 event
            body = json.loads(message["Body"])
            records = body.get("Records", [])

            for record in records:
                if record["eventSource"] != "aws:s3":
                    logger.warning(f"Skipping non-S3 event: {record['eventSource']}")
                    continue

                s3_info = record["s3"]
                bucket_name = s3_info["bucket"]["name"]
                object_key = s3_info["object"]["key"]

                # TODO: Implement AI processing logic here
                # This should process the uploaded batch file
                logger.info(f"Processing batch file: s3://{bucket_name}/{object_key}")

            return True

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message body", exc_info=e)
            return False
        except KeyError as e:
            logger.error(f"Missing required field in message", exc_info=e)
            return False
        except Exception as e:
            logger.error(f"Error processing message", exc_info=e)
            return False

    async def start(self) -> None:
        """Start the SQS listener in a separate thread."""
        if self.is_running:
            logger.warning("SQS Listener is already running")
            return

        self.is_running = True
        self._thread = self._executor.submit(self._handle_messages_sync)
        logger.info("SQS Listener started in background thread")

    async def stop(self) -> None:
        """Stop the SQS listener and its thread."""
        if not self.is_running:
            return

        logger.info("Stopping SQS listener...")
        self.is_running = False
        if self._thread:
            self._thread.cancel()
        self._executor.shutdown(wait=False)
        logger.info("SQS Listener stopped")


@lru_cache()
def get_sqs_listener() -> SQSListener:
    """Get or create a singleton instance of SQSListener."""
    return SQSListener()


# Clear the cache when module reloads
get_sqs_listener.cache_clear()
