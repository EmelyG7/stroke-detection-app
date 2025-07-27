import logging
from datetime import datetime
from io import BytesIO
from typing import Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as PlatypusImage
)

logger = logging.getLogger(__name__)

# Register professional medical fonts
try:
    pdfmetrics.registerFont(TTFont('Helvetica', 'Helvetica.ttf'))
    pdfmetrics.registerFont(TTFont('Helvetica-Bold', 'Helvetica-Bold.ttf'))
except:
    logger.warning("Professional fonts not found, falling back to defaults")

def create_clinical_styles():
    """Create styles for medical professional documentation"""
    return {
        'Title': ParagraphStyle(
            name='ClinicalTitle',
            fontSize=16,
            leading=20,
            alignment=TA_CENTER,
            spaceAfter=20,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#003366')  # Dark blue for professional look
        ),
        'Header': ParagraphStyle(
            name='ClinicalHeader',
            fontSize=14,
            leading=18,
            alignment=TA_LEFT,
            spaceAfter=12,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#003366'),
            leftIndent=0
        ),
        'Subheader': ParagraphStyle(
            name='ClinicalSubheader',
            fontSize=12,
            leading=16,
            alignment=TA_LEFT,
            spaceAfter=8,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#333333')
        ),
        'ClinicalText': ParagraphStyle(
            name='ClinicalText',
            fontSize=11,
            leading=14,
            alignment=TA_JUSTIFY,
            fontName='Helvetica',
            textColor=colors.black,
            spaceAfter=10
        ),
        'CriticalFinding': ParagraphStyle(
            name='CriticalFinding',
            fontSize=12,
            leading=15,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#990000'),  # Dark red for critical findings
            backColor=colors.HexColor('#FFEEEE'),
            borderPadding=5,
            spaceAfter=12
        ),
        'NormalFinding': ParagraphStyle(
            name='NormalFinding',
            fontSize=12,
            leading=15,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#006600'),  # Dark green for normal findings
            backColor=colors.HexColor('#EEFFEE'),
            borderPadding=5,
            spaceAfter=12
        ),
        'TechnicalData': ParagraphStyle(
            name='TechnicalData',
            fontSize=10,
            leading=12,
            alignment=TA_LEFT,
            fontName='Helvetica',
            textColor=colors.HexColor('#555555')
        ),
        'Footer': ParagraphStyle(
            name='ClinicalFooter',
            fontSize=9,
            leading=11,
            alignment=TA_CENTER,
            fontName='Helvetica',
            textColor=colors.HexColor('#666666')
        )
    }

def create_clinical_header(consultation: Dict, styles: Dict):
    """Create professional header for medical report"""
    elements = []

    # Add institution logo if available
    try:
        logo = PlatypusImage("C:/Users/Coshita/Downloads/coursera/ultimocurso/stroke-detection-backend-py/app/utils/hospital_logo.png", width=2.5*inch, height=0.7*inch)
        elements.append(logo)
        elements.append(Spacer(1, 20))
    except:
        pass

    elements.append(Paragraph("INFORME DE NEUROIMÁGENES", styles['Title']))
    elements.append(Paragraph("Sistema de Detección de Accidente Cerebrovascular", styles['ClinicalText']))
    elements.append(Spacer(1, 30))

    # Patient data table
    patient_data = [
        ["PACIENTE:", consultation["patient"].get("name", "No especificado")],
        ["EDAD/SEXO:", f"{consultation['patient'].get('age', 'N/A')} años / {consultation['patient'].get('gender', 'No especificado')}"],
        ["FECHA DE ESTUDIO:", datetime.fromisoformat(consultation["date"]).strftime("%d/%m/%Y") if consultation.get("date") else "No especificada"],
        ["SERVICIO:", consultation.get("service", "Neurología")]
    ]

    patient_table = Table(patient_data, colWidths=[2*inch, 4*inch])
    patient_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F0F5FF')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D6E0F5')),
    ]))

    elements.append(patient_table)
    elements.append(Spacer(1, 30))

    return elements

def create_imaging_findings(consultation: Dict, styles: Dict):
    """Create imaging findings section with clinical details"""
    elements = []

    elements.append(Paragraph("HALLAZGOS DE IMAGEN", styles['Header']))
    elements.append(Spacer(1, 10))

    diagnosis = consultation.get("diagnosis", "").lower()
    prob = consultation.get("probability", 0) * 100

    if diagnosis == "stroke":
        finding_style = styles['CriticalFinding']
        findings_text = f"""
        <b>HALLAZGO PRINCIPAL:</b> Se identifican alteraciones en la secuencia de difusión 
        compatibles con isquemia cerebral aguda. La probabilidad calculada por el sistema 
        es del {prob:.1f}%.
        """

        elements.append(Paragraph(findings_text, finding_style))

        elements.append(Paragraph("""
        <b>Características técnicas:</b> Las imágenes muestran restricción en la difusión 
        con correspondiente disminución en el coeficiente aparente de difusión (ADC), 
        sin efecto de T2 shine-through evidente. La distribución topográfica sugiere 
        compromiso vascular en territorio [ESPECIFICAR ARTERIA SI SE CONOCE].
        """, styles['ClinicalText']))
    else:
        finding_style = styles['NormalFinding']
        findings_text = f"""
        <b>HALLAZGO PRINCIPAL:</b> No se identifican alteraciones agudas en la secuencia 
        de difusión. La probabilidad calculada por el sistema es del {prob:.1f}%.
        """

        elements.append(Paragraph(findings_text, finding_style))

        elements.append(Paragraph("""
        <b>Características técnicas:</b> Las imágenes muestran señal de difusión 
        dentro de parámetros normales, sin evidencia de restricción significativa. 
        El coeficiente aparente de difusión (ADC) se mantiene dentro de rangos 
        esperados para parénquima cerebral sano.
        """, styles['ClinicalText']))

    elements.append(Spacer(1, 15))

    # Add clinical correlation
    elements.append(Paragraph("""
    <b>Correlación clínica:</b> Los hallazgos deben correlacionarse con la presentación 
    clínica del paciente y los resultados de otros estudios complementarios. 
    En casos de discordancia clínico-radiológica, se recomienda reevaluación.
    """, styles['ClinicalText']))

    elements.append(Spacer(1, 20))

    return elements

def create_technical_analysis(images: List[Dict], styles: Dict):
    """Create detailed technical analysis section"""
    elements = []

    if not images:
        return elements

    elements.append(Paragraph("ANÁLISIS TÉCNICO", styles['Header']))
    elements.append(Paragraph("Resultados detallados por imagen:", styles['Subheader']))
    elements.append(Spacer(1, 10))

    for idx, img in enumerate(images, 1):
        elements.append(Paragraph(f"<b>Imagen {idx}:</b> {img.get('filename', 'Imagen no identificada')}", styles['Subheader']))

        img_data = [
            ["Parámetro", "Valor"],
            ["Fecha de procesamiento", img.get("created_at", "No especificada")],
            ["Hallazgo principal", img.get("diagnosis", "No determinado")],
            ["Probabilidad calculada", f"{img.get('probability', 0)*100:.1f}%"],
            ["Confianza del modelo", f"{img.get('confidence', 0)*100:.1f}%"],
            ["Técnica de adquisición", img.get("technique", "DWI estándar")]
        ]

        img_table = Table(img_data, colWidths=[2.5*inch, 3.5*inch])
        img_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#003366')),
            ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F5F9FF')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D6E0F5')),
        ]))

        elements.append(img_table)
        elements.append(Spacer(1, 15))

    return elements

def create_clinical_recommendations(consultation: Dict, styles: Dict):
    """Create clinical recommendations for medical professionals"""
    elements = []

    elements.append(Paragraph("EVALUACIÓN CLÍNICA", styles['Header']))
    elements.append(Spacer(1, 10))

    diagnosis = consultation.get("diagnosis", "").lower()
    prob = consultation.get("probability", 0) * 100

    if diagnosis == "stroke":
        elements.append(Paragraph("""
        <b>Consideraciones para el equipo tratante:</b> Los hallazgos de imagen son 
        compatibles con evento cerebrovascular isquémico agudo. Se sugiere:
        """, styles['ClinicalText']))

        recommendations = [
            "Confirmar ventana terapéutica para posibles intervenciones de reperfusión",
            "Evaluar NIHSS y criterios para trombólisis/trombectomía",
            "Monitorización neurológica estrecha",
            "Control estricto de parámetros hemodinámicos",
            "Iniciar medidas neuroprotectoras según protocolo institucional",
            "Considerar estudios etiológicos (ECG, eco cardíaco, Doppler vascular)"
        ]
    else:
        elements.append(Paragraph("""
        <b>Consideraciones para el equipo tratante:</b> Aunque no se identifican 
        hallazgos agudos en la secuencia de difusión, se recomienda:
        """, styles['ClinicalText']))

        recommendations = [
            "Correlación con cuadro clínico y reevaluación si persiste sospecha",
            "Considerar diagnóstico diferencial según presentación",
            "Evaluar necesidad de estudios complementarios",
            "Seguimiento según evolución clínica",
            "Implementar medidas preventivas según factores de riesgo"
        ]

    # Add recommendations as bullet points
    for rec in recommendations:
        elements.append(Paragraph(f"• {rec}", styles['ClinicalText']))

    elements.append(Spacer(1, 15))

    # Add technical note
    elements.append(Paragraph("""
    <b>Nota técnica:</b> Este reporte ha sido generado mediante sistema de inteligencia 
    artificial especializado en neuroimágenes. La interpretación final y las decisiones 
    terapéuticas corresponden al médico tratante, quien debe considerar el contexto 
    clínico integral del paciente.
    """, styles['TechnicalData']))

    elements.append(Spacer(1, 20))

    return elements

def create_clinical_footer(canvas, doc):
    """Add professional footer to each page"""
    canvas.saveState()
    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(colors.HexColor('#666666'))

    # Footer text
    canvas.drawCentredString(
        A4[0]/2,
        2*cm,
        f"Generado por Sistema de Análisis de Neuroimágenes - {datetime.now().strftime('%d/%m/%Y %H:%M')} - Página {canvas.getPageNumber()}"
    )

    # Confidentiality notice
    canvas.setFont('Helvetica-Oblique', 8)
    canvas.drawCentredString(A4[0]/2, 1.7*cm, "Documento de uso exclusivo para personal médico")
    canvas.restoreState()

def generate_clinical_pdf_report(consultation: Dict, images: List[Dict]) -> bytes:
    """
    Generate a professional clinical PDF report for medical professionals with:
    - Clinical header with patient data
    - Imaging findings with technical details
    - Detailed image analysis
    - Clinical recommendations
    - Professional formatting
    """
    buffer = BytesIO()

    try:
        # Create document with clinical formatting
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=2*cm,
            bottomMargin=2.5*cm,
            title=f"Reporte Clínico - {consultation.get('patient', {}).get('name', '')}",
            author="Sistema de Análisis de Neuroimágenes"
        )

        # Create clinical styles
        styles = create_clinical_styles()

        # Build report content
        story = []

        # Add clinical header
        story.extend(create_clinical_header(consultation, styles))

        # Add imaging findings
        story.extend(create_imaging_findings(consultation, styles))

        # Add technical analysis
        story.extend(create_technical_analysis(images, styles))

        # Add clinical recommendations
        story.extend(create_clinical_recommendations(consultation, styles))

        # Add final notation
        story.append(Paragraph("***", ParagraphStyle(name='Divider', fontSize=14, alignment=TA_CENTER)))
        story.append(Spacer(1, 15))
        # Build document with footer
        doc.build(
            story,
            onFirstPage=create_clinical_footer,
            onLaterPages=create_clinical_footer
        )

        buffer.seek(0)
        return buffer.getvalue()

    except Exception as e:
        logger.error(f"Error generating clinical PDF: {str(e)}", exc_info=True)
        # Fallback to simple error report
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = create_clinical_styles()
        story = [
            Paragraph("Error en Generación de Reporte", styles['Header']),
            Paragraph(f"Se produjo un error técnico al generar el PDF: {str(e)}", styles['ClinicalText'])
        ]
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()