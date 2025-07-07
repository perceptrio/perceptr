import os
import io
from typing import List, Tuple, Optional
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from PIL import Image as PILImage
from common.services.logger import logger
from graphs.ux_audit_graph import UXAudit, Issue


class StructuredUXAuditPDFGenerator:
    """
    A ReportLab-only PDF generator for UX audit reports that works with structured UXAudit data.
    Includes screen images with professional styling.
    """
    
    def __init__(self, page_size=A4):
        self.page_size = page_size
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom styles for the PDF document."""
        # Define color palette
        primary_color = HexColor('#2C3E50')      # Dark blue-grey
        secondary_color = HexColor('#3498DB')     # Blue
        accent_color = HexColor('#E74C3C')        # Red for issues
        success_color = HexColor('#27AE60')       # Green for recommendations
        muted_color = HexColor('#7F8C8D')         # Grey for metadata
        light_bg = HexColor('#ECF0F1')            # Light grey background
        
        # Title style
        self.styles.add(ParagraphStyle(
            name='MainTitle',
            parent=self.styles['Title'],
            fontSize=24,
            spaceAfter=30,
            spaceBefore=20,
            textColor=primary_color,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        # Subtitle style
        self.styles.add(ParagraphStyle(
            name='MainSubtitle',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceAfter=20,
            textColor=secondary_color,
            alignment=TA_CENTER,
            fontName='Helvetica'
        ))
        
        # Frame title style
        self.styles.add(ParagraphStyle(
            name='FrameTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=15,
            spaceBefore=20,
            textColor=primary_color,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold'
        ))
        
        # Screen title style (from UX audit)
        self.styles.add(ParagraphStyle(
            name='ScreenTitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=10,
            textColor=secondary_color,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold'
        ))
        
        # Metadata style
        self.styles.add(ParagraphStyle(
            name='Metadata',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=8,
            textColor=muted_color,
            alignment=TA_LEFT,
            fontName='Helvetica'
        ))
        
        # Summary style
        self.styles.add(ParagraphStyle(
            name='Summary',
            parent=self.styles['Normal'],
            fontSize=12,
            spaceAfter=15,
            textColor=primary_color,
            alignment=TA_JUSTIFY,
            leftIndent=0.2*inch,
            rightIndent=0.2*inch,
            leading=16,
            fontName='Helvetica'
        ))
        
        # Section heading style
        self.styles.add(ParagraphStyle(
            name='SectionHeading',
            parent=self.styles['Heading3'],
            fontSize=14,
            spaceAfter=10,
            spaceBefore=15,
            textColor=primary_color,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold'
        ))
        
        # Issue title style
        self.styles.add(ParagraphStyle(
            name='IssueTitle',
            parent=self.styles['Heading4'],
            fontSize=12,
            spaceAfter=5,
            spaceBefore=10,
            textColor=accent_color,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold'
        ))
        
        # Issue description style
        self.styles.add(ParagraphStyle(
            name='IssueDescription',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            textColor=primary_color,
            alignment=TA_JUSTIFY,
            leftIndent=0.3*inch,
            rightIndent=0.1*inch,
            leading=14,
            fontName='Helvetica'
        ))
        
        # Recommendation style
        self.styles.add(ParagraphStyle(
            name='Recommendation',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=12,
            textColor=success_color,
            alignment=TA_JUSTIFY,
            leftIndent=0.3*inch,
            rightIndent=0.1*inch,
            leading=14,
            fontName='Helvetica'
        ))
        
        # No issues style
        self.styles.add(ParagraphStyle(
            name='NoIssues',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=10,
            textColor=success_color,
            alignment=TA_LEFT,
            leftIndent=0.3*inch,
            fontName='Helvetica-Oblique'
        ))
    
    def _resize_image_if_needed(self, image_path: str, max_width: float, max_height: float) -> Tuple[float, float]:
        """
        Calculate the appropriate image dimensions while maintaining aspect ratio.
        
        Args:
            image_path (str): Path to the image file
            max_width (float): Maximum width in points
            max_height (float): Maximum height in points
            
        Returns:
            Tuple[float, float]: (width, height) in points
        """
        try:
            with PILImage.open(image_path) as img:
                original_width, original_height = img.size
                
                # Calculate scaling factor
                width_ratio = max_width / original_width
                height_ratio = max_height / original_height
                scale_factor = min(width_ratio, height_ratio)
                
                # Calculate new dimensions
                new_width = original_width * scale_factor
                new_height = original_height * scale_factor
                
                return new_width, new_height
        except Exception as e:
            logger.warning(f"Could not calculate image dimensions for {image_path}: {e}")
            # Return default dimensions
            return min(max_width, 6*inch), min(max_height, 4*inch)
    
    def _create_issues_table(self, issues: List[Issue]) -> Optional[Table]:
        """
        Create a formatted table for issues if there are any.
        
        Args:
            issues (List[Issue]): List of issues to display
            
        Returns:
            Optional[Table]: Table element or None if no issues
        """
        if not issues:
            return None
        
        # Create table data with strings instead of Paragraph objects
        data = [['Issue', 'Description', 'Recommendation']]
        
        for issue in issues:
            # Use simple strings for table data
            data.append([issue.issue_title, issue.issue, issue.recommendation])
        
        # Create table
        table = Table(data, colWidths=[2*inch, 2.5*inch, 2.5*inch])
        
        # Style the table
        table.setStyle(TableStyle([
            # Header row styling
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#34495E')),
            ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#FFFFFF')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Data rows styling
            ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F8F9FA')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 1), (-1, -1), 'TOP'),
            
            # Borders
            ('GRID', (0, 0), (-1, -1), 1, HexColor('#BDC3C7')),
            ('LINEBELOW', (0, 0), (-1, 0), 2, HexColor('#2C3E50')),
            
            # Padding
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        return table
    
    def generate_pdf(
        self,
        frames_data: List[Tuple[str, str, UXAudit]],  # (frame_path, timestamp, ux_audit)
        output_path: str,
        title: str = "UX Audit Report",
        subtitle: Optional[str] = None
    ) -> str:
        """
        Generate a PDF report with frame images and their corresponding structured UX audit data.
        
        Args:
            frames_data (List[Tuple[str, str, UXAudit]]): List of (frame_path, timestamp, ux_audit)
            output_path (str): Path where the PDF will be saved
            title (str): Title for the PDF report
            subtitle (Optional[str]): Subtitle for the PDF report
            
        Returns:
            str: Path to the generated PDF file
        """
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Create PDF document
            doc = SimpleDocTemplate(
                output_path,
                pagesize=self.page_size,
                rightMargin=0.75*inch,
                leftMargin=0.75*inch,
                topMargin=1*inch,
                bottomMargin=1*inch
            )
            
            # Build story (content)
            story = []
            
            # Add title page
            story.append(Paragraph(title, self.styles['MainTitle']))
            story.append(Spacer(1, 20))
            
            # Add subtitle if provided
            if subtitle:
                story.append(Paragraph(subtitle, self.styles['MainSubtitle']))
                story.append(Spacer(1, 20))
            
            # Add generation timestamp
            timestamp = datetime.now().strftime("%B %d, %Y at %H:%M:%S")
            story.append(Paragraph(f"Generated on: {timestamp}", self.styles['Metadata']))
            story.append(Spacer(1, 10))
            
            # Add summary
            story.append(Paragraph(f"Total screens analyzed: {len(frames_data)}", self.styles['Metadata']))
            story.append(Spacer(1, 30))
            
            # Add executive summary
            total_issues = sum(len(ux_audit.issues) for _, _, ux_audit in frames_data)
            story.append(Paragraph("Executive Summary", self.styles['SectionHeading']))
            story.append(Paragraph(
                f"This report analyzes {len(frames_data)} screens from the user session. "
                f"A total of {total_issues} issues were identified across all screens, "
                f"ranging from usability concerns to enhancement opportunities.",
                self.styles['Summary']
            ))
            story.append(Spacer(1, 30))
            
            # Process each frame
            for idx, (frame_path, timestamp, ux_audit) in enumerate(frames_data, 1):
                # Add frame section header
                story.append(Paragraph(f"Screen {idx} Analysis", self.styles['FrameTitle']))
                story.append(Spacer(1, 10))
                
                # Add frame timestamp
                story.append(Paragraph(f"Timestamp: {timestamp}", self.styles['Metadata']))
                story.append(Spacer(1, 8))
                
                # Add screen title from UX audit
                if ux_audit.short_title:
                    story.append(Paragraph(f"Screen: {ux_audit.short_title}", self.styles['ScreenTitle']))
                    story.append(Spacer(1, 10))
                
                # Add frame image
                if os.path.exists(frame_path):
                    try:
                        # Calculate image dimensions
                        max_width = self.page_size[0] - 1.5*inch  # Account for margins
                        max_height = 4.5*inch  # Maximum height for images
                        
                        width, height = self._resize_image_if_needed(
                            frame_path, max_width, max_height
                        )
                        
                        # Add image with border
                        img = Image(frame_path, width=width, height=height)
                        story.append(img)
                        story.append(Spacer(1, 15))
                    except Exception as e:
                        logger.warning(f"Could not add image {frame_path} to PDF: {e}")
                        story.append(Paragraph(f"[Image not available: {os.path.basename(frame_path)}]", 
                                             self.styles['Metadata']))
                        story.append(Spacer(1, 15))
                else:
                    story.append(Paragraph(f"[Image not found: {os.path.basename(frame_path)}]", 
                                         self.styles['Metadata']))
                    story.append(Spacer(1, 15))
                
                # Add UX summary
                if ux_audit.summary:
                    story.append(Paragraph("UX Summary", self.styles['SectionHeading']))
                    story.append(Paragraph(ux_audit.summary, self.styles['Summary']))
                    story.append(Spacer(1, 15))
                
                # Add issues section
                story.append(Paragraph("Issues & Recommendations", self.styles['SectionHeading']))
                
                if ux_audit.issues:
                    # Add each issue individually for better formatting
                    for issue_idx, issue in enumerate(ux_audit.issues, 1):
                        story.append(Paragraph(f"{issue_idx}. {issue.issue_title}", self.styles['IssueTitle']))
                        story.append(Paragraph(f"<b>Issue:</b> {issue.issue}", self.styles['IssueDescription']))
                        story.append(Paragraph(f"<b>Recommendation:</b> {issue.recommendation}", self.styles['Recommendation']))
                        story.append(Spacer(1, 10))
                else:
                    story.append(Paragraph("✓ No issues identified for this screen.", self.styles['NoIssues']))
                    story.append(Spacer(1, 15))
                
                # Add page break between frames (except for the last one)
                if idx < len(frames_data):
                    story.append(PageBreak())
            
            # Build PDF
            doc.build(story)
            
            logger.info(f"Structured UX audit PDF report generated successfully: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error generating structured UX audit PDF report: {e}")
            raise
    
    def generate_pdf_from_audit_data(
        self,
        audit_data: List[Tuple[str, str, UXAudit]],  # (frame_path, timestamp, ux_audit)
        output_directory: str,
        filename: Optional[str] = None
    ) -> str:
        """
        Generate a PDF report and save it to a specified directory.
        
        Args:
            audit_data (List[Tuple[str, str, UXAudit]]): List of (frame_path, timestamp, ux_audit)
            output_directory (str): Directory where the PDF will be saved
            filename (Optional[str]): Custom filename for the PDF
            
        Returns:
            str: Path to the generated PDF file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ux_audit_report_{timestamp}.pdf"
        
        if not filename.endswith('.pdf'):
            filename += '.pdf'
        
        output_path = os.path.join(output_directory, filename)
        
        total_issues = sum(len(ux_audit.issues) for _, _, ux_audit in audit_data)
        
        return self.generate_pdf(
            frames_data=audit_data,
            output_path=output_path,
            title="UX Audit Report",
            subtitle=f"Analysis of {len(audit_data)} screens with {total_issues} issues identified"
        ) 