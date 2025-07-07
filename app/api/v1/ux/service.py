from utils.recording import extract_frames_from_video
from utils.structured_ux_pdf_generator import StructuredUXAuditPDFGenerator
from common.services.files_downloader import FilesDownloader
from common.services.logger import logger
from common.services.s3 import s3_service
from graphs.ux_audit_graph import UXAuditGraph, UXAudit, Issue
import os
from typing import List, Tuple
from urllib.parse import unquote

def audit_video_ux(user_email: str, file_name: str) -> Tuple[str, int]:
    """
    Audit the UX of a video by extracting frames and generating a comprehensive PDF report.
    
    Args:
        user_email (str): Email of the user requesting the audit
        file_name (str): Name of the video file to audit (e.g., "1/Mylo 1 trim/original.mp")
        
    Returns:
        Tuple[str, int]: S3 path to the generated PDF report and number of frames analyzed
    """
    logger.info(f"Starting UX audit for video: {file_name} (user: {user_email})")
    
    # Log the file path components for debugging
    logger.info(f"File path analysis:")
    logger.info(f"  - Original file_name: {file_name}")
    logger.info(f"  - Directory: {os.path.dirname(file_name)}")
    logger.info(f"  - Basename: {os.path.basename(file_name)}")
    logger.info(f"  - Name without extension: {os.path.splitext(os.path.basename(file_name))[0]}")
    
    with FilesDownloader(
        s3_service.get_s3_client(), keep_temp_dir=False
    ) as downloader:
        # Download the video file
        file_path = downloader.download_file_from_s3(file_name)
        
        # Create output directory for frames
        output_dir = os.path.join(os.path.dirname(file_path), "frames")
        
        # Extract frames from the video
        logger.info("Extracting frames from video...")
        frames = extract_frames_from_video(file_path, 1, output_dir)
        
        # Collect structured audit data for all frames
        audit_data: List[Tuple[str, str, UXAudit]] = []
        
        # Process each frame (limit to first 3 for performance)
        max_frames = min(20, len(frames))
        logger.info(f"Processing {max_frames} frames for UX audit...")
        
        for i, frame in enumerate(frames[:max_frames]):
            frame_path = frame[0]
            frame_timestamp = frame[1]
            
            logger.info(f"Processing frame {i+1}/{max_frames} at timestamp {frame_timestamp}")
            
            try:
                # Generate UX audit for this frame
                ux_audit_graph = UXAuditGraph()
                response = ux_audit_graph.audit_ux(user_email, frame_timestamp, frame_path)
                ux_audit_report = response["ux_audit_report"]  # This is a UXAudit object
                
                # Add to audit data collection with structured data
                audit_data.append((frame_path, frame_timestamp, ux_audit_report))
                
                # Log the audit response
                logger.info(f"UX audit response for frame {i+1}:")
                logger.info(f"  - Title: {ux_audit_report.short_title}")
                logger.info(f"  - Summary: {ux_audit_report.summary}")
                logger.info(f"  - Issues found: {len(ux_audit_report.issues)}")
                for idx, issue in enumerate(ux_audit_report.issues, 1):
                    logger.info(f"    {idx}. {issue.issue_title}: {issue.issue}")
                logger.info("================================================")
                
            except Exception as e:
                logger.error(f"Error processing frame {i+1} at {frame_timestamp}: {e}")
                # Create a fallback UXAudit object for errors
                error_audit = UXAudit(
                    short_title="Error Processing Screen",
                    summary=f"An error occurred while processing this screen: {str(e)}",
                    issues=[Issue(
                        issue_title="Processing Error",
                        issue=f"Failed to analyze this screen due to: {str(e)}",
                        recommendation="Please check the screen capture and try again."
                    )]
                )
                audit_data.append((frame_path, frame_timestamp, error_audit))
        
        # Generate PDF report using structured ReportLab generator
        logger.info("Generating PDF report with structured data...")
        
        # Create PDF output directory
        pdf_output_dir = os.path.join(os.path.dirname(file_path), "reports")
        os.makedirs(pdf_output_dir, exist_ok=True)
        
        # Generate PDF filename with proper handling of complex paths
        # Extract just the filename without extension, handling cases like "original.mp"
        video_basename = os.path.basename(file_name)
        video_name_no_ext = os.path.splitext(video_basename)[0]
        
        # Clean the filename for PDF generation (replace spaces and special chars if needed)
        safe_video_name = video_name_no_ext.replace(' ', '_').replace('/', '_')
        pdf_filename = f"ux_audit_report_{safe_video_name}.pdf"
        
        logger.info(f"Generated PDF filename: {pdf_filename}")
        
        try:
            # Use the new structured PDF generator
            pdf_generator = StructuredUXAuditPDFGenerator()
            pdf_path = pdf_generator.generate_pdf_from_audit_data(
                audit_data=audit_data,
                output_directory=pdf_output_dir,
                filename=pdf_filename
            )
            
            logger.info(f"PDF generated successfully with structured ReportLab generator: {pdf_path}")
            
        except Exception as e:
            logger.error(f"Error generating PDF with structured generator: {e}")
            raise Exception(f"PDF generation failed: {e}")
        
        logger.info(f"PDF report generated successfully: {pdf_path}")
        
        # Upload PDF to S3 in the same location as the video file
        logger.info("Uploading PDF to S3...")
        
        # Extract directory path from video file name
        # For file_name like "1/Mylo 1 trim/original.mp", this will be "1/Mylo 1 trim"
        video_dir = os.path.dirname(file_name)
        
        if video_dir:
            # If video is in a subdirectory, put PDF in the same directory
            # Use forward slashes for S3 paths regardless of OS
            s3_pdf_path = f"{video_dir}/{pdf_filename}".replace('\\', '/')
        else:
            # If video is in root, put PDF in root
            s3_pdf_path = pdf_filename
        
        logger.info(f"S3 PDF path will be: {s3_pdf_path}")
        
        try:
            # Read the PDF file content
            with open(pdf_path, 'rb') as pdf_file:
                pdf_content = pdf_file.read()
            
            # Upload to S3
            s3_service.upload_file(s3_pdf_path, pdf_content)
            
            logger.info(f"PDF uploaded to S3 successfully: {s3_pdf_path}")
            logger.info(f"PDF size: {len(pdf_content)} bytes")
            
            return s3_pdf_path, len(audit_data)
            
        except Exception as e:
            logger.error(f"Error uploading PDF to S3: {e}")
            # Return local path as fallback
            logger.warning(f"Falling back to local path: {pdf_path}")
            return pdf_path, len(audit_data)