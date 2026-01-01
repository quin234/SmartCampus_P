"""
Transcript Generator Utility
Generates PDF transcripts using PDF template overlay (no image conversion)
"""
import os
from django.conf import settings
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
import zipfile
import tempfile
from io import BytesIO
import shutil

# Try to import pypdf (PyPDF2 or pypdf)
try:
    from pypdf import PdfReader, PdfWriter
    PYPDF_AVAILABLE = True
except ImportError:
    try:
        from PyPDF2 import PdfFileReader as PdfReader, PdfFileWriter as PdfWriter
        PYPDF_AVAILABLE = True
    except ImportError:
        PYPDF_AVAILABLE = False
        print("Warning: pypdf not installed. PDF template overlay requires: pip install pypdf")


def generate_preview_transcript(template, college):
    """
    Generate a preview transcript with sample data
    
    Args:
        template: TranscriptTemplate model instance
        college: College model instance
    
    Returns:
        str: URL path to generated PDF
    """
    # Sample data for preview
    sample_data = {
        'student': {
            'full_name': 'John Doe',
            'admission_number': 'STU001',
            'course_name': 'Diploma in Information Technology',
            'year_of_study': 2,
        },
        'college': {
            'name': college.name or '',
            'address': getattr(college, 'address', '') or '',
        },
        'results': [
            {
                'unit_code': 'IT101',
                'unit_name': 'Introduction to Programming',
                'academic_year': '2024/2025',
                'semester': 1,
                'cat_marks': 25.0,
                'exam_marks': 60.0,
                'total_marks': 85.0,
                'grade': 'A'
            },
            {
                'unit_code': 'IT102',
                'unit_name': 'Database Management Systems',
                'academic_year': '2024/2025',
                'semester': 1,
                'cat_marks': 28.0,
                'exam_marks': 65.0,
                'total_marks': 93.0,
                'grade': 'A'
            },
            {
                'unit_code': 'IT103',
                'unit_name': 'Web Development',
                'academic_year': '2024/2025',
                'semester': 1,
                'cat_marks': 22.0,
                'exam_marks': 55.0,
                'total_marks': 77.0,
                'grade': 'B'
            },
            {
                'unit_code': 'IT104',
                'unit_name': 'Computer Networks',
                'academic_year': '2024/2025',
                'semester': 2,
                'cat_marks': 27.0,
                'exam_marks': 62.0,
                'total_marks': 89.0,
                'grade': 'A'
            },
            {
                'unit_code': 'IT105',
                'unit_name': 'Software Engineering',
                'academic_year': '2024/2025',
                'semester': 2,
                'cat_marks': 24.0,
                'exam_marks': 58.0,
                'total_marks': 82.0,
                'grade': 'A'
            }
        ],
        'summary': {
            'total_units': 5,
            'average_score': 85.2,
            'generation_date': timezone.now().strftime('%Y-%m-%d')
        }
    }
    
    # Generate PDF
    output_path = _create_pdf_from_template(template, sample_data)
    
    return output_path


def generate_transcript_pdf(student, template, academic_year='', semester=''):
    """
    Generate a single transcript PDF for a student
    
    Args:
        student: Student model instance
        template: TranscriptTemplate model instance
        academic_year: Optional filter for academic year
        semester: Optional filter for semester
    
    Returns:
        str: URL path to generated PDF
    """
    from ..models import Enrollment, Result, College
    
    # Get student results
    enrollments = Enrollment.objects.filter(student=student, exam_registered=True)
    
    if academic_year:
        enrollments = enrollments.filter(academic_year=academic_year)
    if semester:
        enrollments = enrollments.filter(semester=int(semester))
    
    enrollments = enrollments.select_related('unit', 'result').order_by('academic_year', 'semester')
    
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
            # No result yet, but include in transcript
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
    
    # Calculate summary
    total_units = len(results)
    completed_results = [r for r in results if r['total_marks'] is not None]
    average_score = sum(r['total_marks'] for r in completed_results) / len(completed_results) if completed_results else None
    
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
            'address': student.college.address,
        },
        'results': results,
        'summary': {
            'total_units': total_units,
            'average_score': round(average_score, 2) if average_score else None,
            'generation_date': timezone.now().strftime('%Y-%m-%d')
        }
    }
    
    # Generate PDF
    output_path = _create_pdf_from_template(template, data)
    
    return output_path


def generate_bulk_transcripts(student_ids, college, template, academic_year='', semester=''):
    """
    Generate transcripts for multiple students and return ZIP file
    
    Args:
        student_ids: List of student IDs
        college: College model instance
        template: TranscriptTemplate model instance
        academic_year: Optional filter
        semester: Optional filter
    
    Returns:
        str: URL path to generated ZIP file
    """
    from ..models import Student
    
    # Create temporary directory for PDFs
    temp_dir = tempfile.mkdtemp()
    pdf_files = []
    
    try:
        for student_id in student_ids:
            try:
                student = Student.objects.get(pk=student_id, college=college)
                pdf_path = generate_transcript_pdf(student, template, academic_year, semester)
                
                # Copy to temp directory with student name
                filename = f"{student.admission_number}_{student.full_name.replace(' ', '_')}.pdf"
                dest_path = os.path.join(temp_dir, filename)
                shutil.copy(pdf_path.replace('/media/', os.path.join(settings.MEDIA_ROOT, '')), dest_path)
                pdf_files.append((filename, dest_path))
            except Student.DoesNotExist:
                continue
        
        # Create ZIP file
        zip_filename = f"transcripts_{college.get_slug()}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = os.path.join(settings.MEDIA_ROOT, 'transcripts', 'generated', zip_filename)
        os.makedirs(os.path.dirname(zip_path), exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename, filepath in pdf_files:
                zipf.write(filepath, filename)
        
        # Cleanup temp directory
        shutil.rmtree(temp_dir)
        
        return f'/media/transcripts/generated/{zip_filename}'
    
    except Exception as e:
        # Cleanup on error
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise e


def _create_pdf_from_template(template, data):
    """
    Create PDF from template using PDF overlay (no image conversion)
    
    Args:
        template: TranscriptTemplate instance
        data: Dictionary with student, college, results, summary
    
    Returns:
        str: URL path to generated PDF
    """
    if not PYPDF_AVAILABLE:
        raise ImportError("pypdf is required for PDF template overlay. Install with: pip install pypdf")
    
    # Only PDF templates are supported (no image conversion)
    if template.template_type != 'pdf':
        raise ValueError(f"Only PDF templates are supported. Template type '{template.template_type}' is not supported. Please upload a PDF template.")
    
    # Get template file path
    if not template.template_file:
        raise ValueError("Template file is missing. Please upload a template file.")
    
    try:
        template_path = template.template_file.path
    except ValueError as e:
        raise ValueError(f"Template file path error: {str(e)}. Please re-upload the template.")
    
    if not os.path.exists(template_path):
        raise ValueError(f"Template file not found at path: {template_path}. Please re-upload the template.")
    
    if not template_path.lower().endswith('.pdf'):
        raise ValueError("Template file must be a PDF. Image templates are no longer supported.")
    
    field_positions = template.field_positions or {}
    
    # Get margins (default to 72 points = 1 inch)
    margin_top = getattr(template, 'margin_top', 72.0)
    margin_bottom = getattr(template, 'margin_bottom', 72.0)
    margin_left = getattr(template, 'margin_left', 72.0)
    margin_right = getattr(template, 'margin_right', 72.0)
    
    # Create output filename
    output_filename = f"transcript_{data['student']['admission_number']}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    output_dir = os.path.join(settings.MEDIA_ROOT, 'transcripts', 'generated')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_filename)
    
    # A4 dimensions in points
    A4_WIDTH = 595.28
    A4_HEIGHT = 841.89
    
    # Calculate content area
    content_width = A4_WIDTH - margin_left - margin_right
    content_height = A4_HEIGHT - margin_top - margin_bottom
    
    # Create temporary PDF for content layer using ReportLab
    temp_content_pdf = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    temp_content_path = temp_content_pdf.name
    temp_content_pdf.close()
    
    try:
        # Create content PDF with ReportLab
        c = canvas.Canvas(temp_content_path, pagesize=A4)
        
        # Draw text fields at specified positions (adjusted for margins)
        _draw_text_fields(c, field_positions, data, A4_WIDTH, A4_HEIGHT, margin_left, margin_top, margin_bottom, margin_right)
        
        # Ensure at least one page exists (ReportLab only creates a page when something is drawn)
        # Always draw a minimal element to guarantee a page is created
        # This is necessary because if field_positions is empty, nothing gets drawn
        c.setFillColor(colors.white)  # White color (invisible on white background)
        c.setStrokeColor(colors.white)  # White stroke (invisible)
        c.setLineWidth(0.1)
        # Draw a tiny rectangle at the corner - this will definitely create a page
        c.rect(0, 0, 0.1, 0.1, fill=1, stroke=0)
        
        c.showPage()  # Finalize the page
        c.save()
        
        # Load template PDF
        try:
            template_reader = PdfReader(template_path)
        except Exception as e:
            raise ValueError(f"Failed to read template PDF: {str(e)}. The template file may be corrupted.")
        
        # Load content PDF
        try:
            content_reader = PdfReader(temp_content_path)
        except Exception as e:
            raise ValueError(f"Failed to read generated content PDF: {str(e)}. Please check the field positions configuration.")
        
        # Validate that both PDFs have pages
        template_pages = len(template_reader.pages)
        content_pages = len(content_reader.pages)
        
        if template_pages == 0:
            raise ValueError("Template PDF has no pages. Please upload a valid PDF template with at least one page.")
        
        if content_pages == 0:
            raise ValueError("Failed to generate content PDF. Please check the field positions configuration.")
        
        # Create output PDF writer
        output_writer = PdfWriter()
        
        # Merge each page
        for page_num in range(max(content_pages, template_pages)):
            try:
                # Get template page (use last page if we need more pages than template has)
                if page_num < template_pages:
                    template_page = template_reader.pages[page_num]
                else:
                    # Use last template page as background (safe because we checked template_pages > 0)
                    template_page = template_reader.pages[template_pages - 1]
            except (IndexError, ValueError) as e:
                raise ValueError(f"Error accessing template PDF page {page_num}: {str(e)}. The template PDF may be corrupted.")
            
            try:
                # Get content page (create blank if we need more pages than content has)
                if page_num < content_pages:
                    content_page = content_reader.pages[page_num]
                else:
                    # Create blank content page if needed
                    from reportlab.pdfgen import canvas as reportlab_canvas
                    blank_content = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
                    blank_canvas = reportlab_canvas.Canvas(blank_content.name, pagesize=A4)
                    blank_canvas.save()
                    blank_reader = PdfReader(blank_content.name)
                    if len(blank_reader.pages) == 0:
                        blank_content.close()
                        os.unlink(blank_content.name)
                        raise ValueError("Failed to create blank content page.")
                    content_page = blank_reader.pages[0]
                    blank_content.close()
                    os.unlink(blank_content.name)
            except (IndexError, ValueError) as e:
                raise ValueError(f"Error accessing content PDF page {page_num}: {str(e)}. Failed to generate transcript content.")
            
            # Merge content onto template
            template_page.merge_page(content_page)
            
            # Add merged page to output
            output_writer.add_page(template_page)
        
        # Write final PDF
        with open(output_path, 'wb') as output_file:
            output_writer.write(output_file)
        
        # Cleanup temp content PDF
        os.unlink(temp_content_path)
        
        return f'/media/transcripts/generated/{output_filename}'
    
    except Exception as e:
        # Cleanup on error
        if os.path.exists(temp_content_path):
            os.unlink(temp_content_path)
        raise e


def _apply_font_settings(canvas_obj, pos):
    """
    Apply font settings from position config to canvas
    
    Args:
        canvas_obj: ReportLab canvas object
        pos: Position dictionary with font settings
    """
    # Get font settings
    font_family = pos.get('font_family', 'Helvetica')
    font_size = pos.get('font_size', 12)
    color = pos.get('color', '#000000')
    bold = pos.get('bold', False)
    italic = pos.get('italic', False)
    
    # Handle font family - check if it already includes style suffix
    if '-' in font_family and (font_family.endswith('-Bold') or font_family.endswith('-Oblique') or 
                               font_family.endswith('-Italic') or font_family.endswith('-BoldOblique') or
                               font_family.endswith('-BoldItalic')):
        font_name = font_family
    else:
        # Build font name from base family and style flags
        if bold and italic:
            font_name = f"{font_family}-BoldOblique" if font_family == 'Helvetica' else f"{font_family}-BoldItalic"
        elif bold:
            font_name = f"{font_family}-Bold"
        elif italic:
            font_name = f"{font_family}-Oblique" if font_family == 'Helvetica' else f"{font_family}-Italic"
        else:
            font_name = font_family
    
    # Set font
    canvas_obj.setFont(font_name, font_size)
    
    # Set color (convert hex to RGB)
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


def _apply_text_transform(text, transform):
    """
    Apply text transformation
    
    Args:
        text: Original text
        transform: 'uppercase', 'lowercase', 'capitalize', or 'none'
    
    Returns:
        Transformed text
    """
    if transform == 'uppercase':
        return text.upper()
    elif transform == 'lowercase':
        return text.lower()
    elif transform == 'capitalize':
        return text.title()
    else:
        return text


def _draw_text_with_alignment(canvas_obj, text, x, y, alignment, pos):
    """
    Draw text with alignment, underline, and strikethrough support
    
    Args:
        canvas_obj: ReportLab canvas object
        text: Text to draw
        x: X coordinate
        y: Y coordinate
        alignment: 'left', 'center', or 'right'
        pos: Position dictionary (for getting text width calculation and styles)
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth
    
    # Apply text transformation
    text_transform = pos.get('text_transform', 'none')
    text = _apply_text_transform(text, text_transform)
    
    # Get font settings for width calculation
    font_family = pos.get('font_family', 'Helvetica')
    font_size = pos.get('font_size', 12)
    bold = pos.get('bold', False)
    italic = pos.get('italic', False)
    
    # Determine font name for width calculation
    if '-' in font_family and (font_family.endswith('-Bold') or font_family.endswith('-Oblique') or 
                               font_family.endswith('-Italic') or font_family.endswith('-BoldOblique') or
                               font_family.endswith('-BoldItalic')):
        font_name = font_family
    else:
        if bold and italic:
            font_name = f"{font_family}-BoldOblique" if font_family == 'Helvetica' else f"{font_family}-BoldItalic"
        elif bold:
            font_name = f"{font_family}-Bold"
        elif italic:
            font_name = f"{font_family}-Oblique" if font_family == 'Helvetica' else f"{font_family}-Italic"
        else:
            font_name = font_family
    
    # Calculate text width for alignment
    text_width = stringWidth(text, font_name, font_size)
    
    # Adjust X position based on alignment
    if alignment == 'center':
        x = x - (text_width / 2)
    elif alignment == 'right':
        x = x - text_width
    
    # Draw the text
    canvas_obj.drawString(x, y, text)
    
    # Draw underline if enabled
    if pos.get('underline', False):
        underline_y = y - 2
        canvas_obj.line(x, underline_y, x + text_width, underline_y)
    
    # Draw strikethrough if enabled
    if pos.get('strikethrough', False):
        strikethrough_y = y + (font_size * 0.35)
        canvas_obj.line(x, strikethrough_y, x + text_width, strikethrough_y)


def _draw_text_fields(canvas_obj, field_positions, data, page_width, page_height, margin_left, margin_top, margin_bottom, margin_right):
    """
    Draw text fields on canvas at specified positions with font customization
    Adjusted for margins - coordinates are relative to content area
    
    Args:
        canvas_obj: ReportLab canvas object
        field_positions: Dictionary of field positions
        data: Data dictionary
        page_width: Page width in points (A4 = 595.28)
        page_height: Page height in points (A4 = 841.89)
        margin_left: Left margin in points
        margin_top: Top margin in points
        margin_bottom: Bottom margin in points
        margin_right: Right margin in points
    """
    # Calculate content area
    content_width = page_width - margin_left - margin_right
    content_height = page_height - margin_top - margin_bottom
    
    # Note: ReportLab uses bottom-left origin, but we store coordinates from top-left
    # So we need to flip Y coordinates: y_canvas = page_height - y_stored
    # Also adjust for margins: x_canvas = margin_left + x_stored, y_canvas = page_height - margin_top - y_stored
    
    # Draw student information
    if 'student_name' in field_positions:
        pos = field_positions['student_name']
        x_stored = pos.get('x', 100)
        y_stored = pos.get('y', 200)
        x = margin_left + x_stored
        y = page_height - margin_top - y_stored  # Flip Y and adjust for margin
        _apply_font_settings(canvas_obj, pos)
        alignment = pos.get('alignment', 'left')
        _draw_text_with_alignment(canvas_obj, data['student']['full_name'], x, y, alignment, pos)
    
    if 'admission_number' in field_positions:
        pos = field_positions['admission_number']
        x_stored = pos.get('x', 100)
        y_stored = pos.get('y', 220)
        x = margin_left + x_stored
        y = page_height - margin_top - y_stored
        _apply_font_settings(canvas_obj, pos)
        alignment = pos.get('alignment', 'left')
        _draw_text_with_alignment(canvas_obj, data['student']['admission_number'], x, y, alignment, pos)
    
    if 'course_name' in field_positions:
        pos = field_positions['course_name']
        x_stored = pos.get('x', 100)
        y_stored = pos.get('y', 240)
        x = margin_left + x_stored
        y = page_height - margin_top - y_stored
        _apply_font_settings(canvas_obj, pos)
        alignment = pos.get('alignment', 'left')
        _draw_text_with_alignment(canvas_obj, data['student']['course_name'], x, y, alignment, pos)
    
    if 'college_name' in field_positions:
        pos = field_positions['college_name']
        x_stored = pos.get('x', 300)
        y_stored = pos.get('y', 50)
        x = margin_left + x_stored
        y = page_height - margin_top - y_stored
        _apply_font_settings(canvas_obj, pos)
        alignment = pos.get('alignment', 'left')
        _draw_text_with_alignment(canvas_obj, data['college']['name'], x, y, alignment, pos)
    
    if 'generation_date' in field_positions:
        pos = field_positions['generation_date']
        x_stored = pos.get('x', 400)
        y_stored = pos.get('y', 500)
        x = margin_left + x_stored
        y = page_height - margin_top - y_stored
        _apply_font_settings(canvas_obj, pos)
        alignment = pos.get('alignment', 'left')
        _draw_text_with_alignment(canvas_obj, data['summary']['generation_date'], x, y, alignment, pos)
    
    # Draw results table
    if 'results_table' in field_positions:
        table_config = field_positions['results_table']
        start_x_stored = table_config.get('start_x', 50)
        start_y_stored = table_config.get('start_y', 300)
        start_x = margin_left + start_x_stored
        start_y = page_height - margin_top - start_y_stored  # Flip Y and adjust for margin
        row_height = table_config.get('row_height', 20)
        columns = table_config.get('columns', {})
        
        current_y = start_y
        font_size = table_config.get('font_size', 10)
        canvas_obj.setFont('Helvetica', font_size)
        
        for i, result in enumerate(data['results']):
            # Check if we need a new page
            if current_y < margin_bottom + 50 and i < len(data['results']) - 1:
                canvas_obj.showPage()
                current_y = start_y
            
            # Unit Code
            if 'unit_code' in columns:
                col = columns['unit_code']
                x = start_x + col.get('x_offset', 0)
                canvas_obj.drawString(x, current_y, result['unit_code'])
            
            # Unit Name
            if 'unit_name' in columns:
                col = columns['unit_name']
                x = start_x + col.get('x_offset', 80)
                # Truncate long names
                name = result['unit_name'][:30] + '...' if len(result['unit_name']) > 30 else result['unit_name']
                canvas_obj.drawString(x, current_y, name)
            
            # Academic Year
            if 'academic_year' in columns:
                col = columns['academic_year']
                x = start_x + col.get('x_offset', 280)
                canvas_obj.drawString(x, current_y, result['academic_year'])
            
            # Semester
            if 'semester' in columns:
                col = columns['semester']
                x = start_x + col.get('x_offset', 380)
                canvas_obj.drawString(x, current_y, str(result['semester']))
            
            # CAT Marks
            if 'cat_marks' in columns:
                col = columns['cat_marks']
                x = start_x + col.get('x_offset', 440)
                cat_str = f"{result['cat_marks']:.1f}" if result['cat_marks'] is not None else '-'
                canvas_obj.drawString(x, current_y, cat_str)
            
            # Exam Marks
            if 'exam_marks' in columns:
                col = columns['exam_marks']
                x = start_x + col.get('x_offset', 500)
                exam_str = f"{result['exam_marks']:.1f}" if result['exam_marks'] is not None else '-'
                canvas_obj.drawString(x, current_y, exam_str)
            
            # Total Marks
            if 'total_marks' in columns:
                col = columns['total_marks']
                x = start_x + col.get('x_offset', 560)
                total_str = f"{result['total_marks']:.1f}" if result['total_marks'] is not None else '-'
                canvas_obj.drawString(x, current_y, total_str)
            
            # Grade
            if 'grade' in columns:
                col = columns['grade']
                x = start_x + col.get('x_offset', 620)
                grade_str = result['grade'] if result['grade'] else '-'
                canvas_obj.drawString(x, current_y, grade_str)
            
            current_y -= row_height  # Move down (in canvas coordinates, this is actually up)
    
    # Draw summary
    if 'average_score' in field_positions and data['summary']['average_score']:
        pos = field_positions['average_score']
        x_stored = pos.get('x', 400)
        y_stored = pos.get('y', 100)
        x = margin_left + x_stored
        y = page_height - margin_top - y_stored
        _apply_font_settings(canvas_obj, pos)
        alignment = pos.get('alignment', 'left')
        _draw_text_with_alignment(canvas_obj, f"Average: {data['summary']['average_score']}", x, y, alignment, pos)
