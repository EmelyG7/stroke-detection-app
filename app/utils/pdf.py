from io import BytesIO
from datetime import datetime
from typing import Dict, List
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as PlatypusImage
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import logging

logger = logging.getLogger(__name__)

def create_custom_styles():
    """Crea estilos personalizados sin modificar la hoja de estilos global"""
    styles = {
        'Title': ParagraphStyle(
            name='CustomTitle',
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=20,
            fontName='Helvetica-Bold'
        ),
        'Subtitle': ParagraphStyle(
            name='CustomSubtitle',
            fontSize=14,
            leading=18,
            alignment=TA_LEFT,
            spaceAfter=12,
            fontName='Helvetica-Bold'
        ),
        'BodyText': ParagraphStyle(
            name='CustomBodyText',
            fontSize=12,
            leading=14,
            alignment=TA_LEFT,
            spaceAfter=12,
            fontName='Helvetica'
        ),
        'Diagnosis': ParagraphStyle(
            name='CustomDiagnosis',
            fontSize=14,
            leading=16,
            alignment=TA_LEFT,
            spaceAfter=20,
            fontName='Helvetica-Bold',
            textColor=colors.red
        ),
        'Footer': ParagraphStyle(
            name='CustomFooter',
            fontSize=10,
            alignment=TA_CENTER,
            textColor=colors.grey
        )
    }
    return styles

def generate_consultation_pdf(consultation: Dict, images: List[Dict]) -> bytes:
    """
    Generate a professional PDF report for a medical consultation
    with proper error handling and custom styles
    """
    buffer = BytesIO()

    try:
        # Initialize document with proper margins
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )

        # Create custom styles
        custom_styles = create_custom_styles()

        # Set diagnosis color based on result
        diagnosis_style = ParagraphStyle(
            name='DynamicDiagnosis',
            parent=custom_styles['Diagnosis'],
            textColor=colors.red if consultation.get("diagnosis") == "Stroke" else colors.green
        )
        custom_styles['DynamicDiagnosis'] = diagnosis_style

        elements = []

        # Title section
        elements.append(Paragraph("Medical Consultation Report", custom_styles['Title']))
        elements.append(Spacer(1, 24))

        # Patient information section
        elements.append(Paragraph("Patient Information", custom_styles['Subtitle']))

        # Safely parse date with error handling
        try:
            consult_date = datetime.strptime(consultation["date"], "%Y-%m-%d").strftime("%B %d, %Y")
        except:
            consult_date = consultation["date"]  # Fallback to raw date if parsing fails

        patient_data = [
            ["Name:", consultation["patient"].get("name", "N/A")],
            ["Age:", str(consultation["patient"].get("age", "N/A"))],
            ["Gender:", consultation["patient"].get("gender", "N/A")],
            ["Consultation Date:", consult_date],
        ]

        patient_table = Table(patient_data, colWidths=[1.5*inch, 4*inch])
        patient_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))

        elements.append(patient_table)
        elements.append(Spacer(1, 12))

        # Medical history section with safe field access
        medical_history = []
        for field in ["hypertension", "diabetes", "heart_disease", "smoker", "alcoholic"]:
            if consultation["patient"].get(field, False):
                medical_history.append(field.capitalize())

        if medical_history:
            elements.append(Paragraph("Medical History", custom_styles['Subtitle']))
            med_history_text = ", ".join(medical_history)
            elements.append(Paragraph(med_history_text, custom_styles['BodyText']))
            elements.append(Spacer(1, 12))

        # Clinical notes section
        if consultation.get("notes"):
            elements.append(Paragraph("Clinical Notes", custom_styles['Subtitle']))
            elements.append(Paragraph(consultation["notes"], custom_styles['BodyText']))
            elements.append(Spacer(1, 12))

        # Diagnosis section
        elements.append(Paragraph("Diagnosis", custom_styles['Subtitle']))
        prob = consultation.get("probability", 0) * 100
        diagnosis_text = f"{consultation.get('diagnosis', 'N/A')} (Probability: {prob:.2f}%)"
        elements.append(Paragraph(diagnosis_text, custom_styles['DynamicDiagnosis']))
        elements.append(Spacer(1, 24))

        # Image analysis section with error handling
        if images:
            elements.append(Paragraph("Image Analysis Results", custom_styles['Subtitle']))

            for img in images:
                try:
                    elements.append(Paragraph(f"Image: {img.get('filename', 'Unnamed')}", custom_styles['BodyText']))

                    # Safely parse image analysis date
                    try:
                        img_date = datetime.strptime(
                            img.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ"
                        ).strftime("%B %d, %Y %H:%M")
                    except:
                        img_date = img.get("created_at", "Date not available")

                    img_data = [
                        ["Diagnosis:", img.get("diagnosis", "N/A")],
                        ["Probability:", f"{img.get('probability', 0)*100:.2f}%"],
                        ["Confidence:", f"{img.get('confidence', 0)*100:.2f}%"],
                        ["Analysis Date:", img_date],
                    ]

                    img_table = Table(img_data, colWidths=[1.5*inch, 4*inch])
                    img_table.setStyle(TableStyle([
                        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 0), (-1, -1), 11),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ]))

                    elements.append(img_table)
                    elements.append(Spacer(1, 12))
                except Exception as img_error:
                    # Skip problematic images but continue with the rest
                    continue

        # Footer section
        elements.append(Spacer(1, 24))
        elements.append(Paragraph(
            f"Report generated on {datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')}",
            custom_styles['Footer']
        ))

        # Build the PDF document
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        # Fallback to a simple error PDF if something goes wrong
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = [
            Paragraph("Error Generating Report", styles["Heading1"]),
            Paragraph(f"An error occurred while generating the PDF report: {str(e)}", styles["BodyText"])
        ]
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()