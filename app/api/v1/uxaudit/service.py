import concurrent.futures
import os
from typing import List, Tuple

import httpx
from api.v1.per.schema import GenericResponse
from common.services.files_downloader import FilesDownloader
from common.services.logger import logger
from common.services.s3 import s3_service
from fastapi import HTTPException
from graphs.ux_audit_graph import Issue, UXAudit, UXAuditGraph
from settings import settings
from utils.recording import extract_frames_from_video
from utils.structured_ux_pdf_generator import StructuredUXAuditPDFGenerator


def _audit_video_ux_thread(user_email, file_name):
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(audit_video_ux(user_email, file_name))
    loop.close()
    return result


def audit_video_ux_background_task(user_email: str, file_name: str):
    """
    Run the audit_video_ux function in a separate process to avoid blocking the main thread.
    """
    try:
        with concurrent.futures.ProcessPoolExecutor() as executor:
            future = executor.submit(_audit_video_ux_thread, user_email, file_name)
            pdf_path, frames_analyzed = future.result()
            logger.info(
                "Background UX audit completed",
                pdf_path=pdf_path,
                frames_analyzed=frames_analyzed,
            )
    except Exception as e:
        logger.error(
            "Error in background UX audit task",
            exc_info=e,
            user_email=user_email,
            file_name=file_name,
        )


async def send_lead_ux_audit_email(email: str):
    """
    Send a lead UX audit email to the user.
    """
    brevo_api_key = settings.BREVO_API_KEY
    if not brevo_api_key:
        raise HTTPException(
            status_code=500, detail="Email service configuration is missing"
        )
    # Prepare the email parameters
    params = {"email": email}
    payload = {
        "templateId": 2,
        "cc": [{"email": "emadmohamed95@gmail.com"}],
        "to": [{"email": "bebofit@aucegypt.edu"}],
        "params": params,
    }
    # Prepare the email payload

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
            return GenericResponse(message="Email sent successfully", success=True)
        except httpx.HTTPStatusError as e:
            logger.error(f"Error sending email", exc_info=e)
            raise HTTPException(status_code=400, detail="Failed to send email")
        except httpx.HTTPError as e:
            logger.error(f"Error sending email", exc_info=e)
            raise HTTPException(status_code=400, detail="Failed to send email")


async def send_ux_audit_result_email(user_email: str, pdf_url: str):
    """
    Send a UX audit result email to the user with a public PDF URL.
    """
    try:
        brevo_api_key = settings.BREVO_API_KEY
        if not brevo_api_key:
            raise HTTPException(
                status_code=500, detail="Email service configuration is missing"
            )

        # Prepare the email parameters
        params = {"email": user_email, "pdfLink": pdf_url}

        # Prepare the email payload
        payload = {
            "templateId": 3,
            "bcc": [{"email": "emadmohamed95@gmail.com"}],
            "to": [{"email": user_email}],
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
                logger.info(f"Audit result email sent successfully")
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Error sending UX audit result email due to status error",
                    exc_info=e,
                )
                raise HTTPException(status_code=500, detail=f"Failed to send email")
            except httpx.HTTPError as e:
                logger.error(
                    f"Error sending UX audit result email due to HTTP error", exc_info=e
                )
                raise HTTPException(status_code=500, detail=f"Failed to send email")
    except Exception as e:
        logger.error(f"Error sending UX audit result email", exc_info=e)
        raise HTTPException(status_code=500, detail=f"Failed to send email")


async def audit_video_ux(user_email: str, key: str) -> Tuple[str, int]:
    """
    Audit the UX of a video by extracting frames and generating a comprehensive PDF report.

    Args:
        user_email (str): Email of the user requesting the audit
        key (str): S3 key of the video file to audit (e.g., "1/Mylo 1 trim/original.mp")

    Returns:
        Tuple[str, int]: S3 path to the generated PDF report and number of frames analyzed
    """
    logger.info(f"Starting UX audit for video: {key} (user: {user_email})")

    # Log the file path components for debugging
    if settings.LOG_STYLE == "line":
        logger.info(f"File path analysis:")
        logger.info(f"  - Original file_name: {key}")
        logger.info(f"  - Directory: {os.path.dirname(key)}")
        logger.info(f"  - Basename: {os.path.basename(key)}")
        logger.info(
            f"  - Name without extension: {os.path.splitext(os.path.basename(key))[0]}"
        )

    with FilesDownloader(s3_service.get_s3_client(), keep_temp_dir=False) as downloader:
        # Download the video file
        file_path = downloader.download_file_from_s3(key)

        # Create output directory for frames
        output_dir = os.path.join(os.path.dirname(file_path), "frames")

        # Extract frames from the video
        frames = extract_frames_from_video(file_path, 1, output_dir)

        # Collect structured audit data for all frames
        audit_data: List[Tuple[str, str, UXAudit]] = []

        # Process each frame (limit to first 3 for performance)
        # max_frames = min(2, len(frames))
        max_frames = len(frames)
        logger.info(f"Processing frames for UX audit...", frames=frames)

        for i, frame in enumerate(frames[:max_frames]):
            frame_path = frame[0]
            frame_timestamp = frame[1]

            logger.info(
                "Processing frame",
                frame_index=i + 1,
                max_frames=max_frames,
                frame_timestamp=frame_timestamp,
            )

            try:
                # Generate UX audit for this frame
                ux_audit_graph = UXAuditGraph()
                response = ux_audit_graph.audit_ux(
                    user_email, frame_timestamp, frame_path
                )
                ux_audit_report = response[
                    "ux_audit_report"
                ]  # This is a UXAudit object

                # Add to audit data collection with structured data
                audit_data.append((frame_path, frame_timestamp, ux_audit_report))

                # Log the audit response
                if settings.LOG_STYLE == "line":
                    logger.info(f"UX audit response for frame {i+1}:")
                    logger.info(f"  - Title: {ux_audit_report.short_title}")
                    logger.info(f"  - Summary: {ux_audit_report.summary}")
                    logger.info(f"  - Issues found: {len(ux_audit_report.issues)}")
                    for idx, issue in enumerate(ux_audit_report.issues, 1):
                        logger.info(f"    {idx}. {issue.issue_title}: {issue.issue}")
                    logger.info("================================================")

            except Exception as e:
                logger.error(
                    "Error processing frame",
                    frame_index=i + 1,
                    frame_timestamp=frame_timestamp,
                    exc_info=e,
                )
                # Create a fallback UXAudit object for errors
                error_audit = UXAudit(
                    short_title="Error Processing Screen",
                    summary=f"An error occurred while processing this screen: {str(e)}",
                    issues=[
                        Issue(
                            issue_title="Processing Error",
                            issue=f"Failed to analyze this screen due to: {str(e)}",
                            recommendation="Please check the screen capture and try again.",
                        )
                    ],
                )
                audit_data.append((frame_path, frame_timestamp, error_audit))

        # Generate PDF report using structured ReportLab generator
        logger.info("Generating PDF report with structured data...")

        # Create PDF output directory
        pdf_output_dir = os.path.join(os.path.dirname(file_path), "reports")
        os.makedirs(pdf_output_dir, exist_ok=True)

        # Generate PDF filename with proper handling of complex paths
        # Extract just the filename without extension, handling cases like "original.mp"
        video_basename = os.path.basename(key)
        video_name_no_ext = os.path.splitext(video_basename)[0]

        # Clean the filename for PDF generation (replace spaces and special chars if needed)
        safe_video_name = video_name_no_ext.replace(" ", "_").replace("/", "_")
        pdf_filename = f"ux_audit_report_{safe_video_name}.pdf"

        try:
            # Use the new structured PDF generator
            pdf_generator = StructuredUXAuditPDFGenerator()
            pdf_path = pdf_generator.generate_pdf_from_audit_data(
                audit_data=audit_data,
                output_directory=pdf_output_dir,
                filename=pdf_filename,
            )

        except Exception as e:
            logger.error("Error generating PDF with structured generator", exc_info=e)
            raise Exception("PDF generation failed")

        # Upload PDF to S3 in the same location as the video file
        logger.info("Uploading PDF to S3", pdf_path=pdf_path)

        # Extract directory path from video file name
        # For file_name like "1/Mylo 1 trim/original.mp", this will be "1/Mylo 1 trim"
        video_dir = os.path.dirname(key)

        if video_dir:
            # If video is in a subdirectory, put PDF in the same directory
            # Use forward slashes for S3 paths regardless of OS
            s3_pdf_path = f"{video_dir}/{pdf_filename}".replace("\\", "/")
        else:
            # If video is in root, put PDF in root
            s3_pdf_path = pdf_filename

        try:
            # Read the PDF file content
            with open(pdf_path, "rb") as pdf_file:
                pdf_content = pdf_file.read()

            # Upload to S3
            s3_service.upload_file(s3_pdf_path, pdf_content)

            # Generate public URL
            pdf_url = s3_service.get_public_url(s3_pdf_path)

            # Send email with PDF URL
            await send_ux_audit_result_email(user_email, pdf_url)

            return s3_pdf_path, len(audit_data)

        except Exception as e:
            logger.error(
                "Error uploading PDF to S3 Falling back to local path",
                exc_info=e,
                pdf_path=pdf_path,
                s3_pdf_path=s3_pdf_path,
            )
            # Return local path as fallback
            return pdf_path, len(audit_data)
