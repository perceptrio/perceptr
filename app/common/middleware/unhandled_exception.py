from common.services.logger import logger
from fastapi import Request, status
from fastapi.responses import JSONResponse


async def unhandled_exceptions_handler(request: Request, exc: Exception):
    url = (
        f"{request.url.path}?{request.query_params}"
        if request.query_params
        else request.url.path
    )
    logger.error("Unhandled exception", exc_info=exc, url=url)
    return JSONResponse(
        {"detail": "Internal Server Error"},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
