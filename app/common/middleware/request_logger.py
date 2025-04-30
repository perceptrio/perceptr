import http
import time
import uuid

from common.services.logger import logger
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    _neglected_paths = ["/health", "/"]

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Generate a unique request ID
        request_id = str(uuid.uuid4())
        url = (
            f"{request.url.path}?{request.query_params}"
            if request.query_params
            else request.url.path
        )
        start_time = time.time()

        # Add request_id to logger context
        logger.set_context(request_id=request_id)
        # Process the request
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        formatted_process_time = "{0:.2f}ms".format(process_time)
        try:
            status_phrase = http.HTTPStatus(response.status_code).phrase
        except ValueError:
            status_phrase = ""
        if url not in self._neglected_paths:
            logger.info(
                "Request completed",
                url=url,
                status_code=response.status_code,
                status_phrase=status_phrase,
                process_time=formatted_process_time,
            )
        # clear the context
        logger.clear_context()
        return response
