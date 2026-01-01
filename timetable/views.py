from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from education.decorators import college_required, verify_college_access, student_required
from education.models import College, CollegeCourse, CollegeTimetable, Student
from .decorators import registrar_required_for_timetable, director_blocked_from_timetable
from .models import TimetableRun, TimetableEntry, TimetableGeneration, TimetableDay, TimeSlot, Classroom
from .forms import TimetableDayForm, TimeSlotForm, ClassroomForm
from .services.generator import generate_timetable as generate_timetable_service
from .services.validation import validate_timetable_run
from django.utils.text import slugify


def get_college_from_slug(college_slug):
    """Helper to get college from slug"""
    try:
        for college in College.objects.all():
            if slugify(college.name) == college_slug:
                return college
        return None
    except College.DoesNotExist:
        return None


@login_required
@verify_college_access
@registrar_required_for_timetable
def upload_timetable(request, college_slug=None):
    """Upload timetable - Only Registrar can access"""
    college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
    
    if request.method == 'POST':
        course_id = request.POST.get('course_id')
        uploaded_file = request.FILES.get('image') or request.FILES.get('file')
        academic_year = request.POST.get('academic_year')
        semester = request.POST.get('semester')
        description = request.POST.get('description', '')
        
        if not uploaded_file:
            messages.error(request, 'Please select a file to upload.')
        else:
            course = None
            if course_id:
                try:
                    course = CollegeCourse.objects.get(id=course_id, college=college)
                except CollegeCourse.DoesNotExist:
                    messages.error(request, 'Invalid course selected.')
                    return redirect('timetable:upload_timetable')
            
            # Determine if it's an image or PDF
            is_pdf = uploaded_file.name.lower().endswith('.pdf') or uploaded_file.content_type == 'application/pdf'
            
            # Check for duplicate
            duplicate = CollegeTimetable.objects.filter(
                college=college,
                course=course,
                academic_year=academic_year or None,
                semester=semester or None
            ).first()
            
            if duplicate:
                messages.warning(request, 'A timetable already exists for this combination. Updating existing timetable.')
                if is_pdf:
                    duplicate.file = uploaded_file
                    duplicate.image = None  # Clear image if uploading PDF
                else:
                    duplicate.image = uploaded_file
                    duplicate.file = None  # Clear file if uploading image
                duplicate.description = description
                duplicate.uploaded_by = request.user
                duplicate.save()
                messages.success(request, 'Timetable updated successfully.')
            else:
                if is_pdf:
                    timetable = CollegeTimetable.objects.create(
                        college=college,
                        course=course,
                        file=uploaded_file,
                        academic_year=academic_year or None,
                        semester=int(semester) if semester else None,
                        description=description,
                        uploaded_by=request.user
                    )
                else:
                    timetable = CollegeTimetable.objects.create(
                        college=college,
                        course=course,
                        image=uploaded_file,
                        academic_year=academic_year or None,
                        semester=int(semester) if semester else None,
                        description=description,
                        uploaded_by=request.user
                    )
                messages.success(request, 'Timetable uploaded successfully.')
            
            return redirect('timetable:upload_timetable')
    
    courses = CollegeCourse.objects.filter(college=college).order_by('name')
    timetables = CollegeTimetable.objects.filter(college=college, is_active=True).order_by('-uploaded_at')
    
    context = {
        'college': college,
        'courses': courses,
        'timetables': timetables,
        'current_academic_year': college.current_academic_year,
        'current_semester': college.current_semester,
    }
    return render(request, 'timetable/upload_timetable.html', context)


@login_required
@verify_college_access
@director_blocked_from_timetable
def general_timetable(request, college_slug=None):
    """View general timetable - Director blocked. Shows published generated timetables."""
    college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
    
    # Get published generated timetables (general - no course)
    published_runs = TimetableRun.objects.filter(
        college=college,
        course__isnull=True,
        status='published'
    ).order_by('-published_at')
    
    # Also get uploaded image timetables (legacy)
    uploaded_timetables = CollegeTimetable.objects.filter(
        college=college,
        course__isnull=True,
        is_active=True
    ).order_by('-uploaded_at')
    
    # Get the most recent published timetable for display
    active_timetable = published_runs.first()
    timetable_data = None
    
    if active_timetable:
        timetable_data = build_timetable_table(active_timetable)
    
    context = {
        'college': college,
        'active_timetable': active_timetable,
        'timetable_data': timetable_data,
        'published_runs': published_runs,
        'uploaded_timetables': uploaded_timetables,
    }
    return render(request, 'timetable/general_timetable.html', context)


@login_required
@verify_college_access
def my_timetable(request, college_slug=None):
    """
    My Timetable view - Shows only entries assigned to the logged-in user (lecturer)
    Visible to: Registrar, Principal, Lecturer
    """
    college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
    
    # Check if user has permission (Registrar, Principal, or Lecturer)
    if not (request.user.is_registrar() or request.user.is_principal() or request.user.is_lecturer()):
        messages.error(request, 'You do not have permission to view this page.')
        return redirect('college_landing', college_slug=college.get_slug())
    
    # Get all published timetable runs
    published_runs = TimetableRun.objects.filter(
        college=college,
        status='published'
    ).order_by('-published_at')
    
    # Get entries where lecturer is the logged-in user
    my_entries = TimetableEntry.objects.filter(
        timetable__in=published_runs,
        lecturer=request.user
    ).select_related('day', 'time_slot', 'course', 'unit', 'lecturer', 'classroom', 'timetable').order_by(
        'timetable__published_at', 'day__order_index', 'time_slot__start_time'
    )
    
    # Build grid data with time slots as rows and days as columns
    days = list(TimetableDay.objects.all().order_by('order_index'))
    time_slots = list(TimeSlot.objects.all().order_by('start_time'))
    
    # Build entries dictionary
    entries_dict = {}
    for entry in my_entries:
        entries_dict[entry.id] = {
            'id': entry.id,
            'day_id': entry.day.id,
            'day_name': entry.day.name,
            'time_slot_id': entry.time_slot.id,
            'time_slot_start': entry.time_slot.start_time.strftime('%H:%M'),
            'time_slot_end': entry.time_slot.end_time.strftime('%H:%M'),
            'course_id': entry.course.id,
            'course_name': entry.course.name,
            'unit_id': entry.unit.id,
            'unit_code': entry.unit.code,
            'unit_name': entry.unit.name,
            'lecturer_id': entry.lecturer.id if entry.lecturer else None,
            'lecturer_name': entry.lecturer.get_full_name() if entry.lecturer else 'TBA',
            'classroom_id': entry.classroom.id if entry.classroom else None,
            'classroom_name': entry.classroom.name if entry.classroom else 'TBA',
        }
    
    # Build rows (time slots) with entries grouped by day
    # Structure: rows[time_slot_index][day_index] = [entry_dicts]
    rows = []
    for time_slot in time_slots:
        day_entries_list = []  # List of lists, one per day
        for day in days:
            day_entry_list = []
            # Find entries for this time slot and day
            for entry in my_entries:
                if entry.time_slot.id == time_slot.id and entry.day.id == day.id:
                    day_entry_list.append(entries_dict[entry.id])
            day_entries_list.append(day_entry_list)
        
        rows.append({
            'id': time_slot.id,
            'label': f"{time_slot.start_time.strftime('%H:%M')} - {time_slot.end_time.strftime('%H:%M')}",
            'time_slot': time_slot,
            'day_entries': day_entries_list  # List of lists for easy template access
        })
    
    # Check if user has any entries
    has_entries = len(my_entries) > 0
    
    context = {
        'college': college,
        'days': days,
        'rows': rows,
        'time_slots': time_slots,
        'has_entries': has_entries,
        'total_entries': len(my_entries),
    }
    return render(request, 'timetable/my_timetable.html', context)


@login_required
@verify_college_access
@director_blocked_from_timetable
def course_specific_timetable(request, college_slug=None, course_id=None):
    """View course-specific timetable - Director blocked. Shows published generated timetables."""
    college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
    
    courses = CollegeCourse.objects.filter(college=college).order_by('name')
    selected_course = None
    active_timetable = None
    timetable_data = None
    
    if course_id:
        try:
            selected_course = CollegeCourse.objects.get(id=course_id, college=college)
            # Get published generated timetable for this course
            active_timetable = TimetableRun.objects.filter(
                college=college,
                course=selected_course,
                status='published'
            ).order_by('-published_at').first()
            
            if active_timetable:
                timetable_data = build_timetable_table(active_timetable)
        except CollegeCourse.DoesNotExist:
            messages.error(request, 'Course not found.')
    
    context = {
        'college': college,
        'courses': courses,
        'selected_course': selected_course,
        'active_timetable': active_timetable,
        'timetable_data': timetable_data,
    }
    return render(request, 'timetable/course_specific_timetable.html', context)


@login_required
@verify_college_access
@director_blocked_from_timetable
def generate_timetable(request, college_slug=None):
    """Generate timetable - Visible to all except Director. Shows validation and preview."""
    college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
    
    if request.method == 'POST' and request.user.is_registrar():
        action = request.POST.get('action')
        
        if action == 'generate':
            # Use global settings from college
            academic_year = college.current_academic_year
            semester = college.current_semester
            
            if not academic_year or not semester:
                return JsonResponse({
                    'success': False,
                    'message': 'Academic year and semester must be set in college settings.',
                    'errors': ['Please configure academic year and semester in college settings before generating timetable.']
                })
            
            # Generate for all eligible courses (general timetable)
            # Get or create timetable run (general - no course)
            timetable_run, created = TimetableRun.objects.get_or_create(
                college=college,
                course=None,  # General timetable
                academic_year=academic_year,
                semester=int(semester),
                defaults={
                    'status': 'draft',
                    'created_by': request.user,
                    'notes': 'Auto-generated for all eligible courses'
                }
            )
            
            if not created:
                # Only allow regeneration if not published
                if timetable_run.status == 'published':
                    return JsonResponse({
                        'success': False,
                        'message': 'Cannot regenerate a published timetable. Create a new one instead.',
                        'errors': ['Timetable is already published and locked.']
                    })
                timetable_run.status = 'draft'
                timetable_run.save()
            
            # Generate timetable using the service
            result = generate_timetable_service(timetable_run)
            
            if result['success']:
                return JsonResponse({
                    'success': True,
                    'message': result['message'],
                    'run_id': timetable_run.id
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': result['message'],
                    'errors': result.get('errors', []),
                    'recommendations': result.get('recommendations', [])
                })
        
        return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)
    
    # GET request - show page
    courses = CollegeCourse.objects.filter(college=college).order_by('name')
    timetable_runs = TimetableRun.objects.filter(college=college).order_by('-created_at')[:10]
    
    # Get reference data counts
    days_count = TimetableDay.objects.count()
    time_slots_count = TimeSlot.objects.count()
    classrooms_count = Classroom.objects.filter(college=college).count()
    
    context = {
        'college': college,
        'courses': courses,
        'timetable_runs': timetable_runs,
        'current_academic_year': college.current_academic_year,
        'current_semester': college.current_semester,
        'days_count': days_count,
        'time_slots_count': time_slots_count,
        'classrooms_count': classrooms_count,
        'is_registrar': request.user.is_registrar(),
    }
    return render(request, 'timetable/generate_timetable.html', context)


@login_required
@verify_college_access
@registrar_required_for_timetable
def deploy_timetable(request, college_slug=None, timetable_run_id=None):
    """Deploy timetable - Only if status = generated. Changes to published and locks editing."""
    college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
    
    timetable_run = get_object_or_404(TimetableRun, id=timetable_run_id, college=college)
    
    if timetable_run.status != 'generated':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({
                'success': False,
                'error': f'Can only deploy timetables with status "generated". Current status: {timetable_run.get_status_display()}.'
            }, status=400)
        messages.error(request, f'Can only deploy timetables with status "generated". Current status: {timetable_run.get_status_display()}.')
        return redirect('timetable:generate_timetable')
    
    # Deploy: change status to published
    timetable_run.status = 'published'
    timetable_run.published_at = timezone.now()
    timetable_run.save()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({
            'success': True,
            'message': 'Timetable deployed successfully. It is now visible to students and locked from editing.'
        })
    
    messages.success(request, 'Timetable deployed successfully. It is now visible to students and locked from editing.')
    return redirect('timetable:generate_timetable')


@login_required
@verify_college_access
@director_blocked_from_timetable
def export_timetable_pdf(request, college_slug=None, timetable_run_id=None):
    """Export timetable as PDF - Director blocked"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    
    college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
    timetable_run = get_object_or_404(TimetableRun, id=timetable_run_id, college=college)
    
    # Only allow export of published timetables (or generated for registrar)
    if timetable_run.status not in ['published', 'generated']:
        messages.error(request, 'Can only export published or generated timetables.')
        return redirect('timetable:general_timetable')
    
    # Build timetable data
    timetable_data = build_timetable_table(timetable_run)
    
    # Create PDF response
    response = HttpResponse(content_type='application/pdf')
    filename = f"timetable_{college.get_slug()}_{timetable_run.academic_year}_sem{timetable_run.semester}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Create PDF document
    doc = SimpleDocTemplate(response, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=12,
        alignment=TA_CENTER
    )
    
    # Header
    story.append(Paragraph(college.name, title_style))
    subtitle = f"Timetable - {timetable_run.academic_year} Semester {timetable_run.semester}"
    if timetable_run.course:
        subtitle += f" - {timetable_run.course.name}"
    story.append(Paragraph(subtitle, styles['Heading2']))
    story.append(Spacer(1, 12))
    
    # Build table data
    days = timetable_data['days']
    time_slots = timetable_data['time_slots']
    table_data_dict = timetable_data['table_rows']
    
    # Table header
    table_data_list = []
    header = ['Time']
    for day in days:
        header.append(day.name)
    table_data_list.append(header)
    
    # Table rows
    for row in table_data_dict:
        time_slot = row['time_slot']
        row_data = [f"{time_slot.start_time.strftime('%H:%M')} - {time_slot.end_time.strftime('%H:%M')}"]
        for entry in row['day_entries']:
            if entry:
                cell_text = f"{entry.unit.code}\n{entry.unit.name}\n{entry.lecturer.get_full_name() if entry.lecturer else 'TBA'}\n{entry.classroom.name if entry.classroom else 'TBA'}"
                row_data.append(cell_text)
            else:
                row_data.append('')
        table_data_list.append(row_data)
    
    # Create table
    table = Table(table_data_list, repeatRows=1)
    
    # Style the table
    table_style = TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        
        # Data rows
        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#ecf0f1')),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (0, -1), 9),
        ('FONTSIZE', (1, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
    ])
    
    table.setStyle(table_style)
    story.append(table)
    
    # Build PDF
    doc.build(story)
    
    return response


@login_required
@verify_college_access
@registrar_required_for_timetable
def edit_timetable(request, college_slug=None, timetable_id=None):
    """Edit timetable - Only Registrar can access"""
    college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
    
    timetable = get_object_or_404(CollegeTimetable, id=timetable_id, college=college)
    
    if request.method == 'POST':
        course_id = request.POST.get('course_id')
        academic_year = request.POST.get('academic_year')
        semester = request.POST.get('semester')
        description = request.POST.get('description', '')
        is_active = request.POST.get('is_active') == 'on'
        
        uploaded_file = request.FILES.get('image') or request.FILES.get('file')
        if uploaded_file:
            is_pdf = uploaded_file.name.lower().endswith('.pdf') or uploaded_file.content_type == 'application/pdf'
            if is_pdf:
                timetable.file = uploaded_file
                timetable.image = None  # Clear image if uploading PDF
            else:
                timetable.image = uploaded_file
                timetable.file = None  # Clear file if uploading image
        
        if course_id:
            try:
                timetable.course = CollegeCourse.objects.get(id=course_id, college=college)
            except CollegeCourse.DoesNotExist:
                messages.error(request, 'Invalid course selected.')
        else:
            timetable.course = None
        
        timetable.academic_year = academic_year or None
        timetable.semester = int(semester) if semester else None
        timetable.description = description
        timetable.is_active = is_active
        timetable.save()
        
        messages.success(request, 'Timetable updated successfully.')
        return redirect('timetable:upload_timetable')
    
    courses = CollegeCourse.objects.filter(college=college).order_by('name')
    
    context = {
        'college': college,
        'timetable': timetable,
        'courses': courses,
    }
    return render(request, 'timetable/edit_timetable.html', context)


@login_required
@verify_college_access
@registrar_required_for_timetable
def delete_timetable(request, college_slug=None, timetable_id=None):
    """Delete timetable (soft delete) - Only Registrar can access"""
    college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
    
    timetable = get_object_or_404(CollegeTimetable, id=timetable_id, college=college)
    timetable.is_active = False
    timetable.save()
    
    messages.success(request, 'Timetable deleted successfully.')
    return redirect('timetable:upload_timetable')


def build_timetable_table(timetable_run):
    """
    Build timetable table data structure for display.
    Returns dict with days as columns and time slots as rows.
    """
    entries = TimetableEntry.objects.filter(
        timetable=timetable_run
    ).select_related('day', 'time_slot', 'course', 'unit', 'lecturer', 'classroom').order_by(
        'day__order_index', 'time_slot__start_time'
    )
    
    # Get all days and time slots
    days = list(TimetableDay.objects.all().order_by('order_index'))
    time_slots = list(TimeSlot.objects.all().order_by('start_time'))
    
    # Build table structure - list of rows, each row is [time_slot, [entries for each day]]
    table_rows = []
    for time_slot in time_slots:
        row = {
            'time_slot': time_slot,
            'day_entries': [None] * len(days)  # Initialize with None for each day
        }
        # Fill in entries for this time slot
        for entry in entries:
            if entry.time_slot.id == time_slot.id:
                day_index = next((i for i, d in enumerate(days) if d.id == entry.day.id), None)
                if day_index is not None:
                    row['day_entries'][day_index] = entry
        table_rows.append(row)
    
    return {
        'days': days,
        'time_slots': time_slots,
        'table_rows': table_rows,
        'timetable_run': timetable_run
    }


def build_timetable_grid(timetable_run, view_mode='course'):
    """
    Build timetable grid data structure for ASC-style display.
    Returns dict with days as columns and courses/lecturers as rows.
    
    Args:
        timetable_run: TimetableRun instance
        view_mode: 'course' or 'lecturer'
    
    Returns:
        dict: {
            'days': [day objects],
            'rows': [{'id': row_id, 'label': row_label, 'day_entries': [entries per day]}],
            'entries': {entry_id: entry_data},
            'all_days': [all days],
            'all_time_slots': [all time slots],
            'all_classrooms': [all classrooms],
            'all_lecturers': [all lecturers]
        }
    """
    entries = TimetableEntry.objects.filter(
        timetable=timetable_run
    ).select_related('day', 'time_slot', 'course', 'unit', 'lecturer', 'classroom').order_by(
        'day__order_index', 'time_slot__start_time'
    )
    
    days = list(TimetableDay.objects.all().order_by('order_index'))
    
    # Build entries dictionary with full details
    entries_dict = {}
    for entry in entries:
        entries_dict[entry.id] = {
            'id': entry.id,
            'day_id': entry.day.id,
            'day_name': entry.day.name,
            'time_slot_id': entry.time_slot.id,
            'time_slot_start': entry.time_slot.start_time.strftime('%H:%M'),
            'time_slot_end': entry.time_slot.end_time.strftime('%H:%M'),
            'course_id': entry.course.id,
            'course_name': entry.course.name,
            'unit_id': entry.unit.id,
            'unit_code': entry.unit.code,
            'unit_name': entry.unit.name,
            'lecturer_id': entry.lecturer.id if entry.lecturer else None,
            'lecturer_name': entry.lecturer.get_full_name() if entry.lecturer else 'TBA',
            'classroom_id': entry.classroom.id if entry.classroom else None,
            'classroom_name': entry.classroom.name if entry.classroom else 'TBA',
        }
    
    # Build rows based on view mode
    if view_mode == 'course':
        # Group by course
        courses_dict = {}
        for entry in entries:
            course_id = entry.course.id
            if course_id not in courses_dict:
                courses_dict[course_id] = {
                    'id': course_id,
                    'label': entry.course.name,
                    'day_entries': {day.id: [] for day in days}
                }
            courses_dict[course_id]['day_entries'][entry.day.id].append(entry.id)
        
        rows = list(courses_dict.values())
    elif view_mode == 'lecturer':
        # Group by lecturer
        lecturers_dict = {}
        for entry in entries:
            lecturer_id = entry.lecturer.id if entry.lecturer else None
            if lecturer_id:
                if lecturer_id not in lecturers_dict:
                    lecturers_dict[lecturer_id] = {
                        'id': lecturer_id,
                        'label': entry.lecturer.get_full_name(),
                        'day_entries': {day.id: [] for day in days}
                    }
                lecturers_dict[lecturer_id]['day_entries'][entry.day.id].append(entry.id)
        
        rows = list(lecturers_dict.values())
    else:  # classroom view
        # Group by classroom
        classrooms_dict = {}
        for entry in entries:
            classroom_id = entry.classroom.id if entry.classroom else None
            if classroom_id:
                if classroom_id not in classrooms_dict:
                    classrooms_dict[classroom_id] = {
                        'id': classroom_id,
                        'label': entry.classroom.name,
                        'day_entries': {day.id: [] for day in days}
                    }
                classrooms_dict[classroom_id]['day_entries'][entry.day.id].append(entry.id)
        
        rows = list(classrooms_dict.values())
    
    # Get all reference data for editing
    from .models import TimeSlot, Classroom
    from education.models import CustomUser
    
    all_time_slots = list(TimeSlot.objects.all().order_by('start_time'))
    all_classrooms = list(Classroom.objects.filter(college=timetable_run.college).order_by('name'))
    all_lecturers = list(CustomUser.objects.filter(college=timetable_run.college, role='lecturer').order_by('first_name', 'last_name'))
    
    return {
        'days': days,
        'rows': rows,
        'entries': entries_dict,
        'all_days': [{'id': d.id, 'name': d.name} for d in days],
        'all_time_slots': [{'id': ts.id, 'start': ts.start_time.strftime('%H:%M'), 'end': ts.end_time.strftime('%H:%M')} for ts in all_time_slots],
        'all_classrooms': [{'id': c.id, 'name': c.name} for c in all_classrooms],
        'all_lecturers': [{'id': l.id, 'name': l.get_full_name()} for l in all_lecturers],
    }


# Management views for reference data
@login_required
@verify_college_access
@director_blocked_from_timetable
def manage_classrooms(request, college_slug=None):
    """Manage classrooms - visible to all except Director"""
    college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
    
    classrooms = Classroom.objects.filter(college=college).order_by('name')
    
    if request.method == 'POST' and request.user.is_registrar():
        if 'add' in request.POST:
            form = ClassroomForm(request.POST)
            if form.is_valid():
                classroom = form.save(commit=False)
                classroom.college = college
                classroom.save()
                messages.success(request, f'Classroom "{classroom.name}" added successfully.')
                return redirect('timetable:manage_classrooms')
        elif 'delete' in request.POST:
            classroom_id = request.POST.get('classroom_id')
            try:
                classroom = Classroom.objects.get(id=classroom_id, college=college)
                classroom.delete()
                messages.success(request, 'Classroom deleted successfully.')
            except Classroom.DoesNotExist:
                messages.error(request, 'Classroom not found.')
            return redirect('timetable:manage_classrooms')
    
    form = ClassroomForm() if request.user.is_registrar() else None
    
    context = {
        'college': college,
        'classrooms': classrooms,
        'form': form,
        'is_registrar': request.user.is_registrar(),
    }
    return render(request, 'timetable/manage_classrooms.html', context)


@login_required
@verify_college_access
@director_blocked_from_timetable
def manage_days(request, college_slug=None):
    """Manage timetable days - visible to all except Director"""
    days = TimetableDay.objects.all().order_by('order_index')
    
    if request.method == 'POST' and request.user.is_registrar():
        if 'add' in request.POST:
            form = TimetableDayForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, f'Day "{form.cleaned_data["name"]}" added successfully.')
                return redirect('timetable:manage_days')
        elif 'delete' in request.POST:
            day_id = request.POST.get('day_id')
            try:
                day = TimetableDay.objects.get(id=day_id)
                day.delete()
                messages.success(request, 'Day deleted successfully.')
            except TimetableDay.DoesNotExist:
                messages.error(request, 'Day not found.')
            return redirect('timetable:manage_days')
    
    form = TimetableDayForm() if request.user.is_registrar() else None
    
    context = {
        'days': days,
        'form': form,
        'is_registrar': request.user.is_registrar(),
    }
    return render(request, 'timetable/manage_days.html', context)


@login_required
@verify_college_access
@director_blocked_from_timetable
def manage_time_slots(request, college_slug=None):
    """Manage time slots - visible to all except Director"""
    time_slots = TimeSlot.objects.all().order_by('start_time')
    
    if request.method == 'POST' and request.user.is_registrar():
        if 'add' in request.POST:
            form = TimeSlotForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, f'Time slot "{form.instance}" added successfully.')
                return redirect('timetable:manage_time_slots')
        elif 'delete' in request.POST:
            slot_id = request.POST.get('slot_id')
            try:
                slot = TimeSlot.objects.get(id=slot_id)
                slot.delete()
                messages.success(request, 'Time slot deleted successfully.')
            except TimeSlot.DoesNotExist:
                messages.error(request, 'Time slot not found.')
            return redirect('timetable:manage_time_slots')
    
    form = TimeSlotForm() if request.user.is_registrar() else None
    
    context = {
        'time_slots': time_slots,
        'form': form,
        'is_registrar': request.user.is_registrar(),
    }
    return render(request, 'timetable/manage_time_slots.html', context)


# API endpoints for grid editing
@login_required
@verify_college_access
@registrar_required_for_timetable
def edit_timetable_entry(request, entry_id):
    """API endpoint to edit a timetable entry"""
    from django.http import JsonResponse
    from django.views.decorators.csrf import csrf_exempt
    from django.db import transaction
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    try:
        entry = TimetableEntry.objects.select_related('timetable', 'timetable__college').get(id=entry_id)
        college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
        
        # Verify entry belongs to user's college
        if entry.timetable.college.id != college.id:
            return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
        
        # Check if timetable is editable - only when status is 'generated'
        if entry.timetable.status != 'generated':
            return JsonResponse({'success': False, 'error': 'Timetable is not editable. Only generated timetables can be edited.'}, status=403)
        
        # Get new values
        day_id = request.POST.get('day_id')
        time_slot_id = request.POST.get('time_slot_id')
        classroom_id = request.POST.get('classroom_id')
        lecturer_id = request.POST.get('lecturer_id')
        
        with transaction.atomic():
            # Validate conflicts before updating
            conflicts = []
            
            if day_id and time_slot_id:
                # Check lecturer conflict
                if lecturer_id:
                    existing = TimetableEntry.objects.filter(
                        timetable=entry.timetable,
                        day_id=day_id,
                        time_slot_id=time_slot_id,
                        lecturer_id=lecturer_id
                    ).exclude(id=entry_id).first()
                    if existing:
                        conflicts.append(f"Lecturer already assigned at this time")
                
                # Check classroom conflict
                if classroom_id:
                    existing = TimetableEntry.objects.filter(
                        timetable=entry.timetable,
                        day_id=day_id,
                        time_slot_id=time_slot_id,
                        classroom_id=classroom_id
                    ).exclude(id=entry_id).first()
                    if existing:
                        conflicts.append(f"Classroom already booked at this time")
            
            if conflicts:
                return JsonResponse({
                    'success': False,
                    'error': 'Conflict detected',
                    'conflicts': conflicts
                }, status=400)
            
            # Update entry
            if day_id:
                entry.day_id = int(day_id)
            if time_slot_id:
                entry.time_slot_id = int(time_slot_id)
            if classroom_id:
                entry.classroom_id = int(classroom_id) if classroom_id else None
            if lecturer_id:
                entry.lecturer_id = int(lecturer_id) if lecturer_id else None
            
            entry.save()
        
        return JsonResponse({
            'success': True,
            'entry': {
                'id': entry.id,
                'day_id': entry.day_id,
                'day_name': entry.day.name,
                'time_slot_id': entry.time_slot_id,
                'time_slot_start': entry.time_slot.start_time.strftime('%H:%M'),
                'time_slot_end': entry.time_slot.end_time.strftime('%H:%M'),
                'classroom_id': entry.classroom_id,
                'classroom_name': entry.classroom.name if entry.classroom else 'TBA',
                'lecturer_id': entry.lecturer_id,
                'lecturer_name': entry.lecturer.get_full_name() if entry.lecturer else 'TBA',
            }
        })
    
    except TimetableEntry.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Entry not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@verify_college_access
@registrar_required_for_timetable
def toggle_edit_mode(request, run_id):
    """API endpoint to toggle edit mode for published timetables"""
    from django.http import JsonResponse
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    try:
        timetable_run = TimetableRun.objects.select_related('college').get(id=run_id)
        college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
        
        if timetable_run.college.id != college.id:
            return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
        
        # Toggle edit mode (store in session or as attribute)
        edit_mode_key = f'timetable_edit_mode_{run_id}'
        current_mode = request.session.get(edit_mode_key, False)
        new_mode = not current_mode
        request.session[edit_mode_key] = new_mode
        
        return JsonResponse({
            'success': True,
            'edit_mode_enabled': new_mode
        })
    
    except TimetableRun.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Timetable run not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@verify_college_access
def get_grid_data(request, run_id):
    """API endpoint to get grid data for a timetable run"""
    from django.http import JsonResponse
    import json
    
    try:
        timetable_run = TimetableRun.objects.select_related('college').get(id=run_id)
        college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
        
        if timetable_run.college.id != college.id:
            return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
        
        view_mode = request.GET.get('mode', 'course')
        grid_data = build_timetable_grid(timetable_run, view_mode=view_mode)
        
        # Serialize for JSON
        serialized = {
            'days': [{'id': d.id, 'name': d.name} for d in grid_data['days']],
            'rows': grid_data['rows'],
            'entries': grid_data['entries'],
            'all_days': grid_data['all_days'],
            'all_time_slots': grid_data['all_time_slots'],
            'all_classrooms': grid_data['all_classrooms'],
            'all_lecturers': grid_data['all_lecturers'],
            'status': timetable_run.status,
        }
        
        return JsonResponse({
            'success': True,
            'data': serialized
        })
    
    except TimetableRun.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Timetable run not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@verify_college_access
def api_grid_init(request):
    """API endpoint to initialize grid data (empty grid before generation)"""
    from django.http import JsonResponse
    from education.models import CollegeCourse, CustomUser
    
    college = request.verified_college if hasattr(request, 'verified_college') else request.user.college
    
    # Get all days and time slots
    days = list(TimetableDay.objects.all().order_by('order_index'))
    time_slots = list(TimeSlot.objects.all().order_by('start_time'))
    
    # Get courses, lecturers, and classrooms for row structure
    courses = list(CollegeCourse.objects.filter(college=college).order_by('name'))
    lecturers = list(CustomUser.objects.filter(college=college, role='lecturer').order_by('first_name', 'last_name'))
    classrooms = list(Classroom.objects.filter(college=college).order_by('name'))
    
    # Check for active timetable (generated or published)
    # Prioritize published, then generated
    active_run = TimetableRun.objects.filter(
        college=college,
        status__in=['generated', 'published']
    ).order_by('-published_at', '-created_at').first()
    
    return JsonResponse({
        'success': True,
        'days': [{'id': d.id, 'name': d.name} for d in days],
        'time_slots': [{'id': ts.id, 'start': ts.start_time.strftime('%H:%M'), 'end': ts.end_time.strftime('%H:%M')} for ts in time_slots],
        'courses': [{'id': c.id, 'name': c.name, 'label': c.name} for c in courses],
        'lecturers': [{'id': l.id, 'name': l.get_full_name(), 'label': l.get_full_name()} for l in lecturers],
        'classrooms': [{'id': c.id, 'name': c.name, 'label': c.name} for c in classrooms],
        'active_run': {'id': active_run.id, 'status': active_run.status} if active_run else None
    })
