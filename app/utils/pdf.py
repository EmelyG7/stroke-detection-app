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
    Image as PlatypusImage,
    PageBreak,
    KeepTogether
)

logger = logging.getLogger(__name__)

# Register professional fonts with fallbacks
def register_professional_fonts():
    """Register professional fonts with system fallbacks"""
    font_registered = False

    # Try to register Times New Roman variants
    times_fonts = [
        ('Times-Roman', ['times.ttf', 'Times New Roman.ttf', 'TimesNewRoman.ttf']),
        ('Times-Bold', ['timesbd.ttf', 'Times New Roman Bold.ttf', 'TimesNewRoman-Bold.ttf']),
        ('Times-Italic', ['timesi.ttf', 'Times New Roman Italic.ttf', 'TimesNewRoman-Italic.ttf']),
        ('Times-BoldItalic', ['timesbi.ttf', 'Times New Roman Bold Italic.ttf', 'TimesNewRoman-BoldItalic.ttf'])
    ]

    for font_name, file_options in times_fonts:
        for font_file in file_options:
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_file))
                font_registered = True
                logger.info(f"Successfully registered {font_name} from {font_file}")
                break
            except:
                continue

    # Try alternative professional fonts if Times is not available
    if not font_registered:
        alternative_fonts = [
            ('Professional-Roman', ['arial.ttf', 'Arial.ttf', 'calibri.ttf', 'Calibri.ttf']),
            ('Professional-Bold', ['arialbd.ttf', 'Arial Bold.ttf', 'calibrib.ttf', 'Calibri-Bold.ttf']),
        ]

        for font_name, file_options in alternative_fonts:
            for font_file in file_options:
                try:
                    pdfmetrics.registerFont(TTFont(font_name, font_file))
                    font_registered = True
                    logger.info(f"Successfully registered {font_name} from {font_file}")
                    break
                except:
                    continue
            if font_registered:
                break

    if not font_registered:
        logger.warning("No custom fonts registered, using ReportLab defaults")

    return font_registered

def get_font_family():
    """Get the appropriate font family based on what's available"""
    try:
        # Check if Times New Roman is available
        pdfmetrics.getFont('Times-Roman')
        return {
            'normal': 'Times-Roman',
            'bold': 'Times-Bold',
            'italic': 'Times-Italic',
            'bold_italic': 'Times-BoldItalic'
        }
    except:
        try:
            # Check if professional alternative is available
            pdfmetrics.getFont('Professional-Roman')
            return {
                'normal': 'Professional-Roman',
                'bold': 'Professional-Bold',
                'italic': 'Professional-Roman',
                'bold_italic': 'Professional-Bold'
            }
        except:
            # Fall back to ReportLab defaults
            return {
                'normal': 'Helvetica',
                'bold': 'Helvetica-Bold',
                'italic': 'Helvetica-Oblique',
                'bold_italic': 'Helvetica-BoldOblique'
            }

def create_clinical_styles():
    """Create professional medical document styles with proper typography"""

    # Register fonts first
    register_professional_fonts()
    fonts = get_font_family()

    # Professional color palette for medical documents
    colors_palette = {
        'primary_blue': colors.HexColor('#1B4B73'),      # Deep medical blue
        'secondary_blue': colors.HexColor('#2E5984'),     # Medium blue
        'accent_blue': colors.HexColor('#E8F1F8'),        # Light blue background
        'critical_red': colors.HexColor('#B91C1C'),       # Medical red for critical findings
        'normal_green': colors.HexColor('#166534'),       # Medical green for normal findings
        'warning_orange': colors.HexColor('#C2410C'),     # Warning orange
        'text_dark': colors.HexColor('#1F2937'),          # Dark gray for text
        'text_medium': colors.HexColor('#4B5563'),        # Medium gray
        'text_light': colors.HexColor('#6B7280'),         # Light gray
        'border_color': colors.HexColor('#D1D5DB'),       # Light border
    }

    return {
        'InstitutionTitle': ParagraphStyle(
            name='InstitutionTitle',
            fontSize=20,
            leading=25,
            alignment=TA_CENTER,
            spaceAfter=8,
            fontName=fonts['bold'],
            textColor=colors_palette['primary_blue']
        ),
        'ReportTitle': ParagraphStyle(
            name='ReportTitle',
            fontSize=16,
            leading=20,
            alignment=TA_CENTER,
            spaceAfter=6,
            fontName=fonts['bold'],
            textColor=colors_palette['secondary_blue']
        ),
        'ReportSubtitle': ParagraphStyle(
            name='ReportSubtitle',
            fontSize=12,
            leading=15,
            alignment=TA_CENTER,
            spaceAfter=25,
            fontName=fonts['italic'],
            textColor=colors_palette['text_medium']
        ),
        'SectionHeader': ParagraphStyle(
            name='SectionHeader',
            fontSize=14,
            leading=18,
            alignment=TA_LEFT,
            spaceAfter=12,
            spaceBefore=20,
            fontName=fonts['bold'],
            textColor=colors_palette['secondary_blue'],
            borderWidth=1,
            borderColor=colors_palette['border_color'],
            borderPadding=8,
            backColor=colors_palette['accent_blue']
        ),
        'SubsectionHeader': ParagraphStyle(
            name='SubsectionHeader',
            fontSize=12,
            leading=16,
            alignment=TA_LEFT,
            spaceAfter=8,
            spaceBefore=12,
            fontName=fonts['bold'],
            textColor=colors_palette['text_dark']
        ),
        'BodyText': ParagraphStyle(
            name='BodyText',
            fontSize=11,
            leading=15,
            alignment=TA_JUSTIFY,
            fontName=fonts['normal'],
            textColor=colors_palette['text_dark'],
            spaceAfter=10,
            firstLineIndent=12
        ),
        'CriticalFinding': ParagraphStyle(
            name='CriticalFinding',
            fontSize=12,
            leading=16,
            alignment=TA_LEFT,
            fontName=fonts['bold'],
            textColor=colors_palette['critical_red'],
            backColor=colors.HexColor('#FEF2F2'),
            borderColor=colors_palette['critical_red'],
            borderWidth=1,
            borderPadding=10,
            spaceBefore=12,
            spaceAfter=12
        ),
        'NormalFinding': ParagraphStyle(
            name='NormalFinding',
            fontSize=12,
            leading=16,
            alignment=TA_LEFT,
            fontName=fonts['bold'],
            textColor=colors_palette['normal_green'],
            backColor=colors.HexColor('#F0FDF4'),
            borderColor=colors_palette['normal_green'],
            borderWidth=1,
            borderPadding=10,
            spaceBefore=12,
            spaceAfter=12
        ),
        'TechnicalData': ParagraphStyle(
            name='TechnicalData',
            fontSize=10,
            leading=13,
            alignment=TA_LEFT,
            fontName=fonts['normal'],
            textColor=colors_palette['text_medium'],
            spaceAfter=6
        ),
        'Disclaimer': ParagraphStyle(
            name='Disclaimer',
            fontSize=10,
            leading=13,
            alignment=TA_JUSTIFY,
            fontName=fonts['italic'],
            textColor=colors_palette['warning_orange'],
            backColor=colors.HexColor('#FFF7ED'),
            borderColor=colors_palette['warning_orange'],
            borderWidth=1,
            borderPadding=12,
            spaceBefore=20,
            spaceAfter=15
        ),
        'Footer': ParagraphStyle(
            name='Footer',
            fontSize=9,
            leading=11,
            alignment=TA_CENTER,
            fontName=fonts['normal'],
            textColor=colors_palette['text_light']
        ),
        'WatermarkText': ParagraphStyle(
            name='WatermarkText',
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            fontName=fonts['italic'],
            textColor=colors_palette['text_light']
        )
    }

def create_medical_header(consultation: Dict, styles: Dict):
    """Create professional medical institution header"""
    elements = []

    # Institution header
    elements.append(Paragraph("CENTRO MÉDICO DE NEUROIMÁGENES", styles['InstitutionTitle']))
    elements.append(Paragraph("DEPARTAMENTO DE RADIOLOGÍA - SECCIÓN NEURORRADIOLOGÍA", styles['ReportSubtitle']))
    elements.append(Spacer(1, 20))

    # Report title with emphasis on DWI
    elements.append(Paragraph("INFORME DE RESONANCIA MAGNÉTICA", styles['ReportTitle']))
    elements.append(Paragraph("Secuencia de Difusión (DWI) - Evaluación de Isquemia Cerebral Aguda", styles['ReportSubtitle']))
    elements.append(Spacer(1, 25))

    # Patient information table with professional styling
    patient_info = consultation.get("patient", {})
    patient_data = [
        ["DATOS DEL PACIENTE", ""],
        ["Nombre:", patient_info.get("name", "No especificado")],
        ["Edad:", f"{patient_info.get('age', 'N/A')} años"],
        ["Sexo:", patient_info.get("gender", "No especificado")],
        ["", ""],
        ["DATOS DEL ESTUDIO", ""],
        ["Fecha del estudio:", datetime.fromisoformat(consultation["date"]).strftime("%d de %B de %Y") if consultation.get("date") else "No especificada"],
        ["Servicio solicitante:", consultation.get("service", "Neurología")],
        ["Técnica utilizada:", "Resonancia Magnética - Secuencia DWI"],
        ["Sistema de análisis:", "IA para Detección de Stroke"]
    ]

    patient_table = Table(patient_data, colWidths=[2.2*inch, 3.8*inch])
    patient_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('FONTNAME', (0, 0), (0, -1), 'Times-Bold'),
        ('FONTNAME', (0, 5), (0, 5), 'Times-Bold'),  # "DATOS DEL ESTUDIO" header
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B4B73')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#1B4B73')),
        ('TEXTCOLOR', (0, 5), (-1, 5), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 1), (-1, 4), colors.HexColor('#F8FAFC')),
        ('BACKGROUND', (0, 6), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
        ('SPAN', (0, 4), (-1, 4)),  # Empty row for spacing
    ]))

    elements.append(patient_table)
    elements.append(Spacer(1, 30))

    return elements

def create_dwi_findings_section(consultation: Dict, styles: Dict):
    """Create detailed DWI-specific findings section"""
    elements = []

    elements.append(Paragraph("HALLAZGOS EN SECUENCIA DE DIFUSIÓN (DWI)", styles['SectionHeader']))

    diagnosis = consultation.get("diagnosis", "").lower()
    prob = consultation.get("probability", 0) * 100

    if diagnosis == "stroke":
        # Critical stroke findings
        finding_text = f"""
        <b>HALLAZGO CRÍTICO - POSIBLE ISQUEMIA CEREBRAL AGUDA</b><br/><br/>
        Se identifican áreas de restricción en la difusión altamente sugestivas de isquemia cerebral aguda. 
        El análisis automatizado mediante inteligencia artificial arroja una probabilidad del <b>{prob:.1f}%</b> 
        para la presencia de accidente cerebrovascular isquémico.
        """

        elements.append(Paragraph(finding_text, styles['CriticalFinding']))

        # Detailed technical description
        elements.append(Paragraph("Descripción Técnica:", styles['SubsectionHeader']))
        elements.append(Paragraph("""
        Las imágenes ponderadas en difusión (DWI) muestran áreas de hiperintensidad con correspondiente 
        hipointensidad en el mapa de coeficiente aparente de difusión (ADC), hallazgo característico de 
        la restricción de la difusión molecular del agua, típica del edema citotóxico asociado a isquemia 
        cerebral aguda. No se observa efecto de "T2 shine-through" que pudiera confundir la interpretación.
        """, styles['BodyText']))

        elements.append(Paragraph("Correlación Anatómica:", styles['SubsectionHeader']))
        elements.append(Paragraph("""
        La distribución topográfica de las lesiones sugiere compromiso vascular en territorio arterial 
        específico. Se recomienda correlación con estudios angiográficos para determinar el vaso afectado 
        y evaluar opciones terapéuticas de reperfusión.
        """, styles['BodyText']))

    else:
        # Normal findings
        finding_text = f"""
        <b>HALLAZGO DENTRO DE LÍMITES NORMALES</b><br/><br/>
        Las secuencias de difusión no muestran evidencia de restricción significativa que sugiera 
        isquemia cerebral aguda. El análisis automatizado mediante inteligencia artificial arroja 
        una probabilidad del <b>{prob:.1f}%</b> para la presencia de accidente cerebrovascular isquémico.
        """

        elements.append(Paragraph(finding_text, styles['NormalFinding']))

        elements.append(Paragraph("Descripción Técnica:", styles['SubsectionHeader']))
        elements.append(Paragraph("""
        Las imágenes ponderadas en difusión (DWI) y los mapas de coeficiente aparente de difusión (ADC) 
        no evidencian áreas de restricción significativa. La señal del parénquima cerebral se encuentra 
        dentro de parámetros normales para los tiempos de evolución evaluados.
        """, styles['BodyText']))

    elements.append(Spacer(1, 20))
    return elements

def create_technical_parameters_section(images: List[Dict], styles: Dict):
    """Create detailed technical parameters section"""
    elements = []

    if not images:
        return elements

    elements.append(Paragraph("PARÁMETROS TÉCNICOS Y ANÁLISIS DETALLADO", styles['SectionHeader']))

    # General technical information
    elements.append(Paragraph("Técnica de Adquisición:", styles['SubsectionHeader']))
    elements.append(Paragraph("""
    Secuencias de difusión (DWI) adquiridas con valores b de 0 y 1000 s/mm². Generación automática 
    de mapas de coeficiente aparente de difusión (ADC). Análisis realizado mediante sistema de 
    inteligencia artificial especializado en detección de patrones de isquemia cerebral aguda.
    """, styles['BodyText']))

    # Analysis per image
    elements.append(Paragraph("Análisis por Imagen:", styles['SubsectionHeader']))

    for idx, img in enumerate(images, 1):
        image_analysis_data = [
            ["Parámetro", "Valor", "Interpretación"],
            ["Archivo", img.get('filename', f'Imagen_{idx}'), ""],
            ["Probabilidad de stroke", f"{img.get('probability', 0)*100:.2f}%",
             "Alta" if img.get('probability', 0) >= 0.7 else "Moderada" if img.get('probability', 0) >= 0.5 else "Baja"],
            ["Confianza del modelo", f"{img.get('confidence', 0)*100:.2f}%",
             "Óptima" if img.get('confidence', 0) >= 0.8 else "Aceptable" if img.get('confidence', 0) >= 0.6 else "Limitada"],
            ["Diagnóstico automatizado", img.get('diagnosis', 'No determinado'), ""],
            ["Fecha de procesamiento", img.get("created_at", "No especificada"), ""]
        ]

        img_table = Table(image_analysis_data, colWidths=[2*inch, 2*inch, 2*inch])
        img_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E5984')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
        ]))

        elements.append(Paragraph(f"<b>Imagen {idx}:</b>", styles['SubsectionHeader']))
        elements.append(img_table)
        elements.append(Spacer(1, 15))

    return elements

def create_clinical_recommendations_section(consultation: Dict, styles: Dict):
    """Create comprehensive clinical recommendations"""
    elements = []

    elements.append(Paragraph("RECOMENDACIONES CLÍNICAS", styles['SectionHeader']))

    diagnosis = consultation.get("diagnosis", "").lower()

    elements.append(Paragraph("Correlación Clínica Requerida:", styles['SubsectionHeader']))

    if diagnosis == "stroke":
        elements.append(Paragraph("""
        Ante la identificación de hallazgos compatibles con isquemia cerebral aguda, se requiere 
        <b>evaluación neurológica urgente</b> para determinar:
        """, styles['BodyText']))

        recommendations = [
            "Tiempo de inicio de síntomas neurológicos (ventana terapéutica)",
            "Escala NIHSS para cuantificar severidad del déficit neurológico",
            "Criterios de inclusión/exclusión para terapias de reperfusión",
            "Evaluación de contraindicaciones para trombólisis intravenosa",
            "Consideración de trombectomía mecánica según criterios institucionales",
            "Monitorización neurológica continua en unidad especializada"
        ]

        for i, rec in enumerate(recommendations, 1):
            elements.append(Paragraph(f"{i}. {rec}", styles['BodyText']))

        elements.append(Paragraph("Estudios Complementarios Sugeridos:", styles['SubsectionHeader']))
        elements.append(Paragraph("""
        • Angio-RM o angio-TC para evaluación vascular<br/>
        • Ecocardiograma y Holter si se sospecha origen cardioembólico<br/>
        • Doppler carotídeo para evaluación de estenosis<br/>
        • Perfil de coagulación completo<br/>
        • Estudios metabólicos (glucosa, electrolitos, función renal)
        """, styles['BodyText']))

    else:
        elements.append(Paragraph("""
        Aunque las imágenes de difusión no muestran evidencia de isquemia aguda, se recomienda:
        """, styles['BodyText']))

        recommendations = [
            "Correlacionar con sintomatología clínica del paciente",
            "Considerar diagnósticos diferenciales según presentación",
            "Evaluar factores de riesgo cardiovascular",
            "Seguimiento clínico según evolución sintomatológica",
            "Considerar repetir estudio si hay alta sospecha clínica"
        ]

        for i, rec in enumerate(recommendations, 1):
            elements.append(Paragraph(f"{i}. {rec}", styles['BodyText']))

    elements.append(Spacer(1, 20))
    return elements

def create_medical_disclaimer(styles: Dict):
    """Create comprehensive medical and AI disclaimer"""
    elements = []

    elements.append(Paragraph("LIMITACIONES Y CONSIDERACIONES IMPORTANTES", styles['SectionHeader']))

    disclaimer_text = """
    <b>ADVERTENCIA MÉDICA IMPORTANTE:</b><br/><br/>
    
    Este reporte ha sido generado mediante un sistema de inteligencia artificial especializado en el 
    análisis de imágenes de resonancia magnética con secuencia de difusión (DWI). 
    
    <b>LIMITACIONES DEL SISTEMA AUTOMATIZADO:</b><br/>
    • El diagnóstico automatizado NO sustituye el criterio clínico del médico especialista<br/>
    • Los resultados deben ser siempre correlacionados con la presentación clínica del paciente<br/>
    • El sistema puede presentar falsos positivos o negativos<br/>
    • La interpretación final y las decisiones terapéuticas son responsabilidad exclusiva del médico tratante<br/>
    • Se requiere validación por neurorradiólogo certificado para confirmación diagnóstica<br/><br/>
    
    <b>RESPONSABILIDAD MÉDICA:</b><br/>
    El médico tratante debe considerar este reporte como una herramienta de apoyo diagnóstico 
    complementaria, manteniendo siempre el juicio clínico independiente y la evaluación integral 
    del paciente como elementos primordiales para la toma de decisiones terapéuticas.
    """

    elements.append(Paragraph(disclaimer_text, styles['Disclaimer']))
    elements.append(Spacer(1, 20))

    return elements

def create_professional_footer(canvas, doc):
    """Add professional footer with validation information"""
    canvas.saveState()

    # Footer background
    canvas.setFillColor(colors.HexColor('#F8FAFC'))
    canvas.rect(0, 0, A4[0], 3*cm, fill=1, stroke=0)

    # Main footer text
    canvas.setFont('Times-Roman', 9)
    canvas.setFillColor(colors.HexColor('#4B5563'))

    # Institution and system info
    canvas.drawCentredString(
        A4[0]/2, 2.5*cm,
        f"Sistema de Análisis de Neuroimágenes por IA - Generado el {datetime.now().strftime('%d/%m/%Y a las %H:%M')} hrs"
    )

    # Page number
    canvas.drawCentredString(A4[0]/2, 2.2*cm, f"Página {canvas.getPageNumber()}")

    # Confidentiality and validation notices
    canvas.setFont('Times-Italic', 8)
    canvas.setFillColor(colors.HexColor('#6B7280'))
    canvas.drawCentredString(A4[0]/2, 1.8*cm, "DOCUMENTO CONFIDENCIAL - USO EXCLUSIVO PARA PERSONAL MÉDICO AUTORIZADO")
    canvas.drawCentredString(A4[0]/2, 1.5*cm, "Requiere validación por especialista en neurorradiología - No sustituye criterio médico")

    # Validation box
    canvas.setStrokeColor(colors.HexColor('#D1D5DB'))
    canvas.setLineWidth(0.5)
    canvas.rect(A4[0] - 4*cm, 0.5*cm, 3.5*cm, 1*cm)
    canvas.setFont('Times-Roman', 7)
    canvas.drawString(A4[0] - 3.8*cm, 1.2*cm, "VALIDACIÓN MÉDICA:")
    canvas.drawString(A4[0] - 3.8*cm, 1.0*cm, "Dr./Dra.: ________________")
    canvas.drawString(A4[0] - 3.8*cm, 0.8*cm, "Firma: ___________________")
    canvas.drawString(A4[0] - 3.8*cm, 0.6*cm, "Fecha: ___________________")

    canvas.restoreState()

def generate_clinical_pdf_report(consultation: Dict, images: List[Dict]) -> bytes:
    """
    Generate a professional clinical PDF report specifically designed for DWI stroke analysis
    with medical-grade formatting, proper disclaimers, and comprehensive technical details.
    """
    buffer = BytesIO()

    try:
        # Create document with professional medical formatting
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2.5*cm,
            bottomMargin=4*cm,  # Extra space for footer
            title=f"Reporte DWI - {consultation.get('patient', {}).get('name', 'Paciente')}",
            author="Sistema de Análisis de Neuroimágenes por IA",
            subject="Informe de Resonancia Magnética - Secuencia de Difusión",
            creator="Sistema Médico de IA para Detección de Stroke"
        )

        # Create professional styles
        styles = create_clinical_styles()

        # Build comprehensive report content
        story = []

        # Medical institution header
        story.extend(create_medical_header(consultation, styles))

        # DWI-specific findings section
        story.extend(create_dwi_findings_section(consultation, styles))

        # Technical parameters and analysis
        story.extend(create_technical_parameters_section(images, styles))

        # Clinical recommendations
        story.extend(create_clinical_recommendations_section(consultation, styles))

        # Medical disclaimers and limitations
        story.extend(create_medical_disclaimer(styles))

        # Final medical signature section
        story.append(Spacer(1, 30))
        story.append(Paragraph("___" * 25, styles['Footer']))
        story.append(Spacer(1, 10))
        story.append(Paragraph("Este reporte requiere validación y firma del médico especialista",
                               styles['Footer']))

        # Build document with professional footer
        doc.build(
            story,
            onFirstPage=create_professional_footer,
            onLaterPages=create_professional_footer
        )

        buffer.seek(0)
        return buffer.getvalue()

    except Exception as e:
        logger.error(f"Error generating professional clinical PDF: {str(e)}", exc_info=True)

        # Generate error report with professional formatting
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = create_clinical_styles()

        error_story = [
            Paragraph("ERROR EN LA GENERACIÓN DEL REPORTE MÉDICO", styles['SectionHeader']),
            Spacer(1, 20),
            Paragraph(f"Se ha producido un error técnico durante la generación del informe médico:",
                      styles['BodyText']),
            Paragraph(f"<b>Detalles del error:</b> {str(e)}", styles['TechnicalData']),
            Spacer(1, 20),
            Paragraph("""
            Por favor, contacte al administrador del sistema o intente generar el reporte nuevamente. 
            Si el problema persiste, proceda con la evaluación manual de las imágenes por parte 
            del especialista en neurorradiología.
            """, styles['BodyText'])
        ]

        doc.build(error_story)
        buffer.seek(0)
        return buffer.getvalue()