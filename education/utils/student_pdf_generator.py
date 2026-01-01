"""
Student PDF Generator Utility
Generates PDFs for students (Results, Registered Units, Fee Structure) using ReportTemplate
"""
import os
from django.conf import settings
from django.utils import timezone
from reportlab.lib.pagesizes import A4, A3, A5, LETTER
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from io import BytesIO
from decimal import Decimal


# Page size mapping
PAGE_SIZES = {
    'A4': A4,
    'A3': A3,
    'A5': A5,
    'Letter': LETTER,
}

# Page dimensions in points (for ReportLab)
PAGE_DIMENSIONS_POINTS = {
    'A4': (595.28, 841.89),
    'A3': (841.89, 1190.55),
    'A5': (419.53, 595.28),
    'Letter': (612, 792),
}


def get_template_for_report_type(college, report_type):
    """
    Get the template for a specific report type using ReportTemplateMapping
    
    Args:
        college: College instance
        report_type: Type of report ('transcript', 'fee_structure', 'exam_card')
    
    Returns:
        ReportTemplate instance or None
    """
    from ..models import ReportTemplateMapping
    
    # Get or create mapping for this college
    mapping, created = ReportTemplateMapping.objects.get_or_create(college=college)
    
    # Get template for the specific report type
    template = mapping.get_template_for_report_type(report_type)
    
    return template


def generate_student_results_pdf(student, template, academic_year=None, semester=None):
    """
    Generate Results PDF for a student using ReportTemplate
    
    Args:
        student: Student instance
        template: ReportTemplate instance
        academic_year: Optional academic year filter
        semester: Optional semester filter
    
    Returns:
        BytesIO: PDF file as BytesIO object
    """
    from ..models import Enrollment, Result
    
    # Get student results
    enrollments = Enrollment.objects.filter(student=student, exam_registered=True)
    
    if academic_year:
        enrollments = enrollments.filter(academic_year=academic_year)
    if semester:
        enrollments = enrollments.filter(semester=int(semester))
    
    enrollments = enrollments.select_related('unit', 'result').order_by('academic_year', 'semester', 'unit__code')
    
    # Prepare results data
    results = []
    for enrollment in enrollments:
        try:
            result = enrollment.result
            grade = enrollment.unit.college.calculate_grade(float(result.total)) if result.total else None
            results.append({
                'unit_code': enrollment.unit.code,
                'unit_name': enrollment.unit.name,
                'academic_year': enrollment.academic_year,
                'semester': enrollment.semester,
                'cat_marks': float(result.cat_marks) if result.cat_marks else None,
                'exam_marks': float(result.exam_marks) if result.exam_marks else None,
                'total_marks': float(result.total) if result.total else None,
                'grade': grade
            })
        except Result.DoesNotExist:
            results.append({
                'unit_code': enrollment.unit.code,
                'unit_name': enrollment.unit.name,
                'academic_year': enrollment.academic_year,
                'semester': enrollment.semester,
                'cat_marks': None,
                'exam_marks': None,
                'total_marks': None,
                'grade': None
            })
    
    # Prepare data context
    data = {
        'student': {
            'full_name': student.full_name,
            'admission_number': student.admission_number,
            'course_name': student.course.name if student.course else 'N/A',
            'year_of_study': student.year_of_study,
        },
        'college': {
            'name': student.college.name,
            'address': getattr(student.college, 'address', '') or '',
        },
        'results': results,
        'academic_year': academic_year or 'All',
        'semester': semester or 'All',
        'generation_date': timezone.now().strftime('%Y-%m-%d')
    }
    
    return _create_pdf_from_template(template, data, 'results')


def generate_student_registered_units_pdf(student, template, academic_year=None, semester=None):
    """
    Generate Registered Units (Exam Card) PDF for a student using ReportTemplate
    
    Args:
        student: Student instance
        template: ReportTemplate instance
        academic_year: Optional academic year filter
        semester: Optional semester filter
    
    Returns:
        BytesIO: PDF file as BytesIO object
    """
    from ..models import Enrollment
    
    # Get registered units
    enrollments = Enrollment.objects.filter(student=student, exam_registered=True)
    
    if academic_year:
        enrollments = enrollments.filter(academic_year=academic_year)
    if semester:
        enrollments = enrollments.filter(semester=int(semester))
    
    enrollments = enrollments.select_related('unit').order_by('academic_year', 'semester', 'unit__code')
    
    # Prepare units data
    units = []
    for enrollment in enrollments:
        units.append({
            'unit_code': enrollment.unit.code,
            'unit_name': enrollment.unit.name,
            'academic_year': enrollment.academic_year,
            'semester': enrollment.semester,
            'exam_registered_at': enrollment.exam_registered_at.strftime('%Y-%m-%d') if enrollment.exam_registered_at else 'N/A',
        })
    
    # Prepare data context
    data = {
        'student': {
            'full_name': student.full_name,
            'admission_number': student.admission_number,
            'course_name': student.course.name if student.course else 'N/A',
            'year_of_study': student.year_of_study,
        },
        'college': {
            'name': student.college.name,
            'address': getattr(student.college, 'address', '') or '',
        },
        'units': units,
        'academic_year': academic_year or 'All',
        'semester': semester or 'All',
        'generation_date': timezone.now().strftime('%Y-%m-%d')
    }
    
    return _create_pdf_from_template(template, data, 'registered_units')


def generate_student_fee_structure_pdf(student, template):
    """
    Generate Fee Structure PDF for a student using ReportTemplate
    
    Args:
        student: Student instance
        template: ReportTemplate instance
    
    Returns:
        BytesIO: PDF file as BytesIO object
    """
    from accounts.models import CourseFeeStructure
    from accounts.views import calculate_expected_fees
    
    # Get fee breakdown
    fee_info = calculate_expected_fees(student)
    fee_breakdown = fee_info.get('fee_breakdown', {})
    
    # Prepare fee items data
    fee_items = []
    total_expected = Decimal('0.00')
    
    for sem_num in sorted(fee_breakdown.keys()):
        sem_data = fee_breakdown[sem_num]
        sem_total = sem_data.get('amount', Decimal('0.00'))
        total_expected += sem_total
        
        # Get fee structures for this semester
        fee_structures = sem_data.get('fee_structures', [])
        
        for fee_struct in fee_structures:
            fee_items.append({
                'semester': sem_num,
                'fee_type': fee_struct.get('fee_type', 'N/A'),
                'amount': float(fee_struct.get('amount', 0)),
            })
    
    # Prepare data context
    data = {
        'student': {
            'full_name': student.full_name,
            'admission_number': student.admission_number,
            'course_name': student.course.name if student.course else 'N/A',
            'year_of_study': student.year_of_study,
        },
        'college': {
            'name': student.college.name,
            'address': getattr(student.college, 'address', '') or '',
        },
        'fee_items': fee_items,
        'total_expected': float(total_expected),
        'generation_date': timezone.now().strftime('%Y-%m-%d')
    }
    
    return _create_pdf_from_template(template, data, 'fee_structure')


def _create_pdf_from_template(template, data, report_type):
    """
    Create PDF from ReportTemplate using elements configuration.
    This function ensures all template elements (logos, headers, footers, text blocks)
    are rendered first, then dynamic data is merged into placeholders and table regions.
    
    Args:
        template: ReportTemplate instance
        data: Dictionary with student, college, and report-specific data
        report_type: Type of report ('results', 'registered_units', 'fee_structure')
    
    Returns:
        BytesIO: PDF file as BytesIO object
    """
    # Get page size
    page_size_str = getattr(template, 'page_size', 'A4')
    page_size = PAGE_SIZES.get(page_size_str, A4)
    page_width_pts, page_height_pts = PAGE_DIMENSIONS_POINTS.get(page_size_str, PAGE_DIMENSIONS_POINTS['A4'])
    
    # Get canvas dimensions in pixels (from template)
    canvas_width_px = getattr(template, 'canvas_width', 794)
    canvas_height_px = getattr(template, 'canvas_height', 1123)
    
    # Conversion factor: pixels to points (assuming 96 DPI for pixels, 72 DPI for points)
    # 1 pixel = 72/96 points = 0.75 points
    px_to_pts = 0.75
    
    # Create PDF in memory
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=page_size)
    
    # Get elements from template
    elements = template.elements or []
    
    # If no elements, create a basic PDF with data
    if not elements:
        _render_basic_pdf(c, data, report_type, page_width_pts, page_height_pts)
    else:
        # IMPORTANT: Render elements in order to preserve template layout
        # First, render all static elements (images, logos, text blocks)
        # Then, render dynamic data (tables with student data)
        
        # Separate static elements from dynamic table elements
        static_elements = []
        table_elements = []
        
        for element in elements:
            element_type = element.get('type', 'text')
            if element_type == 'table':
                table_elements.append(element)
            else:
                static_elements.append(element)
        
        # Step 1: Render all static elements first (logos, headers, footers, text blocks)
        # This ensures the template design is preserved
        for element in static_elements:
            element_type = element.get('type', 'text')
            
            if element_type == 'text' or element_type == 'placeholder':
                _render_text_element(c, element, data, page_width_pts, page_height_pts, canvas_width_px, canvas_height_px, px_to_pts)
            elif element_type == 'image' or element_type == 'logo':
                _render_image_element(c, element, data, page_width_pts, page_height_pts, canvas_width_px, canvas_height_px, px_to_pts)
        
        # Step 2: Render dynamic data into table regions
        # This merges student data into the template's table areas
        for element in table_elements:
            _render_table_element(c, element, data, report_type, page_width_pts, page_height_pts, canvas_width_px, canvas_height_px, px_to_pts)
    
    # Save PDF
    c.save()
    buffer.seek(0)
    
    return buffer


def _render_text_element(canvas_obj, element, data, page_width_pts, page_height_pts, canvas_width_px, canvas_height_px, px_to_pts):
    """Render a text element on the canvas, resolving data-bound variables"""
    content = element.get('content', '')
    x_px = element.get('x', 0)
    y_px = element.get('y', 0)
    
    # Check if this is a data-bound placeholder
    is_data_bound = element.get('isDataBound', False)
    data_key = element.get('dataKey') or element.get('placeholder')
    
    # Resolve data-bound variable
    if is_data_bound and data_key:
        content = _resolve_data_key(data_key, data)
    elif element.get('isPlaceholder', False) or element.get('type') == 'placeholder':
        # Legacy placeholder format - try to extract data key from content
        if '{{' in content:
            content = _replace_placeholders(content, data)
        elif data_key:
            content = _resolve_data_key(data_key, data)
    elif '{{' in content or '{' in content:
        # Replace placeholders in content
        content = _replace_placeholders(content, data)
    
    # Get style properties
    font_family = element.get('fontFamily', 'Helvetica')
    font_size = element.get('fontSize', 12)
    color = element.get('color', '#000000')
    bold = element.get('bold', False)
    italic = element.get('italic', False)
    alignment = element.get('alignment', 'left') or element.get('textAlign', 'left')
    
    # Map common font names to ReportLab standard fonts
    font_mapping = {
        'Arial': 'Helvetica',
        'Times New Roman': 'Times-Roman',
        'Courier New': 'Courier',
        'Georgia': 'Times-Roman',
        'Verdana': 'Helvetica',
        'Helvetica': 'Helvetica',
        'Times-Roman': 'Times-Roman',
        'Courier': 'Courier',
    }
    
    # Convert to ReportLab font name
    base_font = font_mapping.get(font_family, 'Helvetica')
    
    # Build font name with style
    if bold and italic:
        font_name = f"{base_font}-BoldOblique" if base_font == 'Helvetica' else f"{base_font}-BoldItalic"
    elif bold:
        font_name = f"{base_font}-Bold"
    elif italic:
        font_name = f"{base_font}-Oblique" if base_font == 'Helvetica' else f"{base_font}-Italic"
    else:
        font_name = base_font
    
    # Set font (with error handling)
    actual_font_name = font_name
    try:
        canvas_obj.setFont(font_name, font_size)
    except Exception as e:
        # Fallback to Helvetica if font is not available
        print(f"Warning: Font '{font_name}' not available, using Helvetica. Error: {e}")
        actual_font_name = 'Helvetica'
        canvas_obj.setFont(actual_font_name, font_size)
    
    # Set color
    try:
        if color.startswith('#'):
            r = int(color[1:3], 16) / 255.0
            g = int(color[3:5], 16) / 255.0
            b = int(color[5:7], 16) / 255.0
            canvas_obj.setFillColorRGB(r, g, b)
        else:
            canvas_obj.setFillColor(colors.black)
    except:
        canvas_obj.setFillColor(colors.black)
    
    # Convert pixel coordinates to points and scale to page size
    # Scale factor: page_size / canvas_size
    scale_x = page_width_pts / (canvas_width_px * px_to_pts) if canvas_width_px > 0 else 1
    scale_y = page_height_pts / (canvas_height_px * px_to_pts) if canvas_height_px > 0 else 1
    
    x_pts = x_px * px_to_pts * scale_x
    y_pts = y_px * px_to_pts * scale_y
    
    # Calculate text width for alignment (use actual_font_name in case of fallback)
    from reportlab.pdfbase.pdfmetrics import stringWidth
    try:
        text_width = stringWidth(content, actual_font_name, font_size)
    except Exception:
        # Fallback to Helvetica if stringWidth fails
        text_width = stringWidth(content, 'Helvetica', font_size)
    
    # Adjust X position based on alignment
    if alignment == 'center':
        x_pts = x_pts - (text_width / 2)
    elif alignment == 'right':
        x_pts = x_pts - text_width
    
    # Note: ReportLab uses bottom-left origin, so we need to flip Y
    y_canvas = page_height_pts - y_pts
    
    # Draw text
    canvas_obj.drawString(x_pts, y_canvas, content)


def _render_table_element(canvas_obj, element, data, report_type, page_width_pts, page_height_pts, canvas_width_px, canvas_height_px, px_to_pts):
    """
    Render a table element on the canvas.
    Merges dynamic student data into the template's table region,
    respecting the template's positioning and layout rules.
    Supports data-bound table placeholders that auto-expand based on collections.
    """
    # Check if this is a data-bound table placeholder
    data_key = element.get('dataKey') or element.get('placeholder', '')
    is_data_bound = element.get('isDataBound', False)
    
    # Map data key to report type and data source
    if is_data_bound and data_key:
        data_key_map = {
            'table.results': ('results', 'results'),
            'table.registered_units': ('registered_units', 'units'),
            'table.fee_structure': ('fee_structure', 'fee_items')
        }
        if data_key in data_key_map:
            report_type, data_key = data_key_map[data_key]
    elif data_key and data_key.startswith('table.'):
        # Legacy placeholder format
        placeholder_map = {
            'table.results': ('results', 'results'),
            'table.registered_units': ('registered_units', 'units'),
            'table.fee_structure': ('fee_structure', 'fee_items')
        }
        if data_key in placeholder_map:
            report_type, data_key = placeholder_map[data_key]
    
    table_config = element.get('tableConfig', {})
    
    # Use element's x/y coordinates if present, otherwise fallback to center
    # This ensures position persistence - never reset to (0,0)
    element_x = element.get('x')
    element_y = element.get('y')
    
    if element_x is not None and element_y is not None:
        # Trust stored values - use element coordinates
        start_x_px = element_x
        start_y_px = element_y
    else:
        # Fallback to center if coordinates missing
        start_x_px = canvas_width_px / 2 if canvas_width_px > 0 else 50
        start_y_px = canvas_height_px / 2 if canvas_height_px > 0 else 300
    
    row_height_px = table_config.get('rowHeight', 20)
    font_size = table_config.get('fontSize', 10)
    
    # Get column configuration from template if available
    column_configs = table_config.get('columns', [])
    
    # Convert to points and scale
    scale_x = page_width_pts / (canvas_width_px * px_to_pts) if canvas_width_px > 0 else 1
    scale_y = page_height_pts / (canvas_height_px * px_to_pts) if canvas_height_px > 0 else 1
    
    start_x_pts = start_x_px * px_to_pts * scale_x
    start_y_pts = start_y_px * px_to_pts * scale_y
    row_height_pts = row_height_px * px_to_pts * scale_y
    
    # Get table data based on report type or data key
    # For data-bound tables, fetch from the specified data key
    if is_data_bound and data_key:
        # Try to get data directly from the data key
        table_data = _get_nested_data(data, data_key, [])
    elif report_type == 'results':
        table_data = data.get('results', [])
    elif report_type == 'registered_units':
        table_data = data.get('units', [])
    elif report_type == 'fee_structure':
        table_data = data.get('fee_items', [])
    else:
        table_data = []
    
    # Use template column config if available, otherwise use defaults based on report type
    column_definitions = []  # List of dicts with 'header', 'field', 'width', 'alignment'
    
    if column_configs:
        # Handle both formats: list of strings or list of dicts
        if isinstance(column_configs, list) and len(column_configs) > 0:
            if isinstance(column_configs[0], dict):
                # New structured format: list of dictionaries with 'header', 'field', 'width', 'alignment'
                column_definitions = column_configs
            elif isinstance(column_configs[0], str):
                # Legacy format: list of strings (column names)
                column_definitions = [
                    {
                        'header': col.replace('_', ' ').title(),
                        'field': col,
                        'width': 80,
                        'alignment': 'left'
                    }
                    for col in column_configs if col
                ]
            else:
                column_definitions = []
        else:
            column_definitions = []
    else:
        # Default columns based on report type
        if report_type == 'results':
            default_cols = ['unit_code', 'unit_name', 'academic_year', 'semester', 'cat_marks', 'exam_marks', 'total_marks', 'grade']
            column_definitions = [
                {'header': col.replace('_', ' ').title(), 'field': col, 'width': 80, 'alignment': 'left'}
                for col in default_cols
            ]
        elif report_type == 'registered_units':
            default_cols = ['unit_code', 'unit_name', 'academic_year', 'semester', 'exam_registered_at']
            column_definitions = [
                {'header': col.replace('_', ' ').title(), 'field': col, 'width': 80, 'alignment': 'left'}
                for col in default_cols
            ]
        elif report_type == 'fee_structure':
            default_cols = ['semester', 'fee_type', 'amount']
            column_definitions = [
                {'header': col.replace('_', ' ').title(), 'field': col, 'width': 80, 'alignment': 'left'}
                for col in default_cols
            ]
        else:
            # Auto-detect columns from first row of data if available
            if table_data and isinstance(table_data, list) and len(table_data) > 0:
                default_cols = list(table_data[0].keys()) if isinstance(table_data[0], dict) else []
                column_definitions = [
                    {'header': col.replace('_', ' ').title(), 'field': col, 'width': 80, 'alignment': 'left'}
                    for col in default_cols
                ]
            else:
                column_definitions = []
    
    # Extract columns, widths, and alignments for rendering
    columns = [col.get('field', '') for col in column_definitions if col.get('field')]
    column_widths = [col.get('width', 80) for col in column_definitions]
    column_alignments = [col.get('alignment', 'left') for col in column_definitions]
    column_headers = [col.get('header', col.get('field', '')) for col in column_definitions]
    
    # Get font properties from table config
    # FORCE black text and white background - ignore any theme or inherited colors
    font_family = table_config.get('fontFamily', 'Helvetica')
    font_style = table_config.get('fontStyle', 'normal')  # normal, bold, italic
    text_color = '#000000'  # FORCE black - ignore config
    
    # Map font family
    font_mapping = {
        'Arial': 'Helvetica',
        'Times New Roman': 'Times-Roman',
        'Courier New': 'Courier',
        'Georgia': 'Times-Roman',
        'Verdana': 'Helvetica',
        'Helvetica': 'Helvetica',
        'Times-Roman': 'Times-Roman',
        'Courier': 'Courier',
    }
    base_font = font_mapping.get(font_family, 'Helvetica')
    
    # Build font name with style
    if font_style == 'bold' or table_config.get('bold', False):
        font_name = f"{base_font}-Bold"
    elif font_style == 'italic':
        font_name = f"{base_font}-Oblique" if base_font == 'Helvetica' else f"{base_font}-Italic"
    else:
        font_name = base_font
    
    # Set font
    try:
        canvas_obj.setFont(font_name, font_size)
    except:
        canvas_obj.setFont('Helvetica', font_size)
    
    # Set text color - FORCE black (#000000)
    try:
        # Always use black - ignore any color config
        canvas_obj.setFillColor(colors.black)
    except:
        canvas_obj.setFillColor(colors.black)
    
    # Ensure white background (PDF default is white, but explicitly set if needed)
    # Note: ReportLab canvas background is white by default, but we ensure it
    
    # Get header row configuration
    header_row_height = table_config.get('headerRowHeight', 25)
    header_font_size = table_config.get('headerFontSize', 11)
    header_bold = table_config.get('headerBold', True)
    header_row_height_pts = header_row_height * px_to_pts * scale_y
    
    # Calculate Y position (flip for ReportLab - bottom-left origin)
    current_y = page_height_pts - start_y_pts
    
    # Draw header row if columns are defined
    if column_headers and len(column_headers) > 0:
        # Set header font (bold)
        if header_bold:
            header_font_name = f"{base_font}-Bold" if base_font != 'Courier' else 'Courier-Bold'
        else:
            header_font_name = font_name
        try:
            canvas_obj.setFont(header_font_name, header_font_size)
        except:
            canvas_obj.setFont('Helvetica-Bold', header_font_size)
        
        # FORCE black color for headers
        canvas_obj.setFillColor(colors.black)
        
        x_offset = 0
        for col_idx, header_text in enumerate(column_headers):
            if col_idx >= len(column_widths):
                break
            col_width_px = column_widths[col_idx]
            col_width_pts = col_width_px * px_to_pts * scale_x
            col_alignment = column_alignments[col_idx] if col_idx < len(column_alignments) else 'left'
            
            # Calculate text position based on alignment
            from reportlab.pdfbase.pdfmetrics import stringWidth
            try:
                text_width = stringWidth(header_text, header_font_name, header_font_size)
            except:
                text_width = stringWidth(header_text, 'Helvetica-Bold', header_font_size)
            
            text_x = start_x_pts + x_offset
            if col_alignment == 'center':
                text_x = start_x_pts + x_offset + (col_width_pts / 2) - (text_width / 2)
            elif col_alignment == 'right':
                text_x = start_x_pts + x_offset + col_width_pts - text_width
            
            # Draw header text
            canvas_obj.drawString(text_x, current_y, str(header_text))
            x_offset += col_width_pts
        
        # Move down for data rows
        current_y -= header_row_height_pts
    
    # Reset to data row font
    try:
        canvas_obj.setFont(font_name, font_size)
    except:
        canvas_obj.setFont('Helvetica', font_size)
    
    # Draw table rows - merge data into template position
    for i, row_data in enumerate(table_data):
        # Check if we need a new page (preserve template header/footer on new pages)
        if current_y < 50 and i < len(table_data) - 1:
            canvas_obj.showPage()
            # Re-render static elements on new page if needed
            # For now, just reset Y position
            current_y = page_height_pts - start_y_pts
        
        x_offset = 0
        # Use configured column definitions
        for col_idx, col_field in enumerate(columns):
            if col_idx >= len(column_widths):
                break
            col_width_px = column_widths[col_idx]
            col_width_pts = col_width_px * px_to_pts * scale_x
            col_alignment = column_alignments[col_idx] if col_idx < len(column_alignments) else 'left'
            
            # Get cell value
            value = row_data.get(col_field, '')
            if value is None:
                value = '-'
            elif isinstance(value, float):
                value = f"{value:.1f}"
            elif isinstance(value, int):
                value = str(value)
            else:
                value = str(value)
            
            # Calculate text position based on alignment
            from reportlab.pdfbase.pdfmetrics import stringWidth
            try:
                text_width = stringWidth(value, font_name, font_size)
            except:
                text_width = stringWidth(value, 'Helvetica', font_size)
            
            text_x = start_x_pts + x_offset
            if col_alignment == 'center':
                text_x = start_x_pts + x_offset + (col_width_pts / 2) - (text_width / 2)
            elif col_alignment == 'right':
                text_x = start_x_pts + x_offset + col_width_pts - text_width
            
            # Draw cell content - ensure black color
            canvas_obj.setFillColor(colors.black)
            canvas_obj.drawString(text_x, current_y, value)
            x_offset += col_width_pts
        
        current_y -= row_height_pts


def _render_image_element(canvas_obj, element, data, page_width_pts, page_height_pts, canvas_width_px, canvas_height_px, px_to_pts):
    """
    Render an image/logo element on the canvas.
    Preserves static template elements like logos and images.
    """
    try:
        from reportlab.lib.utils import ImageReader
        import base64
        try:
            from PIL import Image
        except ImportError:
            # PIL/Pillow not available - log warning and skip image
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("PIL/Pillow not installed. Image elements will be skipped. Install with: pip install Pillow")
            return
        
        # Get image content (can be base64 data URL or file path)
        content = element.get('content', '')
        if not content:
            return
        
        # Get position and size
        x_px = element.get('x', 0)
        y_px = element.get('y', 0)
        width_px = element.get('width', 200)
        height_px = element.get('height', 200)
        
        # Convert pixel coordinates to points and scale to page size
        scale_x = page_width_pts / (canvas_width_px * px_to_pts) if canvas_width_px > 0 else 1
        scale_y = page_height_pts / (canvas_height_px * px_to_pts) if canvas_height_px > 0 else 1
        
        x_pts = x_px * px_to_pts * scale_x
        y_pts = y_px * px_to_pts * scale_y
        width_pts = width_px * px_to_pts * scale_x
        height_pts = height_px * px_to_pts * scale_y
        
        # Handle base64 data URL (data:image/png;base64,...)
        if content.startswith('data:image'):
            # Extract base64 data
            header, encoded = content.split(',', 1)
            image_data = base64.b64decode(encoded)
            
            # Create image from bytes
            img = Image.open(BytesIO(image_data))
            
            # Convert to RGB if necessary (for JPEG compatibility)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create a white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            
            # Convert PIL image to bytes for ReportLab
            img_buffer = BytesIO()
            img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            # Draw image on canvas
            # Note: ReportLab uses bottom-left origin, so we need to flip Y
            y_canvas = page_height_pts - y_pts - height_pts
            canvas_obj.drawImage(ImageReader(img_buffer), x_pts, y_canvas, width=width_pts, height=height_pts, preserveAspectRatio=True)
            
        elif content.startswith('http://') or content.startswith('https://'):
            # Handle URL (if needed in future)
            # For now, skip URL-based images
            pass
        else:
            # Try to treat as file path (relative to MEDIA_ROOT or absolute)
            import os
            from django.conf import settings
            
            # Check if it's a relative path in MEDIA_ROOT
            if not os.path.isabs(content):
                file_path = os.path.join(settings.MEDIA_ROOT, content)
            else:
                file_path = content
            
            if os.path.exists(file_path):
                # Draw image from file
                y_canvas = page_height_pts - y_pts - height_pts
                canvas_obj.drawImage(file_path, x_pts, y_canvas, width=width_pts, height=height_pts, preserveAspectRatio=True)
                
    except Exception as e:
        # Log error but don't fail the entire PDF generation
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Error rendering image element: {str(e)}")
        # Continue with other elements
        pass


def _render_basic_pdf(canvas_obj, data, report_type, page_width_pts, page_height_pts):
    """Render a basic PDF when no template elements are configured"""
    # Header
    canvas_obj.setFont('Helvetica-Bold', 16)
    canvas_obj.drawString(50, page_height_pts - 50, data.get('college', {}).get('name', ''))
    
    # Student info
    canvas_obj.setFont('Helvetica', 12)
    y_pos = page_height_pts - 100
    student = data.get('student', {})
    canvas_obj.drawString(50, y_pos, f"Student: {student.get('full_name', '')}")
    y_pos -= 20
    canvas_obj.drawString(50, y_pos, f"Admission Number: {student.get('admission_number', '')}")
    y_pos -= 20
    canvas_obj.drawString(50, y_pos, f"Course: {student.get('course_name', '')}")
    y_pos -= 40
    
    # Report-specific content
    if report_type == 'results':
        canvas_obj.setFont('Helvetica-Bold', 14)
        canvas_obj.drawString(50, y_pos, "Results")
        y_pos -= 30
        canvas_obj.setFont('Helvetica', 10)
        
        results = data.get('results', [])
        for result in results:
            line = f"{result.get('unit_code', '')} - {result.get('unit_name', '')}: {result.get('total_marks', '-')} ({result.get('grade', '-')})"
            canvas_obj.drawString(50, y_pos, line)
            y_pos -= 15
            if y_pos < 50:
                canvas_obj.showPage()
                y_pos = page_height_pts - 50
    
    elif report_type == 'registered_units':
        canvas_obj.setFont('Helvetica-Bold', 14)
        canvas_obj.drawString(50, y_pos, "Registered Units (Exam Card)")
        y_pos -= 30
        canvas_obj.setFont('Helvetica', 10)
        
        units = data.get('units', [])
        for unit in units:
            line = f"{unit.get('unit_code', '')} - {unit.get('unit_name', '')} ({unit.get('academic_year', '')} Sem {unit.get('semester', '')})"
            canvas_obj.drawString(50, y_pos, line)
            y_pos -= 15
            if y_pos < 50:
                canvas_obj.showPage()
                y_pos = page_height_pts - 50
    
    elif report_type == 'fee_structure':
        canvas_obj.setFont('Helvetica-Bold', 14)
        canvas_obj.drawString(50, y_pos, "Fee Structure")
        y_pos -= 30
        canvas_obj.setFont('Helvetica', 10)
        
        fee_items = data.get('fee_items', [])
        for item in fee_items:
            line = f"Semester {item.get('semester', '')} - {item.get('fee_type', '')}: KES {item.get('amount', 0):.2f}"
            canvas_obj.drawString(50, y_pos, line)
            y_pos -= 15
            if y_pos < 50:
                canvas_obj.showPage()
                y_pos = page_height_pts - 50
        
        # Total
        y_pos -= 10
        canvas_obj.setFont('Helvetica-Bold', 12)
        total = data.get('total_expected', 0)
        canvas_obj.drawString(50, y_pos, f"Total Expected: KES {total:.2f}")


def _replace_placeholders(text, data):
    """
    Replace placeholders in text with actual data.
    Supports both {{variable}} and {variable} syntax.
    Also handles nested placeholders like {{student.full_name}}.
    """
    if not text or not isinstance(text, str):
        return text
    
    # Standard replacements
    replacements = {
        '{{student.full_name}}': data.get('student', {}).get('full_name', ''),
        '{{student.admission_number}}': data.get('student', {}).get('admission_number', ''),
        '{{student.full_name}}': data.get('student', {}).get('full_name', ''),
        '{{student.course_name}}': data.get('student', {}).get('course_name', ''),
        '{{student.year_of_study}}': str(data.get('student', {}).get('year_of_study', '')),
        '{{college.name}}': data.get('college', {}).get('name', ''),
        '{{college.address}}': data.get('college', {}).get('address', ''),
        '{{generation_date}}': data.get('generation_date', ''),
        '{{academic_year}}': str(data.get('academic_year', '')),
        '{{semester}}': str(data.get('semester', '')),
        # Also support single brace syntax
        '{student.full_name}': data.get('student', {}).get('full_name', ''),
        '{student.admission_number}': data.get('student', {}).get('admission_number', ''),
        '{student.course_name}': data.get('student', {}).get('course_name', ''),
        '{student.year_of_study}': str(data.get('student', {}).get('year_of_study', '')),
        '{college.name}': data.get('college', {}).get('name', ''),
        '{college.address}': data.get('college', {}).get('address', ''),
        '{generation_date}': data.get('generation_date', ''),
        '{academic_year}': str(data.get('academic_year', '')),
        '{semester}': str(data.get('semester', '')),
    }
    
    # Replace all placeholders
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, str(value))
    
    # Handle dynamic placeholder replacement (e.g., {{student.full_name}})
    import re
    # Match {{variable}} or {{object.property}} patterns
    pattern = r'\{\{([^}]+)\}\}'
    def replace_match(match):
        key = match.group(1).strip()
        # Handle nested keys like 'student.full_name'
        keys = key.split('.')
        value = data
        try:
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k, '')
                else:
                    return ''
            return str(value) if value is not None else ''
        except:
            return ''
    
    text = re.sub(pattern, replace_match, text)
    
    return text


def _resolve_data_key(data_key, data):
    """
    Resolve a data key (e.g., 'student.full_name') to its actual value from the data dictionary.
    Supports nested keys like 'student.full_name' or 'college.name'.
    
    Args:
        data_key: String key like 'student.full_name', 'college.name', etc.
        data: Dictionary containing the data
    
    Returns:
        str: Resolved value or empty string if not found
    """
    if not data_key or not data:
        return ''
    
    # Split the key by dots to handle nested access
    keys = data_key.split('.')
    value = data
    
    try:
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, '')
            elif isinstance(value, (list, tuple)) and len(value) > 0:
                # If it's a list, get the first item (for single value access)
                value = value[0].get(key, '') if isinstance(value[0], dict) else ''
            else:
                return ''
        
        # Convert to string, handle None
        if value is None:
            return ''
        return str(value)
    except (KeyError, IndexError, TypeError, AttributeError):
        return ''


def _get_nested_data(data, data_key, default=None):
    """
    Get nested data from a dictionary using a dot-separated key.
    For example, 'student.full_name' returns data['student']['full_name']
    For collections like 'results', returns the list directly.
    
    Args:
        data: Dictionary containing the data
        data_key: Dot-separated key like 'student.full_name' or 'results'
        default: Default value if key not found
    
    Returns:
        The value at the nested key, or default if not found
    """
    if not data_key or not data:
        return default
    
    keys = data_key.split('.')
    value = data
    
    try:
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, default)
            elif isinstance(value, (list, tuple)):
                # If it's a list, return it directly (for collections)
                if len(keys) == 1:  # Top-level key
                    return value
                return default
            else:
                return default
        
        return value if value is not None else default
    except (KeyError, IndexError, TypeError, AttributeError):
        return default


