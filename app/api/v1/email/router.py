import httpx
from api.v1.email.schema import EmailRequest
from core.constants import APIPath
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from settings import settings

router = APIRouter(prefix=f"{APIPath.V1}/email", tags=["email"])


@router.post("/demo", response_model=dict[str, str])  # type: ignore
async def send_contact_email(request: EmailRequest):  # type: ignore
    # Honeypot check
    if request.website:
        # If honeypot field is filled, return success but don't send email
        return JSONResponse(
            status_code=200, content={"message": "Email sent successfully"}
        )

    brevo_api_key = settings.BREVO_API_KEY
    if not brevo_api_key:
        raise HTTPException(
            status_code=500, detail="Email service configuration is missing"
        )

    # Prepare the email parameters
    params = {
        "name": request.name,
        "email": request.email,
        "company": request.company or "Not provided",
        "details": request.details or "Not provided",
    }

    # Prepare the email payload
    payload = {
        "templateId": 1,
        "cc": [{"email": "emadmohamed95@gmail.com"}],
        "to": [{"email": "bebofit@aucegypt.edu"}],
        "params": params,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.brevo.com/v3/smtp/email",
                json=payload,
                headers={
                    "accept": "application/json",
                    "api-key": brevo_api_key,
                    "content-type": "application/json",
                },
            )
            response.raise_for_status()
            return {"message": "Email sent successfully"}
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to send email: {str(e)}"
            )
