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
from PIL import Image as PILImage
import io

# Registrar fuentes (opcional)
try:
    pdfmetrics.registerFont(TTFont('Helvetica', 'Helvetica.ttf'))
    pdfmetrics.registerFont(TTFont('Helvetica-Bold', 'Helvetica-Bold.ttf'))
except:
    pass  # Usar fuentes por defecto si no están disponibles

def generate_consultation_pdf(consultation: Dict, images: List[Dict]) -> bytes:
    """
    Generate a professional PDF report for a medical consultation

    Args:
        consultation: Dictionary with consultation data
        images: List of dictionaries with image analysis data

    Returns:
        Bytes containing the PDF file
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='Title',
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        spaceAfter=20,
        fontName='Helvetica-Bold'
    ))
    styles.add(ParagraphStyle(
        name='Subtitle',
        fontSize=14,
        leading=18,
        alignment=TA_LEFT,
        spaceAfter=12,
        fontName='Helvetica-Bold'
    ))
    styles.add(ParagraphStyle(
        name='BodyText',
        fontSize=12,
        leading=14,
        alignment=TA_LEFT,
        spaceAfter=12,
        fontName='Helvetica'
    ))
    styles.add(ParagraphStyle(
        name='Diagnosis',
        fontSize=14,
        leading=16,
        alignment=TA_LEFT,
        spaceAfter=20,
        fontName='Helvetica-Bold',
        textColor=colors.red if consultation["diagnosis"] == "Stroke" else colors.green
    ))

    elements = []

    # Título del reporte
    elements.append(Paragraph("Medical Consultation Report", styles["Title"]))
    elements.append(Spacer(1, 24))

    # Información del paciente
    elements.append(Paragraph("Patient Information", styles["Subtitle"]))

    patient_data = [
        ["Name:", consultation["patient"]["name"]],
        ["Age:", str(consultation["patient"]["age"])],
        ["Gender:", consultation["patient"]["gender"]],
        ["Consultation Date:", datetime.strptime(consultation["date"], "%Y-%m-%d").strftime("%B %d, %Y")],
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

    # Historial médico
    medical_history = []
    for field in ["hypertension", "diabetes", "heart_disease", "smoker", "alcoholic"]:
        if consultation["patient"].get(field, False):
            medical_history.append(field.capitalize())

    if medical_history:
        elements.append(Paragraph("Medical History", styles["Subtitle"]))
        med_history_text = ", ".join(medical_history)
        elements.append(Paragraph(med_history_text, styles["BodyText"]))
        elements.append(Spacer(1, 12))

    # Notas de consulta
    if consultation.get("notes"):
        elements.append(Paragraph("Clinical Notes", styles["Subtitle"]))
        elements.append(Paragraph(consultation["notes"], styles["BodyText"]))
        elements.append(Spacer(1, 12))

    # Diagnóstico
    elements.append(Paragraph("Diagnosis", styles["Subtitle"]))
    diagnosis_text = f"{consultation['diagnosis']} (Probability: {consultation['probability']*100:.2f}%)"
    elements.append(Paragraph(diagnosis_text, styles["Diagnosis"]))
    elements.append(Spacer(1, 24))

    # Resultados de imágenes
    if images:
        elements.append(Paragraph("Image Analysis Results", styles["Subtitle"]))

        for img in images:
            # Encabezado de imagen
            elements.append(Paragraph(f"Image: {img['filename']}", styles["BodyText"]))

            # Tabla de resultados
            img_data = [
                ["Diagnosis:", img["diagnosis"]],
                ["Probability:", f"{img['probability']*100:.2f}%"],
                ["Confidence:", f"{img['confidence']*100:.2f}%"],
                ["Analysis Date:", datetime.strptime(
                    img["created_at"], "%Y-%m-%dT%H:%M:%SZ"
                ).strftime("%B %d, %Y %H:%M")],
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

    # Pie de página
    elements.append(Spacer(1, 24))
    elements.append(Paragraph(
        f"Report generated on {datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')}",
        ParagraphStyle(
            name='Footer',
            fontSize=10,
            alignment=TA_CENTER,
            textColor=colors.grey
        )
    ))

    # Construir el PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()