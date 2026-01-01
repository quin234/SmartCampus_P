"""
API Views for college-specific endpoints
Returns JSON responses for frontend consumption
All endpoints enforce college-level data isolation
"""
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.utils.text import slugify
from django.utils import timezone
from django.db.models import Q, F, OuterRef, Subquery, Max
import json
import re
import csv
from io import StringIO
from datetime import datetime

from .models import College, Student, CollegeCourse, CollegeUnit, CustomUser, Enrollment, Result, CollegeCourseUnit, GlobalUnit, GlobalCourse, CollegeTimetable, Announcement, StudentSemesterSignIn, ReportTemplate, ReportTemplateMapping
from .utils.student_pdf_generator import (
    get_template_for_report_type,
    generate_student_results_pdf,
    generate_student_registered_units_pdf,
    generate_student_fee_structure_pdf
)
from .decorators import verify_college_access, get_college_from_slug, student_required
from accounts.models import FeeStructure, Payment
from accounts.views import calculate_expected_fees
from django.db.models import Sum
from decimal import Decimal


def verify_user_college_access(request, college):
    """
    Verify that the authenticated user has access to the specified college.
    STRICT: Super admins are BLOCKED from accessing college-specific API endpoints.
    Only college admins and lecturers can access their own college data.
    """
    if not request.user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    
    # STRICT: Super admin CANNOT access college-specific API endpoints
    # They must use superadmin API endpoints only
    if request.user.is_super_admin():
        raise PermissionDenied("Super Admin cannot access individual college data. Use Super Admin API endpoints instead.")
    
    # Regular users can only access their own college
    if not hasattr(request.user, 'college') or not request.user.college:
        raise PermissionDenied("You must be associated with a college to access this resource.")
    
    if request.user.college.id != college.id:
        raise PermissionDenied("You don't have access to this college.")
    
    return True


@login_required
@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_departments_list(request, college_slug):
    """API endpoint for departments list, create, update, delete - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        # Get all courses grouped by name (as departments)
        search = request.GET.get('search', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 10)), 50)  # Max 50
        include_courses = request.GET.get('include_courses', 'true').lower() == 'true'
        
        # For now, use course names as departments (you can create a Department model later)
        courses = CollegeCourse.objects.filter(college=college).select_related('global_course')
        if search:
            courses = courses.filter(name__icontains=search)
        
        # Get stored department metadata from college
        departments_metadata = {}
        if college.grading_criteria and 'departments' in college.grading_criteria:
            departments_metadata = college.grading_criteria.get('departments', {})
        
        # Group courses by department (using first word of course name)
        departments_dict = {}
        for course in courses:
            dept_name = course.name.split()[0] if course.name else 'General'  # Use first word as department
            
            if dept_name not in departments_dict:
                # Check if we have stored metadata for this department
                stored_meta = departments_metadata.get(dept_name, {})
                
                departments_dict[dept_name] = {
                    'id': len(departments_dict) + 1,
                    'code': stored_meta.get('code', dept_name[:3].upper()) if stored_meta.get('code') else dept_name[:3].upper(),
                    'name': stored_meta.get('name', dept_name) if stored_meta.get('name') else dept_name,
                    'description': stored_meta.get('description', f'Department for {dept_name} courses') if stored_meta.get('description') else f'Department for {dept_name} courses',
                    'courses': []
                }
            
            # Add course to department
            if include_courses:
                course_data = {
                    'id': course.id,
                    'code': course.code,
                    'name': course.name,
                    'duration': course.duration_years,
                    'global_course_id': course.global_course.id if course.global_course else None,
                    'global_course_name': course.global_course.name if course.global_course else None,
                    'global_course_level': course.global_course.get_level_display() if course.global_course else None,
                    'admission_requirements': course.admission_requirements or '',
                    'status': 'active'
                }
                departments_dict[dept_name]['courses'].append(course_data)
        
        # Add standalone departments (departments in metadata but no courses yet)
        for dept_name, dept_meta in departments_metadata.items():
            if dept_name not in departments_dict:
                # This is a standalone department (created but no courses assigned)
                departments_dict[dept_name] = {
                    'id': len(departments_dict) + 1,
                    'code': dept_meta.get('code', dept_name[:3].upper()),
                    'name': dept_meta.get('name', dept_name),
                    'description': dept_meta.get('description', f'Department for {dept_name} courses'),
                    'courses': []
                }
        
        # Convert to list and add course_count
        departments = []
        for dept_name, dept_data in departments_dict.items():
            dept_data['course_count'] = len(dept_data['courses'])
            departments.append(dept_data)
        
        # Sort departments by name
        departments.sort(key=lambda x: x['name'])
        
        paginator = Paginator(departments, page_size)
        page_obj = paginator.get_page(page)
        
        return JsonResponse({
            'count': paginator.count,
            'results': list(page_obj),
            'next': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'page': page_obj.number,
            'total_pages': paginator.num_pages
        })
    
    elif request.method == 'POST':
        # Create new department
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        
        dept_name = data.get('name', '').strip()
        dept_code = data.get('code', '').strip()
        dept_description = data.get('description', '').strip()
        
        if not dept_name:
            return JsonResponse({'error': 'Department name is required'}, status=400)
        
        if not dept_code:
            return JsonResponse({'error': 'Department code is required'}, status=400)
        
        # Initialize departments metadata storage
        if not college.grading_criteria:
            college.grading_criteria = {}
        if 'departments' not in college.grading_criteria:
            college.grading_criteria['departments'] = {}
        
        departments_metadata = college.grading_criteria.get('departments', {})
        
        # Check if department with this name already exists
        if dept_name in departments_metadata:
            return JsonResponse({'error': f'Department "{dept_name}" already exists'}, status=400)
        
        # Save new department metadata
        departments_metadata[dept_name] = {
            'code': dept_code,
            'name': dept_name,
            'description': dept_description
        }
        
        # Save to college
        college.grading_criteria['departments'] = departments_metadata
        try:
            college.save(update_fields=['grading_criteria', 'updated_at'])
        except Exception as e:
            return JsonResponse({'error': f'Failed to save department: {str(e)}'}, status=500)
        
        # Return created department
        return JsonResponse({
            'id': len(departments_metadata),  # Sequential ID for compatibility
            'code': dept_code,
            'name': dept_name,
            'description': dept_description
        }, status=201)
    
    elif request.method in ['PUT', 'PATCH']:
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        
        dept_id = data.get('id')
        old_name = data.get('old_name', '').strip()  # Original department name to identify which department
        new_name = data.get('name', '').strip()
        new_code = data.get('code', '').strip()
        new_description = data.get('description', '').strip()
        
        if not dept_id:
            return JsonResponse({'error': 'Department ID is required'}, status=400)
        
        if not new_name:
            return JsonResponse({'error': 'Department name is required'}, status=400)
        
        # Initialize departments metadata storage in college's grading_criteria
        if not college.grading_criteria:
            college.grading_criteria = {}
        if 'departments' not in college.grading_criteria:
            college.grading_criteria['departments'] = {}
        
        departments_metadata = college.grading_criteria.get('departments', {})
        
        # Determine the key to use for lookup
        # If old_name is provided, use it; otherwise try to find by matching existing metadata
        dept_key = None
        if old_name:
            dept_key = old_name
        else:
            # Try to find department by matching name or code in existing metadata
            for key, meta in departments_metadata.items():
                if meta.get('name') == new_name or meta.get('code') == new_code:
                    dept_key = key
                    break
        
        # If still not found and we have old_name, use it anyway
        if not dept_key and old_name:
            dept_key = old_name
        
        # If name changed, update the key
        if dept_key and old_name and new_name and old_name != new_name:
            # Remove old key and create new one
            if dept_key in departments_metadata:
                departments_metadata[new_name] = departments_metadata.pop(dept_key)
            else:
                departments_metadata[new_name] = {}
            dept_key = new_name
        elif not dept_key:
            # New department (shouldn't happen in PUT, but handle it)
            dept_key = new_name
            if dept_key not in departments_metadata:
                departments_metadata[dept_key] = {}
        
        # Update department metadata
        departments_metadata[dept_key] = {
            'code': new_code,
            'name': new_name,
            'description': new_description
        }
        
        # Save to college - this is critical!
        college.grading_criteria['departments'] = departments_metadata
        try:
            college.save(update_fields=['grading_criteria', 'updated_at'])
        except Exception as e:
            return JsonResponse({'error': f'Failed to save department: {str(e)}'}, status=500)
        
        return JsonResponse({
            'id': dept_id,
            'code': new_code,
            'name': new_name,
            'description': new_description
        })
    
    elif request.method == 'DELETE':
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            data = {}
        
        dept_id = data.get('id')
        old_name = data.get('old_name', '').strip()
        
        if not dept_id:
            return JsonResponse({'error': 'Department ID is required'}, status=400)
        
        # Get department metadata
        if not college.grading_criteria:
            college.grading_criteria = {}
        if 'departments' not in college.grading_criteria:
            college.grading_criteria['departments'] = {}
        
        departments_metadata = college.grading_criteria.get('departments', {})
        
        # Find and remove the department
        # Use old_name if provided, otherwise try to find by matching
        dept_key = None
        if old_name:
            dept_key = old_name
        else:
            # Try to find by iterating through metadata
            for key in list(departments_metadata.keys()):
                if key:  # If we have any department, we'll delete the first matching one
                    dept_key = key
                    break
        
        # Remove department from metadata
        if dept_key and dept_key in departments_metadata:
            del departments_metadata[dept_key]
            college.grading_criteria['departments'] = departments_metadata
            try:
                college.save(update_fields=['grading_criteria', 'updated_at'])
            except Exception as e:
                return JsonResponse({'error': f'Failed to delete department: {str(e)}'}, status=500)
        
        # Return 204 No Content (no body)
        return HttpResponse(status=204)


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def api_department_detail(request, college_slug, pk):
    """API endpoint for department detail, update, delete - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        # Return placeholder department
        return JsonResponse({
            'id': pk,
            'code': 'DEPT',
            'name': 'Department',
            'description': 'Department description'
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        return JsonResponse({
            'id': pk,
            'code': data.get('code', ''),
            'name': data.get('name', ''),
            'description': data.get('description', '')
        })
    
    elif request.method == 'DELETE':
        return JsonResponse({'success': True}, status=204)


@login_required
@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_courses_list(request, college_slug):
    """API endpoint for courses list, create, update, delete - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        search = request.GET.get('search', '')
        department = request.GET.get('department', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 10)), 50)  # Max 50
        
        courses = CollegeCourse.objects.filter(college=college).select_related('global_course')
        if search:
            courses = courses.filter(name__icontains=search)
        
        # Optimize: Paginate queryset first, then build list (more efficient)
        paginator = Paginator(courses, page_size)
        page_obj = paginator.get_page(page)
        
        courses_list = []
        for course in page_obj:
            courses_list.append({
                'id': course.id,
                'code': course.code,
                'name': course.name,
                'department_id': 1,  # Placeholder
                'department_name': course.name.split()[0] if course.name else 'General',
                'duration': course.duration_years,
                'global_course_id': course.global_course.id if course.global_course else None,
                'global_course_name': course.global_course.name if course.global_course else None,
                'global_course_level': course.global_course.get_level_display() if course.global_course else None,
                'admission_requirements': course.admission_requirements or '',
                'status': 'active'
            })
        
        return JsonResponse({
            'count': paginator.count,
            'results': courses_list,
            'next': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'page': page_obj.number,
            'total_pages': paginator.num_pages
        })
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        
        course_name = data.get('name', '').strip()
        course_code = data.get('code', '').strip().upper()
        department_name = data.get('department_name', '').strip()
        
        if not course_name:
            return JsonResponse({'error': 'Course name is required'}, status=400)
        
        if not course_code:
            return JsonResponse({'error': 'Course code is required'}, status=400)
        
        course = CollegeCourse.objects.create(
            college=college,
            code=course_code,
            name=course_name,
            duration_years=data.get('duration', 1),
            global_course_id=data.get('global_course_id') if data.get('global_course_id') else None,
            admission_requirements=data.get('admission_requirements', '')
        )
        
        # Extract department name from course name (first word)
        dept_name = course.name.split()[0] if course.name else 'General'
        
        return JsonResponse({
            'id': course.id,
            'code': course.code,
            'name': course.name,
            'department_id': 1,
            'department_name': dept_name,
            'duration': course.duration_years,
            'global_course_id': course.global_course.id if course.global_course else None,
            'global_course_name': course.global_course.name if course.global_course else None,
            'global_course_level': course.global_course.get_level_display() if course.global_course else None,
            'admission_requirements': course.admission_requirements or '',
            'status': 'active'
        }, status=201)
    
    elif request.method in ['PUT', 'PATCH']:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        course_id = data.get('id')
        if not course_id:
            return JsonResponse({'error': 'Course ID is required'}, status=400)
        
        try:
            course = CollegeCourse.objects.get(pk=course_id, college=college)
        except CollegeCourse.DoesNotExist:
            return JsonResponse({'error': 'Course not found'}, status=404)
        
        course.name = data.get('name', course.name)
        course.duration_years = data.get('duration', course.duration_years)
        
        # Handle code updates
        if 'code' in data:
            course.code = data.get('code', '').strip().upper()
        
        # Handle global_course_id updates
        if 'global_course_id' in data:
            course.global_course_id = data.get('global_course_id') if data.get('global_course_id') else None
        
        # Handle admission_requirements updates
        if 'admission_requirements' in data:
            course.admission_requirements = data.get('admission_requirements', '')
        
        course.save()
        
        return JsonResponse({
            'id': course.id,
            'code': course.code,
            'name': course.name,
            'department_id': 1,
            'duration': course.duration_years,
            'global_course_id': course.global_course.id if course.global_course else None,
            'global_course_name': course.global_course.name if course.global_course else None,
            'global_course_level': course.global_course.get_level_display() if course.global_course else None,
            'admission_requirements': course.admission_requirements or '',
            'status': 'active'
        })
    
    elif request.method == 'DELETE':
        data = json.loads(request.body) if request.body else {}
        course_id = data.get('id')
        if not course_id:
            return JsonResponse({'error': 'Course ID is required'}, status=400)
        
        try:
            course = CollegeCourse.objects.get(pk=course_id, college=college)
            course.delete()
            return JsonResponse({'success': True}, status=204)
        except CollegeCourse.DoesNotExist:
            return JsonResponse({'error': 'Course not found'}, status=404)


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_global_courses_list(request, college_slug):
    """API endpoint for global courses list - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        search = request.GET.get('search', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 50)), 100)  # Max 100 for search results
        
        global_courses = GlobalCourse.objects.all()
        if search:
            global_courses = global_courses.filter(name__icontains=search)
        
        global_courses_list = []
        for course in global_courses:
            global_courses_list.append({
                'id': course.id,
                'name': course.name,
                'level': course.level,
                'level_display': course.get_level_display(),
                'category': course.category
            })
        
        paginator = Paginator(global_courses_list, page_size)
        page_obj = paginator.get_page(page)
        
        return JsonResponse({
            'count': paginator.count,
            'results': list(page_obj),
            'next': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'page': page_obj.number,
            'total_pages': paginator.num_pages
        })


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def api_course_detail(request, college_slug, pk):
    """API endpoint for course detail, update, delete - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    try:
        course = CollegeCourse.objects.get(pk=pk, college=college)
    except CollegeCourse.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    if request.method == 'GET':
        return JsonResponse({
            'id': course.id,
            'code': getattr(course, 'code', f'COURSE{course.id}'),
            'name': course.name,
            'department_id': 1,
            'duration': course.duration_years,
            'status': 'active'
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        course.name = data.get('name', course.name)
        course.duration_years = data.get('duration', course.duration_years)
        course.save()
        return JsonResponse({
            'id': course.id,
            'code': getattr(course, 'code', f'COURSE{course.id}'),
            'name': course.name,
            'department_id': 1,
            'duration': course.duration_years,
            'status': 'active'
        })
    
    elif request.method == 'DELETE':
        course.delete()
        return JsonResponse({'success': True}, status=204)


@login_required
@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_units_list(request, college_slug):
    """API endpoint for units list, create, update, delete - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        search = request.GET.get('search', '')
        department = request.GET.get('department', '')
        course = request.GET.get('course', '')
        lecturer = request.GET.get('lecturer', '')
        semester = request.GET.get('semester', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 50)), 100)  # Increased for search results
        
        units = CollegeUnit.objects.filter(college=college).select_related('assigned_lecturer', 'global_unit')
        
        if search:
            units = units.filter(Q(name__icontains=search) | Q(code__icontains=search))
        if lecturer:
            units = units.filter(assigned_lecturer_id=lecturer)
        if semester:
            units = units.filter(semester=int(semester))
        if course:
            # Filter by course through course-unit assignments
            units = units.filter(course_assignments__course_id=course).distinct()
        
        # Optimize: Paginate queryset first, then build list (more efficient)
        paginator = Paginator(units, page_size)
        page_obj = paginator.get_page(page)
        
        # Get all unit IDs from the page
        unit_ids = [unit.id for unit in page_obj]
        
        # Get course assignments for these units in one query
        course_assignments_map = {}
        if unit_ids:
            assignments = CollegeCourseUnit.objects.filter(
                unit_id__in=unit_ids,
                college=college
            ).select_related('course').values('unit_id', 'course_id', 'course__name', 'year_of_study', 'semester')
            
            for assignment in assignments:
                unit_id = assignment['unit_id']
                if unit_id not in course_assignments_map:
                    course_assignments_map[unit_id] = []
                course_assignments_map[unit_id].append({
                    'course_id': assignment['course_id'],
                    'course_name': assignment['course__name'],
                    'year': assignment['year_of_study'],
                    'semester': assignment['semester']
                })
        
        # Get course assignments for each unit
        units_list = []
        for unit in page_obj:
            # Get course assignments from the map (already formatted)
            courses_info = course_assignments_map.get(unit.id, [])
            
            units_list.append({
                'id': unit.id,
                'code': unit.code,
                'name': unit.name,
                'department_id': 1,
                'department_name': 'General',
                'semester': unit.semester,
                'lecturer_id': unit.assigned_lecturer.id if unit.assigned_lecturer else None,
                'lecturer_name': f"{unit.assigned_lecturer.first_name} {unit.assigned_lecturer.last_name}".strip() if unit.assigned_lecturer else None,
                'global_unit_id': unit.global_unit.id if unit.global_unit else None,
                'global_unit_code': unit.global_unit.code if unit.global_unit else None,
                'global_unit_name': unit.global_unit.name if unit.global_unit else None,
                'course_assignments': courses_info,
                'status': 'active'
            })
        
        # If no pagination needed (search mode), return all results
        if search or lecturer or semester or course:
            return JsonResponse({
                'count': len(units_list),
                'results': units_list,
                'next': None,
                'previous': None,
                'page': 1,
                'total_pages': 1
            })
        else:
            # Paginate only when no filters are applied
            paginator = Paginator(units_list, page_size)
            page_obj = paginator.get_page(page)
            
            return JsonResponse({
                'count': paginator.count,
                'results': list(page_obj),
                'next': page_obj.next_page_number() if page_obj.has_next() else None,
                'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
                'page': page_obj.number,
                'total_pages': paginator.num_pages
            })
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        unit = CollegeUnit.objects.create(
            college=college,
            name=data.get('name', ''),
            code=data.get('code', ''),
            semester=data.get('semester', 1),
            global_unit_id=data.get('global_unit_id') if data.get('global_unit_id') else None,
            assigned_lecturer_id=data.get('assigned_lecturer_id') or data.get('lecturer') if (data.get('assigned_lecturer_id') or data.get('lecturer')) else None
        )
        return JsonResponse({
            'id': unit.id,
            'code': unit.code,
            'name': unit.name,
            'department_id': data.get('department', 1),
            'course_id': data.get('course'),
            'year': data.get('year', 1),
            'semester': unit.semester,
            'lecturer_id': unit.assigned_lecturer.id if unit.assigned_lecturer else None,
            'lecturer_name': f"{unit.assigned_lecturer.first_name} {unit.assigned_lecturer.last_name}".strip() if unit.assigned_lecturer else None,
            'global_unit_id': unit.global_unit.id if unit.global_unit else None,
            'global_unit_code': unit.global_unit.code if unit.global_unit else None,
            'global_unit_name': unit.global_unit.name if unit.global_unit else None,
            'status': data.get('status', 'active')
        }, status=201)
    
    elif request.method in ['PUT', 'PATCH']:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        unit_id = data.get('id')
        if not unit_id:
            return JsonResponse({'error': 'Unit ID is required'}, status=400)
        
        try:
            unit = CollegeUnit.objects.get(pk=unit_id, college=college)
        except CollegeUnit.DoesNotExist:
            return JsonResponse({'error': 'Unit not found'}, status=404)
        
        unit.name = data.get('name', unit.name)
        unit.code = data.get('code', unit.code)
        unit.semester = data.get('semester', unit.semester)
        
        # Handle global_unit_id updates
        if 'global_unit_id' in data:
            unit.global_unit_id = data.get('global_unit_id') if data.get('global_unit_id') else None
        
        # Handle assigned_lecturer_id updates
        if 'assigned_lecturer_id' in data or 'lecturer' in data:
            unit.assigned_lecturer_id = data.get('assigned_lecturer_id') or data.get('lecturer') if (data.get('assigned_lecturer_id') or data.get('lecturer')) else None
        
        unit.save()
        
        return JsonResponse({
            'id': unit.id,
            'code': unit.code,
            'name': unit.name,
            'department_id': data.get('department', 1),
            'course_id': data.get('course'),
            'year': data.get('year', 1),
            'semester': unit.semester,
            'lecturer_id': unit.assigned_lecturer.id if unit.assigned_lecturer else None,
            'lecturer_name': f"{unit.assigned_lecturer.first_name} {unit.assigned_lecturer.last_name}".strip() if unit.assigned_lecturer else None,
            'global_unit_id': unit.global_unit.id if unit.global_unit else None,
            'global_unit_code': unit.global_unit.code if unit.global_unit else None,
            'global_unit_name': unit.global_unit.name if unit.global_unit else None,
            'status': data.get('status', 'active')
        })
    
    elif request.method == 'DELETE':
        data = json.loads(request.body) if request.body else {}
        unit_id = data.get('id')
        if not unit_id:
            return JsonResponse({'error': 'Unit ID is required'}, status=400)
        
        try:
            unit = CollegeUnit.objects.get(pk=unit_id, college=college)
            unit.delete()
            return JsonResponse({'success': True}, status=204)
        except CollegeUnit.DoesNotExist:
            return JsonResponse({'error': 'Unit not found'}, status=404)


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_global_units_list(request, college_slug):
    """API endpoint for global units list - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        search = request.GET.get('search', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 50)), 100)  # Max 100 for search results
        
        global_units = GlobalUnit.objects.all()
        if search:
            global_units = global_units.filter(
                code__icontains=search
            ) | global_units.filter(
                name__icontains=search
            )
        
        global_units_list = []
        for unit in global_units:
            global_units_list.append({
                'id': unit.id,
                'code': unit.code,
                'name': unit.name
            })
        
        paginator = Paginator(global_units_list, page_size)
        page_obj = paginator.get_page(page)
        
        return JsonResponse({
            'count': paginator.count,
            'results': list(page_obj),
            'next': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'page': page_obj.number,
            'total_pages': paginator.num_pages
        })


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def api_unit_detail(request, college_slug, pk):
    """API endpoint for unit detail, update, delete - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    try:
        unit = CollegeUnit.objects.get(pk=pk, college=college)
    except CollegeUnit.DoesNotExist:
        return JsonResponse({'error': 'Unit not found'}, status=404)
    
    if request.method == 'GET':
        # Get all course assignments for this unit
        course_assignments = CollegeCourseUnit.objects.filter(
            unit=unit,
            college=college
        ).select_related('course').order_by('course__name', 'year_of_study', 'semester')
        
        courses_info = []
        for assignment in course_assignments:
            courses_info.append({
                'course_id': assignment.course.id,
                'course_name': assignment.course.name,
                'year': assignment.year_of_study,
                'semester': assignment.semester
            })
        
        return JsonResponse({
            'id': unit.id,
            'code': unit.code,
            'name': unit.name,
            'semester': unit.semester,
            'lecturer_id': unit.assigned_lecturer.id if unit.assigned_lecturer else None,
            'lecturer_name': f"{unit.assigned_lecturer.first_name} {unit.assigned_lecturer.last_name}".strip() if unit.assigned_lecturer else None,
            'global_unit_id': unit.global_unit.id if unit.global_unit else None,
            'global_unit_code': unit.global_unit.code if unit.global_unit else None,
            'global_unit_name': unit.global_unit.name if unit.global_unit else None,
            'course_assignments': courses_info,
            'status': 'active'
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        unit.name = data.get('name', unit.name)
        unit.code = data.get('code', unit.code)
        unit.semester = data.get('semester', unit.semester)
        unit.save()
        return JsonResponse({
            'id': unit.id,
            'code': unit.code,
            'name': unit.name,
            'department_id': data.get('department', 1),
            'course_id': data.get('course'),
            'year': data.get('year', 1),
            'semester': unit.semester,
            'status': data.get('status', 'active')
        })
    
    elif request.method == 'DELETE':
        unit.delete()
        return JsonResponse({'success': True}, status=204)


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_lecturer_units(request, college_slug):
    """API endpoint for lecturer's assigned units - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Allow users who have units assigned to them, or lecturers/principals/registrars
    # This allows everyone to view their own assigned units
    has_assigned_units = CollegeUnit.objects.filter(
        college=college,
        assigned_lecturer=request.user
    ).exists()
    
    can_access_all = request.user.is_principal() or request.user.is_registrar() or request.user.is_director()
    
    if not (has_assigned_units or can_access_all):
        return JsonResponse({'error': 'Access denied. You must have units assigned to you.'}, status=403)
    
    # Get units assigned to the logged-in user (or all units if principal/registrar)
    if can_access_all:
        # Principals and registrars can see all units (for future registrar section)
        units = CollegeUnit.objects.filter(
            college=college
        ).select_related('assigned_lecturer', 'global_unit').order_by('code')
    else:
        # Regular users see only their assigned units
        units = CollegeUnit.objects.filter(
            college=college,
            assigned_lecturer=request.user
        ).select_related('assigned_lecturer', 'global_unit').order_by('code')
    
    units_list = []
    for unit in units:
        # Get all course assignments for this unit
        course_assignments = CollegeCourseUnit.objects.filter(
            unit=unit,
            college=college
        ).select_related('course').values('course_id', 'course__name', 'year_of_study', 'semester')
        
        courses_info = []
        for assignment in course_assignments:
            courses_info.append({
                'course_id': assignment['course_id'],
                'course_name': assignment['course__name'],
                'year': assignment['year_of_study'],
                'semester': assignment['semester']
            })
        
        units_list.append({
            'id': unit.id,
            'code': unit.code,
            'name': unit.name,
            'semester': unit.semester,
            'lecturer_id': unit.assigned_lecturer.id if unit.assigned_lecturer else None,
            'lecturer_name': f"{unit.assigned_lecturer.first_name} {unit.assigned_lecturer.last_name}".strip() if unit.assigned_lecturer else None,
            'global_unit_id': unit.global_unit.id if unit.global_unit else None,
            'global_unit_code': unit.global_unit.code if unit.global_unit else None,
            'global_unit_name': unit.global_unit.name if unit.global_unit else None,
            'course_assignments': courses_info,
            'status': 'active'
        })
    
    return JsonResponse({
        'count': len(units_list),
        'results': units_list
    })


@login_required
@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_students_list(request, college_slug):
    """API endpoint for students list, create, update, delete - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        search = request.GET.get('search', '')
        department = request.GET.get('department', '')
        status_filter = request.GET.get('status', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 10)), 50)  # Max 50
        
        students = Student.objects.filter(college=college).select_related('course')
        if search:
            students = students.filter(
                full_name__icontains=search
            ) | students.filter(
                admission_number__icontains=search
            ) | students.filter(
                email__icontains=search
            )
        
        # Filter by status if provided
        if status_filter:
            students = students.filter(status=status_filter)
        
        # Optimize: Paginate queryset first, then build list (more efficient)
        paginator = Paginator(students, page_size)
        page_obj = paginator.get_page(page)
        
        students_list = []
        for student in page_obj:
            students_list.append({
                'id': student.id,
                'admission_number': student.admission_number,
                'full_name': student.full_name,
                'name': student.full_name,
                'email': student.email or '',
                'phone': student.phone or '',
                'gender': student.gender,
                'year': student.year_of_study,
                'date_of_birth': student.date_of_birth.strftime('%Y-%m-%d') if student.date_of_birth else None,
                'current_semester': student.current_semester,
                'department_id': 1,
                'department_name': 'General',
                'course_id': student.course.id if student.course else None,
                'course_name': student.course.name if student.course else None,
                'status': student.status,
                'graduation_date': student.graduation_date.strftime('%Y-%m-%d') if student.graduation_date else None,
                'has_ream_paper': student.has_ream_paper,
                'is_sponsored': student.is_sponsored,
                'sponsorship_discount_type': student.sponsorship_discount_type,
                'sponsorship_discount_value': float(student.sponsorship_discount_value) if student.sponsorship_discount_value else None
            })
        
        return JsonResponse({
            'count': paginator.count,
            'results': students_list,
            'next': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'page': page_obj.number,
            'total_pages': paginator.num_pages
        })
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Validate required fields
        # Note: Frontend sends 'year' but we need 'year_of_study' - accept both
        required_fields = ['admission_number', 'full_name', 'gender', 'date_of_birth']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({'error': f'{field} is required'}, status=400)
        
        # Get year_of_study from either 'year' or 'year_of_study' field
        year_of_study = data.get('year_of_study') or data.get('year')
        if not year_of_study:
            return JsonResponse({'error': 'year_of_study is required'}, status=400)
        
        # Get course if provided
        course = None
        if data.get('course'):
            try:
                course = CollegeCourse.objects.get(pk=data['course'], college=college)
            except CollegeCourse.DoesNotExist:
                return JsonResponse({'error': 'Course not found'}, status=404)
        
        # Validate year_of_study against course duration
        try:
            year_of_study = int(year_of_study)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'year_of_study must be a valid number'}, status=400)
        if year_of_study < 1 or year_of_study > 5:
            return JsonResponse({'error': 'Year of study must be between 1 and 5'}, status=400)
        
        if course and year_of_study > course.duration_years:
            return JsonResponse({
                'error': f'Year of study ({year_of_study}) cannot exceed course duration ({course.duration_years} years)'
            }, status=400)
        
        # Validate current_semester against college semesters_per_year
        current_semester = data.get('current_semester')
        if current_semester is not None:
            try:
                current_semester = int(current_semester)
                if current_semester < 1 or current_semester > college.semesters_per_year:
                    return JsonResponse({
                        'error': f'Semester ({current_semester}) must be between 1 and {college.semesters_per_year}'
                    }, status=400)
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid current_semester value'}, status=400)
        else:
            current_semester = None
        
        # Parse date_of_birth
        try:
            from datetime import datetime
            date_of_birth = datetime.strptime(data.get('date_of_birth'), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid date_of_birth format. Use YYYY-MM-DD'}, status=400)
        
        # Validate sponsorship fields if is_sponsored is True
        is_sponsored = data.get('is_sponsored', False)
        sponsorship_discount_type = data.get('sponsorship_discount_type')
        sponsorship_discount_value = data.get('sponsorship_discount_value')
        
        if is_sponsored:
            if not sponsorship_discount_type:
                return JsonResponse({'error': 'Discount type is required when student is sponsored'}, status=400)
            if not sponsorship_discount_value:
                return JsonResponse({'error': 'Discount value is required when student is sponsored'}, status=400)
            try:
                discount_value = float(sponsorship_discount_value)
                if sponsorship_discount_type == 'percentage' and (discount_value < 0 or discount_value > 100):
                    return JsonResponse({'error': 'Percentage discount must be between 0 and 100'}, status=400)
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid discount value'}, status=400)
        
        # Create student
        student = Student.objects.create(
            college=college,
            admission_number=data.get('admission_number', ''),
            full_name=data.get('full_name', ''),
            email=data.get('email', ''),
            phone=data.get('phone', ''),
            gender=data.get('gender', 'M'),
            year_of_study=year_of_study,
            date_of_birth=date_of_birth,
            current_semester=current_semester,
            status=data.get('status', 'active'),
            course_id=data.get('course') if data.get('course') else None,
            has_ream_paper=data.get('has_ream_paper', False),
            is_sponsored=is_sponsored,
            sponsorship_discount_type=sponsorship_discount_type if is_sponsored else None,
            sponsorship_discount_value=sponsorship_discount_value if is_sponsored else None
        )
        
        return JsonResponse({
            'id': student.id,
            'admission_number': student.admission_number,
            'full_name': student.full_name,
            'email': student.email or '',
            'phone': student.phone or '',
            'gender': student.gender,
            'year': student.year_of_study,
            'date_of_birth': student.date_of_birth.strftime('%Y-%m-%d'),
            'current_semester': student.current_semester,
            'course_id': student.course.id if student.course else None,
            'status': student.status,
            'graduation_date': student.graduation_date.strftime('%Y-%m-%d') if student.graduation_date else None,
            'has_ream_paper': student.has_ream_paper,
            'is_sponsored': student.is_sponsored,
            'sponsorship_discount_type': student.sponsorship_discount_type,
            'sponsorship_discount_value': float(student.sponsorship_discount_value) if student.sponsorship_discount_value else None
        }, status=201)
    
    elif request.method in ['PUT', 'PATCH']:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        student_id = data.get('id')
        if not student_id:
            return JsonResponse({'error': 'Student ID is required'}, status=400)
        
        try:
            student = Student.objects.get(pk=student_id, college=college)
        except Student.DoesNotExist:
            return JsonResponse({'error': 'Student not found'}, status=404)
        
        # Get course if provided
        course = None
        if data.get('course'):
            try:
                course = CollegeCourse.objects.get(pk=data['course'], college=college)
            except CollegeCourse.DoesNotExist:
                return JsonResponse({'error': 'Course not found'}, status=404)
        else:
            course = student.course
        
        # Validate year_of_study if provided
        if 'year' in data:
            year_of_study = int(data.get('year'))
            if year_of_study < 1 or year_of_study > 5:
                return JsonResponse({'error': 'Year of study must be between 1 and 5'}, status=400)
            
            if course and year_of_study > course.duration_years:
                return JsonResponse({
                    'error': f'Year of study ({year_of_study}) cannot exceed course duration ({course.duration_years} years)'
                }, status=400)
            student.year_of_study = year_of_study
        
        # Validate current_semester if provided
        if 'current_semester' in data:
            current_semester = data.get('current_semester')
            if current_semester is not None:
                try:
                    current_semester = int(current_semester)
                    if current_semester < 1 or current_semester > college.semesters_per_year:
                        return JsonResponse({
                            'error': f'Semester ({current_semester}) must be between 1 and {college.semesters_per_year}'
                        }, status=400)
                    student.current_semester = current_semester
                except (ValueError, TypeError):
                    return JsonResponse({'error': 'Invalid current_semester value'}, status=400)
            else:
                student.current_semester = None
        
        # Update date_of_birth if provided
        if 'date_of_birth' in data:
            try:
                from datetime import datetime
                student.date_of_birth = datetime.strptime(data.get('date_of_birth'), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid date_of_birth format. Use YYYY-MM-DD'}, status=400)
        
        # Update other fields
        student.full_name = data.get('full_name', student.full_name)
        student.admission_number = data.get('admission_number', student.admission_number)
        student.email = data.get('email', student.email)
        student.phone = data.get('phone', student.phone)
        student.gender = data.get('gender', student.gender)
        if 'status' in data:
            student.status = data.get('status', student.status)
        if data.get('course'):
            student.course_id = data.get('course')
        elif 'course' in data and data.get('course') is None:
            student.course_id = None
        
        # Update ream paper and sponsorship fields
        if 'has_ream_paper' in data:
            student.has_ream_paper = data.get('has_ream_paper', False)
        if 'is_sponsored' in data:
            is_sponsored = data.get('is_sponsored', False)
            student.is_sponsored = is_sponsored
            if is_sponsored:
                sponsorship_discount_type = data.get('sponsorship_discount_type')
                sponsorship_discount_value = data.get('sponsorship_discount_value')
                if not sponsorship_discount_type:
                    return JsonResponse({'error': 'Discount type is required when student is sponsored'}, status=400)
                if not sponsorship_discount_value:
                    return JsonResponse({'error': 'Discount value is required when student is sponsored'}, status=400)
                try:
                    discount_value = float(sponsorship_discount_value)
                    if sponsorship_discount_type == 'percentage' and (discount_value < 0 or discount_value > 100):
                        return JsonResponse({'error': 'Percentage discount must be between 0 and 100'}, status=400)
                    student.sponsorship_discount_type = sponsorship_discount_type
                    student.sponsorship_discount_value = discount_value
                except (ValueError, TypeError):
                    return JsonResponse({'error': 'Invalid discount value'}, status=400)
            else:
                student.sponsorship_discount_type = None
                student.sponsorship_discount_value = None
        
        student.save()
        
        return JsonResponse({
            'id': student.id,
            'admission_number': student.admission_number,
            'full_name': student.full_name,
            'email': student.email or '',
            'phone': student.phone or '',
            'gender': student.gender,
            'year': student.year_of_study,
            'date_of_birth': student.date_of_birth.strftime('%Y-%m-%d'),
            'current_semester': student.current_semester,
            'course_id': student.course.id if student.course else None,
            'status': student.status,
            'graduation_date': student.graduation_date.strftime('%Y-%m-%d') if student.graduation_date else None,
            'has_ream_paper': student.has_ream_paper,
            'is_sponsored': student.is_sponsored,
            'sponsorship_discount_type': student.sponsorship_discount_type,
            'sponsorship_discount_value': float(student.sponsorship_discount_value) if student.sponsorship_discount_value else None
        })
    
    elif request.method == 'DELETE':
        data = json.loads(request.body) if request.body else {}
        student_id = data.get('id')
        if not student_id:
            return JsonResponse({'error': 'Student ID is required'}, status=400)
        
        try:
            student = Student.objects.get(pk=student_id, college=college)
            student.delete()
            return JsonResponse({'success': True}, status=204)
        except Student.DoesNotExist:
            return JsonResponse({'error': 'Student not found'}, status=404)


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def api_student_detail(request, college_slug, pk):
    """API endpoint for student detail, update, delete - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    try:
        student = Student.objects.get(pk=pk, college=college)
    except Student.DoesNotExist:
        return JsonResponse({'error': 'Student not found'}, status=404)
    
    if request.method == 'GET':
        return JsonResponse({
            'id': student.id,
            'admission_number': student.admission_number,
            'full_name': student.full_name,
            'name': student.full_name,
            'email': student.email or '',
            'phone': student.phone or '',
            'gender': student.gender,
            'year': student.year_of_study,
            'department_id': 1,
            'course_id': student.course.id if student.course else None,
            'status': student.status,
            'graduation_date': student.graduation_date.strftime('%Y-%m-%d') if student.graduation_date else None
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        student.full_name = data.get('full_name', student.full_name)
        student.admission_number = data.get('admission_number', student.admission_number)
        student.email = data.get('email', student.email)
        student.phone = data.get('phone', student.phone)
        student.gender = data.get('gender', student.gender)
        student.year_of_study = data.get('year', student.year_of_study)
        if data.get('course'):
            student.course_id = data.get('course')
        student.save()
        return JsonResponse({
            'id': student.id,
            'admission_number': student.admission_number,
            'full_name': student.full_name,
            'email': student.email or '',
            'phone': student.phone or '',
            'gender': student.gender,
            'year': student.year_of_study,
            'course_id': student.course.id if student.course else None,
            'status': student.status,
            'graduation_date': student.graduation_date.strftime('%Y-%m-%d') if student.graduation_date else None
        })
    
    elif request.method == 'DELETE':
        student.delete()
        return JsonResponse({'success': True}, status=204)


@login_required
@csrf_exempt
@require_http_methods(["PUT"])
def api_student_status_update(request, college_slug, pk):
    """API endpoint to update student status (suspend, activate, graduate, defer)"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    try:
        student = Student.objects.get(pk=pk, college=college)
    except Student.DoesNotExist:
        return JsonResponse({'error': 'Student not found'}, status=404)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    new_status = data.get('status', '').lower()
    
    # Validate status
    valid_statuses = ['active', 'suspended', 'graduated', 'deferred']
    if new_status not in valid_statuses:
        return JsonResponse({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}, status=400)
    
    # Handle graduation
    if new_status == 'graduated':
        from django.utils import timezone
        student.status = 'graduated'
        if not student.graduation_date:
            student.graduation_date = timezone.now().date()
        student.save()
    else:
        student.status = new_status
        # Clear graduation date if not graduated
        if new_status != 'graduated':
            student.graduation_date = None
        student.save()
    
    return JsonResponse({
        'id': student.id,
        'admission_number': student.admission_number,
        'full_name': student.full_name,
        'status': student.status,
        'graduation_date': student.graduation_date.strftime('%Y-%m-%d') if student.graduation_date else None,
        'message': f'Student status updated to {new_status}'
    })


@login_required
@csrf_exempt
@require_http_methods(["PUT"])
def api_lecturer_status_update(request, college_slug, pk):
    """API endpoint to suspend/activate lecturers"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    try:
        lecturer = CustomUser.objects.get(pk=pk, college=college)
    except CustomUser.DoesNotExist:
        return JsonResponse({'error': 'Lecturer not found'}, status=404)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    action = data.get('action', '').lower()
    
    if action == 'suspend':
        lecturer.is_active = False
        lecturer.save()
        message = 'Lecturer suspended'
    elif action == 'activate':
        lecturer.is_active = True
        lecturer.save()
        message = 'Lecturer activated'
    else:
        return JsonResponse({'error': 'Invalid action. Must be "suspend" or "activate"'}, status=400)
    
    return JsonResponse({
        'id': lecturer.id,
        'username': lecturer.username,
        'full_name': lecturer.get_full_name(),
        'is_active': lecturer.is_active,
        'message': message
    })


@login_required
@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_lecturers_list(request, college_slug):
    """API endpoint for lecturers list, create, update, delete - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        search = request.GET.get('search', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 10)), 50)  # Max 50
        
        # Get both lecturers and college admins (exclude super admins and director)
        # Director should not be visible to other users
        # This allows User Management to see all users except director
        from django.db.models import Q, Count
        users = CustomUser.objects.filter(
            college=college
        ).exclude(role='super_admin').exclude(role='director').annotate(
            assigned_units_count=Count('assigned_units', filter=Q(assigned_units__college=college))
        )
        
        if search:
            users = users.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        
        # Optimize: Paginate queryset first, then build list (more efficient)
        paginator = Paginator(users, page_size)
        page_obj = paginator.get_page(page)
        
        users_list = []
        for user in page_obj:
            users_list.append({
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
                'email': user.email or '',
                'phone': user.phone or '',
                'role': user.role,
                'role_display': user.get_role_display(),
                'assigned_units_count': user.assigned_units_count,
                'status': 'active' if user.is_active else 'inactive'
            })
        
        return JsonResponse({
            'count': paginator.count,
            'results': users_list,
            'next': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'page': page_obj.number,
            'total_pages': paginator.num_pages
        })
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Check if username already exists
        if CustomUser.objects.filter(username=data.get('username', '')).exists():
            return JsonResponse({'error': 'Username already exists'}, status=400)
        
        # Check if email already exists
        if data.get('email') and CustomUser.objects.filter(email=data.get('email')).exists():
            return JsonResponse({'error': 'Email already exists'}, status=400)
        
        # Determine role - only college admins can set role
        role = 'lecturer'  # Default
        if data.get('role'):
            # Only allow role setting if user is college admin
            if request.user.is_college_admin():
                valid_roles = ['lecturer', 'college_admin', 'principal', 'registrar', 'accounts_officer', 'reception']
                if data.get('role') in valid_roles:
                    role = data.get('role')
                else:
                    return JsonResponse({'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'}, status=400)
            else:
                # Non-admins can only create lecturers
                role = 'lecturer'
        
        lecturer = CustomUser.objects.create_user(
            username=data.get('username', ''),
            email=data.get('email', ''),
            password=data.get('password', ''),
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            phone=data.get('phone', ''),
            role=role,
            college=college,
            is_active=True
        )
        
        assigned_units_count = CollegeUnit.objects.filter(college=college, assigned_lecturer=lecturer).count()
        
        return JsonResponse({
            'id': lecturer.id,
            'username': lecturer.username,
            'first_name': lecturer.first_name,
            'last_name': lecturer.last_name,
            'full_name': f"{lecturer.first_name} {lecturer.last_name}".strip() or lecturer.username,
            'email': lecturer.email or '',
            'phone': lecturer.phone or '',
            'role': lecturer.role,
            'assigned_units_count': assigned_units_count,
            'status': 'active'
        }, status=201)
    
    elif request.method in ['PUT', 'PATCH']:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        lecturer_id = data.get('id')
        if not lecturer_id:
            return JsonResponse({'error': 'Lecturer ID is required'}, status=400)
        
        try:
            # Allow updating both lecturers and college admins (don't filter by role)
            # Only exclude super_admin and director
            lecturer = CustomUser.objects.get(
                pk=lecturer_id, 
                college=college
            )
            # Prevent updating super_admin
            if lecturer.is_super_admin():
                return JsonResponse({'error': 'Cannot update super admin'}, status=403)
            # Prevent updating director
            if lecturer.is_director():
                return JsonResponse({'error': 'Cannot update director'}, status=403)
        except CustomUser.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
        
        # Update fields (username is typically not changed, but allow it if provided)
        if data.get('username') and data.get('username') != lecturer.username:
            # Check if new username already exists
            if CustomUser.objects.filter(username=data.get('username')).exclude(pk=lecturer_id).exists():
                return JsonResponse({'error': 'Username already exists'}, status=400)
            lecturer.username = data.get('username')
        lecturer.first_name = data.get('first_name', lecturer.first_name)
        lecturer.last_name = data.get('last_name', lecturer.last_name)
        lecturer.email = data.get('email', lecturer.email)
        lecturer.phone = data.get('phone', lecturer.phone)
        if data.get('password'):
            lecturer.set_password(data.get('password'))
        lecturer.save()
        
        assigned_units_count = CollegeUnit.objects.filter(college=college, assigned_lecturer=lecturer).count()
        
        return JsonResponse({
            'id': lecturer.id,
            'username': lecturer.username,
            'first_name': lecturer.first_name,
            'last_name': lecturer.last_name,
            'full_name': f"{lecturer.first_name} {lecturer.last_name}".strip() or lecturer.username,
            'email': lecturer.email or '',
            'phone': lecturer.phone or '',
            'role': lecturer.role,
            'assigned_units_count': assigned_units_count,
            'status': 'active' if lecturer.is_active else 'inactive'
        })
    
    elif request.method == 'DELETE':
        data = json.loads(request.body) if request.body else {}
        lecturer_id = data.get('id')
        if not lecturer_id:
            return JsonResponse({'error': 'User ID is required'}, status=400)
        
        try:
            # Allow deleting both lecturers and college admins (don't filter by role)
            # Only exclude super_admin and director
            lecturer = CustomUser.objects.get(pk=lecturer_id, college=college)
            # Prevent deleting super_admin
            if lecturer.is_super_admin():
                return JsonResponse({'error': 'Cannot delete super admin'}, status=403)
            # Prevent deleting director
            if lecturer.is_director():
                return JsonResponse({'error': 'Cannot delete director'}, status=403)
            lecturer.delete()
            return JsonResponse({'success': True}, status=204)
        except CustomUser.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def api_lecturer_detail(request, college_slug, pk):
    """API endpoint for lecturer detail, update, delete - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    try:
        # Allow accessing both lecturers and college admins (don't filter by role)
        # Only exclude super_admin and director
        lecturer = CustomUser.objects.get(pk=pk, college=college)
        # Prevent accessing super_admin
        if lecturer.is_super_admin():
            return JsonResponse({'error': 'Cannot access super admin'}, status=403)
        # Prevent accessing director
        if lecturer.is_director():
            return JsonResponse({'error': 'Cannot access director'}, status=403)
    except CustomUser.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    
    if request.method == 'GET':
        assigned_units_count = CollegeUnit.objects.filter(college=college, assigned_lecturer=lecturer).count()
        return JsonResponse({
            'id': lecturer.id,
            'username': lecturer.username,
            'first_name': lecturer.first_name,
            'last_name': lecturer.last_name,
            'full_name': f"{lecturer.first_name} {lecturer.last_name}".strip() or lecturer.username,
            'email': lecturer.email or '',
            'phone': lecturer.phone or '',
            'role': lecturer.role,
            'assigned_units_count': assigned_units_count,
            'status': 'active' if lecturer.is_active else 'inactive'
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        # Update fields (username is typically not changed, but allow it if provided)
        if data.get('username') and data.get('username') != lecturer.username:
            # Check if new username already exists
            if CustomUser.objects.filter(username=data.get('username')).exclude(pk=pk).exists():
                return JsonResponse({'error': 'Username already exists'}, status=400)
            lecturer.username = data.get('username')
        lecturer.first_name = data.get('first_name', lecturer.first_name)
        lecturer.last_name = data.get('last_name', lecturer.last_name)
        lecturer.email = data.get('email', lecturer.email)
        lecturer.phone = data.get('phone', lecturer.phone)
        if data.get('password'):
            lecturer.set_password(data.get('password'))
        lecturer.save()
        
        assigned_units_count = CollegeUnit.objects.filter(college=college, assigned_lecturer=lecturer).count()
        return JsonResponse({
            'id': lecturer.id,
            'username': lecturer.username,
            'first_name': lecturer.first_name,
            'last_name': lecturer.last_name,
            'full_name': f"{lecturer.first_name} {lecturer.last_name}".strip() or lecturer.username,
            'email': lecturer.email or '',
            'phone': lecturer.phone or '',
            'assigned_units_count': assigned_units_count,
            'status': 'active' if lecturer.is_active else 'inactive'
        })
    
    elif request.method == 'DELETE':
        # Prevent deleting director
        if lecturer.is_director():
            return JsonResponse({'error': 'Cannot delete director'}, status=403)
        lecturer.delete()
        return JsonResponse({'success': True}, status=204)


@login_required
@csrf_exempt
@require_http_methods(["PUT"])
def api_lecturer_role_update(request, college_slug, pk):
    """
    API endpoint to update lecturer role (promote/demote).
    Only college admins can change roles.
    """
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    # Only college admins can change roles
    if not request.user.is_college_admin():
        raise PermissionDenied("Only college administrators can change user roles.")
    
    try:
        user = CustomUser.objects.get(pk=pk, college=college)
    except CustomUser.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    
    # Prevent changing own role
    if user.id == request.user.id:
        return JsonResponse({'error': 'You cannot change your own role'}, status=400)
    
    # Prevent changing super admin role
    if user.is_super_admin():
        return JsonResponse({'error': 'Cannot change super admin role'}, status=400)
    
    # Prevent changing director role (college admin/director)
    if user.is_director():
        return JsonResponse({'error': 'Cannot change director role'}, status=400)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    new_role = data.get('role')
    
    # Prevent setting director role (director role cannot be assigned or changed)
    if new_role == 'director':
        return JsonResponse({'error': 'Cannot assign director role'}, status=400)
    
    # Validate role
    valid_roles = ['college_admin', 'lecturer', 'principal', 'registrar', 'accounts_officer', 'reception']
    if new_role not in valid_roles:
        return JsonResponse({'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'}, status=400)
    
    # Update role
    user.role = new_role
    user.save()
    
    assigned_units_count = CollegeUnit.objects.filter(college=college, assigned_lecturer=user).count()
    
    return JsonResponse({
        'success': True,
        'message': f'User role updated to {user.get_role_display()}',
        'user': {
            'id': user.id,
            'username': user.username,
            'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
            'role': user.role,
            'role_display': user.get_role_display(),
            'assigned_units_count': assigned_units_count,
            'status': 'active' if user.is_active else 'inactive'
        }
    })


@login_required
@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_enrollments_list(request, college_slug):
    """API endpoint for enrollments list and create - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        search = request.GET.get('search', '')
        unit_filter = request.GET.get('unit', '')
        course_filter = request.GET.get('course', '')
        year_filter = request.GET.get('academic_year', '')
        semester_filter = request.GET.get('semester', '')
        exam_status_filter = request.GET.get('exam_registered', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 10)), 50)
        
        enrollments = Enrollment.objects.filter(unit__college=college).select_related(
            'student', 'student__course', 'unit', 'unit__assigned_lecturer'
        ).prefetch_related('unit__course_assignments__course')
        
        if search:
            enrollments = enrollments.filter(
                student__full_name__icontains=search
            ) | enrollments.filter(
                student__admission_number__icontains=search
            ) | enrollments.filter(
                unit__name__icontains=search
            ) | enrollments.filter(
                unit__code__icontains=search
            )
        
        if unit_filter:
            enrollments = enrollments.filter(unit_id=unit_filter)
        if course_filter:
            # Filter by course through course-unit assignments
            enrollments = enrollments.filter(unit__course_assignments__course_id=course_filter).distinct()
        if year_filter:
            enrollments = enrollments.filter(academic_year=year_filter)
        if semester_filter:
            enrollments = enrollments.filter(semester=semester_filter)
        if exam_status_filter:
            if exam_status_filter.lower() == 'true' or exam_status_filter == 'registered':
                enrollments = enrollments.filter(exam_registered=True)
            elif exam_status_filter.lower() == 'false' or exam_status_filter == 'not_registered':
                enrollments = enrollments.filter(exam_registered=False)
        
        # Optimize: Order and paginate queryset first, then build list (more efficient)
        enrollments = enrollments.order_by('-enrolled_at', '-academic_year', '-semester')
        
        # Paginate the queryset first (more efficient than building entire list)
        paginator = Paginator(enrollments, page_size)
        page_obj = paginator.get_page(page)
        
        # Get all unit IDs from the page
        unit_ids = [enrollment.unit.id for enrollment in page_obj]
        
        # Get course assignments for these units in one query
        course_assignments_map = {}
        if unit_ids:
            assignments = CollegeCourseUnit.objects.filter(
                unit_id__in=unit_ids,
                college=college
            ).select_related('course', 'unit').values('unit_id', 'course__name', 'course_id')
            
            for assignment in assignments:
                unit_id = assignment['unit_id']
                if unit_id not in course_assignments_map:
                    course_assignments_map[unit_id] = assignment['course__name']
        
        # Build list only for the current page
        enrollments_list = []
        for enrollment in page_obj:
            # Get course name from the map
            course_name = course_assignments_map.get(enrollment.unit.id, None)
            
            enrollments_list.append({
                'id': enrollment.id,
                'student_id': enrollment.student.id,
                'student_name': enrollment.student.full_name,
                'student_admission': enrollment.student.admission_number,
                'unit_id': enrollment.unit.id,
                'unit_code': enrollment.unit.code,
                'unit_name': enrollment.unit.name,
                'course_name': course_name,
                'academic_year': enrollment.academic_year,
                'semester': enrollment.semester,
                'enrolled_at': enrollment.enrolled_at.strftime('%Y-%m-%d') if enrollment.enrolled_at else None,
                'exam_registered': enrollment.exam_registered,
                'exam_registered_at': enrollment.exam_registered_at.strftime('%Y-%m-%d %H:%M') if enrollment.exam_registered_at else None
            })
        
        return JsonResponse({
            'count': paginator.count,
            'results': enrollments_list,
            'next': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'page': page_obj.number,
            'total_pages': paginator.num_pages
        })
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        try:
            student = Student.objects.get(pk=data.get('student'), college=college)
            unit = CollegeUnit.objects.get(pk=data.get('unit'), college=college)
        except (Student.DoesNotExist, CollegeUnit.DoesNotExist):
            return JsonResponse({'error': 'Student or Unit not found'}, status=404)
        
        # Check if enrollment already exists
        if Enrollment.objects.filter(student=student, unit=unit, academic_year=data.get('academic_year')).exists():
            return JsonResponse({'error': 'Student is already enrolled in this unit for this academic year'}, status=400)
        
        # Default to college's current_academic_year if not provided
        academic_year = data.get('academic_year') or college.current_academic_year
        if not academic_year:
            # Fallback: calculate from current date
            from django.utils import timezone
            current_year = timezone.now().year
            academic_year = f"{current_year}/{current_year + 1}"
        
        enrollment = Enrollment.objects.create(
            student=student,
            unit=unit,
            academic_year=academic_year,
            semester=data.get('semester', 1)
        )
        
        return JsonResponse({
            'id': enrollment.id,
            'student_id': enrollment.student.id,
            'student_name': enrollment.student.full_name,
            'student_admission': enrollment.student.admission_number,
            'unit_id': enrollment.unit.id,
            'unit_code': enrollment.unit.code,
            'unit_name': enrollment.unit.name,
            'academic_year': enrollment.academic_year,
            'semester': enrollment.semester,
            'enrolled_at': enrollment.enrolled_at.strftime('%Y-%m-%d') if enrollment.enrolled_at else None
        }, status=201)


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
def api_enrollment_detail(request, college_slug, pk):
    """API endpoint for enrollment detail, update, delete - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    try:
        enrollment = Enrollment.objects.get(pk=pk, unit__college=college)
    except Enrollment.DoesNotExist:
        return JsonResponse({'error': 'Enrollment not found'}, status=404)
    
    if request.method == 'GET':
        # Get course name from course assignments
        course_assignments = CollegeCourseUnit.objects.filter(
            unit=enrollment.unit,
            college=college
        ).select_related('course').first()
        course_name = course_assignments.course.name if course_assignments else None
        
        return JsonResponse({
            'id': enrollment.id,
            'student_id': enrollment.student.id,
            'student_name': enrollment.student.full_name,
            'student_admission': enrollment.student.admission_number,
            'unit_id': enrollment.unit.id,
            'unit_code': enrollment.unit.code,
            'unit_name': enrollment.unit.name,
            'course_name': course_name,
            'academic_year': enrollment.academic_year,
            'semester': enrollment.semester,
            'enrolled_at': enrollment.enrolled_at.strftime('%Y-%m-%d') if enrollment.enrolled_at else None,
            'exam_registered': enrollment.exam_registered,
            'exam_registered_at': enrollment.exam_registered_at.strftime('%Y-%m-%d %H:%M') if enrollment.exam_registered_at else None
        })
    
    elif request.method in ['PUT', 'PATCH']:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        if data.get('unit'):
            try:
                unit = CollegeUnit.objects.get(pk=data.get('unit'), college=college)
                enrollment.unit = unit
            except CollegeUnit.DoesNotExist:
                return JsonResponse({'error': 'Unit not found'}, status=404)
        
        enrollment.academic_year = data.get('academic_year', enrollment.academic_year)
        enrollment.semester = data.get('semester', enrollment.semester)
        enrollment.save()
        
        # Get course name for response
        course_assignments = CollegeCourseUnit.objects.filter(
            unit=enrollment.unit,
            college=college
        ).select_related('course').first()
        course_name = course_assignments.course.name if course_assignments else None
        
        return JsonResponse({
            'id': enrollment.id,
            'student_id': enrollment.student.id,
            'student_name': enrollment.student.full_name,
            'student_admission': enrollment.student.admission_number,
            'unit_id': enrollment.unit.id,
            'unit_code': enrollment.unit.code,
            'unit_name': enrollment.unit.name,
            'course_name': course_name,
            'academic_year': enrollment.academic_year,
            'semester': enrollment.semester,
            'enrolled_at': enrollment.enrolled_at.strftime('%Y-%m-%d') if enrollment.enrolled_at else None,
            'exam_registered': enrollment.exam_registered,
            'exam_registered_at': enrollment.exam_registered_at.strftime('%Y-%m-%d %H:%M') if enrollment.exam_registered_at else None
        })
    
    elif request.method == 'DELETE':
        enrollment.delete()
        return JsonResponse({'success': True}, status=204)


@login_required
@csrf_exempt
def api_enrollments_academic_years(request, college_slug):
    """Get distinct academic years from enrollments"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Get distinct academic years from enrollments, ordered by most recent first
    years = Enrollment.objects.filter(
        unit__college=college
    ).values_list('academic_year', flat=True).distinct().order_by('-academic_year')
    
    years_list = list(years)
    
    # If no years exist, include current_academic_year as fallback
    if not years_list and college.current_academic_year:
        years_list = [college.current_academic_year]
    
    return JsonResponse({'academic_years': years_list})


@login_required
@csrf_exempt
def api_results_academic_years(request, college_slug):
    """Get distinct academic years from enrollments that have exam_registered=True (for results)"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Get distinct academic years from enrollments that have exam_registered=True
    years = Enrollment.objects.filter(
        unit__college=college,
        exam_registered=True
    ).values_list('academic_year', flat=True).distinct().order_by('-academic_year')
    
    years_list = list(years)
    
    # If no years exist, include current_academic_year as fallback
    if not years_list and college.current_academic_year:
        years_list = [college.current_academic_year]
    
    return JsonResponse({'academic_years': years_list})


@login_required
@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "PATCH"])
def api_results_list(request, college_slug):
    """API endpoint for results list, create, update - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        search = request.GET.get('search', '')
        unit_filter = request.GET.get('unit', '')
        semester_filter = request.GET.get('semester', '')
        academic_year_filter = request.GET.get('academic_year', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 10)), 50)
        show_submitted = request.GET.get('show_submitted', 'false').lower() == 'true'
        
        # Use provided academic_year or default to college's current_academic_year
        academic_year = academic_year_filter if academic_year_filter else college.current_academic_year
        if not academic_year:
            # Fallback: calculate from current date
            from django.utils import timezone
            current_year = timezone.now().year
            academic_year = f"{current_year}/{current_year + 1}"
        
        # Start with enrollments filtered by exam_registered=True and academic year
        enrollments = Enrollment.objects.filter(
            unit__college=college,
            exam_registered=True,
            academic_year=academic_year
        ).select_related('student', 'student__course', 'unit', 'unit__assigned_lecturer')
        
        # Filter by semester if provided
        if semester_filter:
            try:
                semester = int(semester_filter)
                enrollments = enrollments.filter(semester=semester)
            except ValueError:
                pass  # Invalid semester, ignore filter
        else:
            # If no semester filter, show all enrollments for the academic year
            # (Don't filter by max semester - show all enrolled students)
            # This ensures all students enrolled in any semester are displayed
            pass
        
        # Lecturers: filter by assigned units only
        if request.user.is_lecturer():
            enrollments = enrollments.filter(unit__assigned_lecturer=request.user)
        
        # Registrar and Principal: only see submitted results (exclude drafts)
        # Lecturers: only see draft results for their assigned units
        # (This filtering happens later when processing results)
        
        if search:
            enrollments = enrollments.filter(
                student__full_name__icontains=search
            ) | enrollments.filter(
                student__admission_number__icontains=search
            ) | enrollments.filter(
                unit__code__icontains=search
            )
        
        if unit_filter:
            enrollments = enrollments.filter(unit_id=unit_filter)
        
        # Optimize: Prefetch results to avoid N+1 queries
        from django.db.models import Prefetch
        enrollments = enrollments.prefetch_related(
            Prefetch('result', queryset=Result.objects.select_related('entered_by'))
        )
        
        results_list = []
        for enrollment in enrollments:
            # Get result if it exists (using prefetch to avoid extra queries)
            try:
                result = enrollment.result
            except Result.DoesNotExist:
                result = None
            
            # Visibility rules:
            # - Lecturers: Only see draft results for their assigned units
            # - Registrar/Principal: Only see submitted results (not drafts)
            # - Other roles: Follow show_submitted flag
            
            if request.user.is_lecturer():
                # Lecturers only see draft results or no result yet
                if result and result.status != 'draft':
                    continue
            elif request.user.is_registrar() or request.user.is_principal():
                # Registrar and Principal only see submitted results
                if not result or result.status != 'submitted':
                    continue
            else:
                # For other roles, use the show_submitted flag
                if result and result.status == 'submitted' and not show_submitted:
                    continue
                if result and result.status != 'draft' and not show_submitted:
                    continue
            
            # Calculate grade
            grade = 'N/A'
            if result and result.total is not None:
                if result.total >= 70:
                    grade = 'A'
                elif result.total >= 60:
                    grade = 'B'
                elif result.total >= 50:
                    grade = 'C'
                elif result.total >= 40:
                    grade = 'D'
                else:
                    grade = 'F'
            
            # Check if user can edit
            can_edit = False
            if result:
                can_edit = result.can_edit(request.user)
            else:
                # No result yet - check if user can create one
                # Only lecturers can create new results (they will be drafts)
                if request.user.is_lecturer() and enrollment.unit.assigned_lecturer == request.user:
                    can_edit = True
            
            results_list.append({
                'id': result.id if result else None,
                'enrollment_id': enrollment.id,
                'student_id': enrollment.student.id,
                'student_name': enrollment.student.full_name,
                'student_admission': enrollment.student.admission_number,
                'unit_id': enrollment.unit.id,
                'unit_code': enrollment.unit.code,
                'unit_name': enrollment.unit.name,
                'cat_marks': float(result.cat_marks) if result and result.cat_marks else None,
                'exam_marks': float(result.exam_marks) if result and result.exam_marks else None,
                'total': float(result.total) if result and result.total else None,
                'grade': grade,
                'academic_year': enrollment.academic_year,
                'semester': enrollment.semester,
                'status': result.status if result else 'draft',
                'submitted_at': result.submitted_at.isoformat() if result and result.submitted_at else None,
                'can_edit': can_edit,
                'entered_by': result.entered_by.get_full_name() if result and result.entered_by else None
            })
        
        paginator = Paginator(results_list, page_size)
        page_obj = paginator.get_page(page)
        
        return JsonResponse({
            'count': paginator.count,
            'results': list(page_obj),
            'next': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'page': page_obj.number,
            'total_pages': paginator.num_pages
        })
    
    elif request.method in ['POST', 'PUT', 'PATCH']:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        enrollment_id = data.get('enrollment_id')
        if not enrollment_id:
            return JsonResponse({'error': 'Enrollment ID is required'}, status=400)
        
        try:
            enrollment = Enrollment.objects.get(pk=enrollment_id, unit__college=college)
        except Enrollment.DoesNotExist:
            return JsonResponse({'error': 'Enrollment not found'}, status=404)
        
        # Check if enrollment is exam_registered
        if not enrollment.exam_registered:
            return JsonResponse({'error': 'Student must be registered for examination to enter results'}, status=400)
        
        result, created = Result.objects.get_or_create(enrollment=enrollment)
        
        # Check can_edit permission
        if not result.can_edit(request.user):
            if result.status == 'submitted' and request.user.is_lecturer():
                return JsonResponse({'error': 'Cannot edit submitted results. Only college admins can edit submitted results.'}, status=403)
            return JsonResponse({'error': 'You do not have permission to edit this result'}, status=403)
        
        cat_marks = data.get('cat_marks')
        exam_marks = data.get('exam_marks')
        
        # Get max marks from grading criteria (cat_weight and exam_weight represent max marks)
        criteria = college.get_grading_criteria()
        max_cat = criteria.get('cat_weight', 30.0)
        max_exam = criteria.get('exam_weight', 70.0)
        
        # Validate marks range
        if cat_marks is not None:
            try:
                cat_marks = float(cat_marks)
                if cat_marks < 0 or cat_marks > max_cat:
                    return JsonResponse({'error': f'CAT marks must be between 0 and {max_cat}'}, status=400)
                result.cat_marks = cat_marks
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid CAT marks value'}, status=400)
        
        if exam_marks is not None:
            try:
                exam_marks = float(exam_marks)
                if exam_marks < 0 or exam_marks > max_exam:
                    return JsonResponse({'error': f'Exam marks must be between 0 and {max_exam}'}, status=400)
                result.exam_marks = exam_marks
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid exam marks value'}, status=400)
        
        # Status handling:
        # - College admins can set status directly if provided
        # - Lecturers: Always keep as draft when editing
        # - Registrar: Results created/edited by registrar are marked as submitted
        if 'status' in data and request.user.is_college_admin():
            result.status = data.get('status', 'draft')
        elif request.user.is_lecturer():
            result.status = 'draft'
        elif request.user.is_registrar() or request.user.is_principal():
            result.status = 'submitted'
        else:
            result.status = 'draft'
        
        result.entered_by = request.user
        result.save()  # This will calculate total using the save() method
        
        # Calculate grade
        grade = 'N/A'
        if result.total is not None:
            if result.total >= 70:
                grade = 'A'
            elif result.total >= 60:
                grade = 'B'
            elif result.total >= 50:
                grade = 'C'
            elif result.total >= 40:
                grade = 'D'
            else:
                grade = 'F'
        
        return JsonResponse({
            'id': result.id,
            'enrollment_id': enrollment.id,
            'student_id': enrollment.student.id,
            'student_name': enrollment.student.full_name,
            'student_admission': enrollment.student.admission_number,
            'unit_id': enrollment.unit.id,
            'unit_code': enrollment.unit.code,
            'unit_name': enrollment.unit.name,
            'cat_marks': float(result.cat_marks) if result.cat_marks else None,
            'exam_marks': float(result.exam_marks) if result.exam_marks else None,
            'total': float(result.total) if result.total else None,
            'grade': grade,
            'academic_year': enrollment.academic_year,
            'semester': enrollment.semester,
            'status': result.status,
            'submitted_at': result.submitted_at.isoformat() if result.submitted_at else None,
            'can_edit': result.can_edit(request.user)
        }, status=201 if created else 200)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_result_submit(request, college_slug, result_id):
    """API endpoint for submitting a result"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Only lecturers can submit (college admins don't need to submit)
    if not request.user.is_lecturer() and not request.user.is_college_admin():
        return JsonResponse({'error': 'Only lecturers and college admins can submit results'}, status=403)
    
    try:
        result = Result.objects.get(pk=result_id, enrollment__unit__college=college)
    except Result.DoesNotExist:
        return JsonResponse({'error': 'Result not found'}, status=404)
    
    # Check that result.entered_by == request.user OR user is college_admin
    if not request.user.is_college_admin():
        if result.entered_by != request.user:
            return JsonResponse({'error': 'You can only submit results that you entered'}, status=403)
    
    # Validate that at least one mark is entered
    if result.cat_marks is None and result.exam_marks is None:
        return JsonResponse({'error': 'At least one mark (CAT or Exam) must be entered before submission'}, status=400)
    
    # Validate marks are between 0-100 (should already be validated, but double-check)
    if result.cat_marks is not None and (result.cat_marks < 0 or result.cat_marks > 100):
        return JsonResponse({'error': 'CAT marks must be between 0 and 100'}, status=400)
    
    if result.exam_marks is not None and (result.exam_marks < 0 or result.exam_marks > 100):
        return JsonResponse({'error': 'Exam marks must be between 0 and 100'}, status=400)
    
    # Set status to submitted
    from django.utils import timezone
    result.status = 'submitted'
    result.submitted_at = timezone.now()
    result.save()
    
    # Calculate grade using college's grading system
    grade = 'N/A'
    if result.total is not None:
        college = result.enrollment.unit.college
        grade = college.calculate_grade(float(result.total))
    
    return JsonResponse({
        'success': True,
        'message': 'Result submitted successfully',
        'result': {
            'id': result.id,
            'enrollment_id': result.enrollment.id,
            'student_name': result.enrollment.student.full_name,
            'student_admission': result.enrollment.student.admission_number,
            'unit_code': result.enrollment.unit.code,
            'unit_name': result.enrollment.unit.name,
            'cat_marks': float(result.cat_marks) if result.cat_marks else None,
            'exam_marks': float(result.exam_marks) if result.exam_marks else None,
            'total': float(result.total) if result.total else None,
            'grade': grade,
            'status': result.status,
            'submitted_at': result.submitted_at.isoformat() if result.submitted_at else None
        }
    })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_lecturer_units_with_stats(request, college_slug):
    """API endpoint for lecturer's assigned units with enrollment and marks statistics"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Allow all authenticated users to access this endpoint
    # Everyone can view their own units and submit marks for their own units
    # Principals, registrars, and directors can see all units (for future registrar section)
    can_access_all = request.user.is_principal() or request.user.is_registrar() or request.user.is_director()
    
    # Get academic year, semester, and unit filters
    academic_year = request.GET.get('academic_year', '').strip() or college.current_academic_year
    semester_filter = request.GET.get('semester', '').strip()
    unit_filter = request.GET.get('unit', '').strip()
    search_filter = request.GET.get('search', '').strip()
    for_my_units = request.GET.get('for_my_units', 'false').lower() == 'true'
    only_submitted = request.GET.get('only_submitted', 'false').lower() == 'true'
    
    if not academic_year:
        from django.utils import timezone
        current_year = timezone.now().year
        academic_year = f"{current_year}/{current_year + 1}"
    
    # Get units assigned to the logged-in user (or all units if principal/registrar)
    if can_access_all:
        if for_my_units:
            # For My Units tab: show only units assigned to the registrar/principal
            units = CollegeUnit.objects.filter(
                college=college,
                assigned_lecturer=request.user
            ).select_related('assigned_lecturer', 'global_unit').order_by('code')
        else:
            # For Results tab: show all units (will be filtered by submitted status later)
            units = CollegeUnit.objects.filter(
                college=college
            ).select_related('assigned_lecturer', 'global_unit').order_by('code')
    else:
        # Regular users see only their assigned units
        units = CollegeUnit.objects.filter(
            college=college,
            assigned_lecturer=request.user
        ).select_related('assigned_lecturer', 'global_unit').order_by('code')
    
    # Apply unit filter if provided
    if unit_filter:
        try:
            unit_id = int(unit_filter)
            units = units.filter(id=unit_id)
        except ValueError:
            pass  # Invalid unit ID, ignore filter
    
    # Apply search filter if provided
    if search_filter:
        from django.db.models import Q
        units = units.filter(
            Q(code__icontains=search_filter) | Q(name__icontains=search_filter)
        )
    
    units_list = []
    for unit in units:
        # Get enrollments for this unit - show all enrolled students, not just exam-registered
        enrollments = Enrollment.objects.filter(
            unit=unit,
            academic_year=academic_year
        )
        
        if semester_filter:
            try:
                semester = int(semester_filter)
                enrollments = enrollments.filter(semester=semester)
            except ValueError:
                pass
        
        total_enrolled = enrollments.count()
        
        # Get exam-registered enrollments separately for marks counting
        exam_registered_enrollments = enrollments.filter(exam_registered=True)
        
        # Get results for exam-registered enrollments
        from django.db.models import Prefetch
        exam_registered_enrollments = exam_registered_enrollments.prefetch_related(
            Prefetch('result', queryset=Result.objects.select_related('entered_by'))
        )
        
        marked_count = 0
        submitted_count = 0
        draft_count = 0
        
        # Count marks only for exam-registered enrollments
        for enrollment in exam_registered_enrollments:
            try:
                result = enrollment.result
                if result:
                    # Check if result actually has marks (cat_marks or exam_marks)
                    has_marks = (result.cat_marks is not None) or (result.exam_marks is not None)
                    if has_marks:
                        marked_count += 1
                        if result.status == 'submitted':
                            submitted_count += 1
                        elif result.status == 'draft':
                            draft_count += 1
            except Result.DoesNotExist:
                pass
        
        # Determine status
        if submitted_count == total_enrolled and total_enrolled > 0:
            status = 'submitted'
        elif marked_count > 0:
            status = 'draft'
        else:
            status = 'empty'
        
        # For Results tab with only_submitted filter: skip units that don't have submitted results
        if only_submitted:
            if submitted_count == 0:
                continue  # Skip this unit if it doesn't have any submitted results
        
        # Get lecturer name who submitted (for registrar view)
        lecturer_name = None
        if unit.assigned_lecturer:
            lecturer_name = f"{unit.assigned_lecturer.first_name} {unit.assigned_lecturer.last_name}".strip()
        
        units_list.append({
            'id': unit.id,
            'code': unit.code,
            'name': unit.name,
            'academic_year': academic_year,
            'semester': unit.semester,
            'total_enrolled': total_enrolled,
            'marked_count': marked_count,
            'submitted_count': submitted_count,
            'draft_count': draft_count,
            'status': status,
            'lecturer_name': lecturer_name,
            'lecturer_id': unit.assigned_lecturer.id if unit.assigned_lecturer else None
        })
    
    # If no units found, include a message
    message = None
    if len(units_list) == 0:
        if can_access_all:
            message = 'No units found in this college.'
        else:
            message = 'No units assigned to you yet.'
    
    response_data = {
        'units': units_list,
        'count': len(units_list),
        'academic_year': academic_year
    }
    
    if message:
        response_data['message'] = message
    
    return JsonResponse(response_data)


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_unit_students_marks(request, college_slug, unit_id):
    """API endpoint to get all students enrolled in a unit with their marks for bulk entry"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    try:
        unit = CollegeUnit.objects.get(pk=unit_id, college=college)
    except CollegeUnit.DoesNotExist:
        return JsonResponse({'error': 'Unit not found'}, status=404)
    
    # Lecturers can only access their assigned units
    if request.user.is_lecturer() and unit.assigned_lecturer != request.user:
        return JsonResponse({'error': 'You do not have access to this unit'}, status=403)
    
    # Registrar and Principal can access all units (for viewing submitted results)
    # Lecturers can only access their assigned units (for entering draft results)
    
    # Get academic year and semester filters (both optional to show all enrollments)
    academic_year = request.GET.get('academic_year', '').strip()
    semester_filter = request.GET.get('semester', '').strip()
    
    # Get enrollments for this unit - show all enrolled students for marks entry
    enrollments = Enrollment.objects.filter(
        unit=unit
    ).select_related('student', 'unit')
    
    # Filter by academic year only if provided
    if academic_year:
        enrollments = enrollments.filter(academic_year=academic_year)
    elif college.current_academic_year:
        # If no year provided but college has current year, use it as default
        enrollments = enrollments.filter(academic_year=college.current_academic_year)
    
    # Filter by semester only if provided
    if semester_filter:
        try:
            semester = int(semester_filter)
            enrollments = enrollments.filter(semester=semester)
        except ValueError:
            pass
    
    # Prefetch results
    from django.db.models import Prefetch
    enrollments = enrollments.prefetch_related(
        Prefetch('result', queryset=Result.objects.select_related('entered_by'))
    ).order_by('student__admission_number')
    
    # Get grading criteria from college (lecturers need this for marks entry)
    criteria = college.get_grading_criteria()
    pass_mark = criteria.get('pass_mark', 50.0)
    cat_weight = criteria.get('cat_weight', 30.0)
    exam_weight = criteria.get('exam_weight', 70.0)
    
    students_list = []
    for enrollment in enrollments:
        try:
            result = enrollment.result
        except Result.DoesNotExist:
            result = None
        
        # Visibility rules:
        # - Lecturers: Only see draft results for their assigned units
        # - Registrar/Principal: See all students (can review and edit submitted results)
        if request.user.is_lecturer():
            # Lecturers only see draft results or no result yet
            if result and result.status != 'draft':
                continue
        # Note: Registrars and Principals can see all students - they can review submitted results
        # and edit them (permissions handled by can_edit check below)
        
        # Calculate grade
        grade = 'N/A'
        if result and result.total is not None:
            grade = college.calculate_grade(float(result.total))
        
        # Determine retake status
        retake = False
        retake_reason = None
        
        if not result or (result.cat_marks is None and result.exam_marks is None):
            retake = True
            retake_reason = 'No marks entered'
        elif result.total is not None and float(result.total) < pass_mark:
            retake = True
            retake_reason = f'Below pass mark ({pass_mark})'
        
        # Determine if user can edit
        can_edit = False
        if result:
            can_edit = result.can_edit(request.user)
        else:
            # No result yet - lecturers and registrars can create new results
            if request.user.is_lecturer() and enrollment.unit.assigned_lecturer == request.user:
                can_edit = True
            elif request.user.is_registrar() or request.user.is_principal():
                # Registrars can create results for students without results
                can_edit = True
        
        students_list.append({
            'enrollment_id': enrollment.id,
            'student_id': enrollment.student.id,
            'student_name': enrollment.student.full_name,
            'admission_number': enrollment.student.admission_number,
            'academic_year': enrollment.academic_year,
            'semester': enrollment.semester,
            'result_id': result.id if result else None,
            'cat_marks': float(result.cat_marks) if result and result.cat_marks is not None else None,
            'exam_marks': float(result.exam_marks) if result and result.exam_marks is not None else None,
            'total': float(result.total) if result and result.total is not None else None,
            'grade': grade,
            'status': result.status if result else 'draft',
            'retake': retake,
            'retake_reason': retake_reason,
            'can_edit': can_edit,
            'entered_by': result.entered_by.get_full_name() if result and result.entered_by else None
        })
    
    # Determine which academic year was actually used for filtering
    actual_academic_year = academic_year if academic_year else (college.current_academic_year if college.current_academic_year else None)
    
    return JsonResponse({
        'unit': {
            'id': unit.id,
            'code': unit.code,
            'name': unit.name
        },
        'students': students_list,
        'count': len(students_list),
        'academic_year': actual_academic_year,
        'pass_mark': pass_mark,
        'grading_criteria': {
            'cat_weight': cat_weight,
            'exam_weight': exam_weight,
            'pass_mark': pass_mark
        }
    })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_bulk_save_marks(request, college_slug):
    """API endpoint for bulk save marks (auto-save)"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    enrollment_id = data.get('enrollment_id')
    if not enrollment_id:
        return JsonResponse({'error': 'Enrollment ID is required'}, status=400)
    
    try:
        enrollment = Enrollment.objects.get(pk=enrollment_id, unit__college=college)
    except Enrollment.DoesNotExist:
        return JsonResponse({'error': 'Enrollment not found'}, status=404)
    
    # Check if enrollment is exam_registered
    if not enrollment.exam_registered:
        return JsonResponse({'error': 'Student must be registered for examination to enter results'}, status=400)
    
    # Lecturers can only edit their assigned units
    if request.user.is_lecturer() and enrollment.unit.assigned_lecturer != request.user:
        return JsonResponse({'error': 'You do not have permission to edit this result'}, status=403)
    
    result, created = Result.objects.get_or_create(enrollment=enrollment)
    
    # Check can_edit permission
    if not result.can_edit(request.user):
        if result.status == 'submitted':
            if request.user.is_lecturer():
                return JsonResponse({'error': 'Cannot edit submitted results. Only registrar can edit submitted results.'}, status=403)
            elif request.user.is_principal():
                return JsonResponse({'error': 'Cannot edit submitted results. Only registrar can edit submitted results.'}, status=403)
        return JsonResponse({'error': 'You do not have permission to edit this result'}, status=403)
    
    cat_marks = data.get('cat_marks')
    exam_marks = data.get('exam_marks')
    
    # Get max marks from grading criteria
    criteria = college.get_grading_criteria()
    max_cat = criteria.get('cat_weight', 30.0)
    max_exam = criteria.get('exam_weight', 70.0)
    
    # Validate marks range
    if cat_marks is not None:
        try:
            cat_marks = float(cat_marks)
            if cat_marks < 0 or cat_marks > max_cat:
                return JsonResponse({'error': f'CAT marks must be between 0 and {max_cat}'}, status=400)
            result.cat_marks = cat_marks
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid CAT marks value'}, status=400)
    
    if exam_marks is not None:
        try:
            exam_marks = float(exam_marks)
            if exam_marks < 0 or exam_marks > max_exam:
                return JsonResponse({'error': f'Exam marks must be between 0 and {max_exam}'}, status=400)
            result.exam_marks = exam_marks
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid exam marks value'}, status=400)
    
    # Status handling:
    # - Lecturers: Always keep as draft when auto-saving
    # - Registrar: Results created/edited by registrar are marked as submitted
    if request.user.is_lecturer():
        result.status = 'draft'
    elif request.user.is_registrar() or request.user.is_principal():
        # Registrar edits/creates are marked as submitted
        result.status = 'submitted'
    
    result.entered_by = request.user
    result.save()
    
    # Calculate grade
    grade = 'N/A'
    if result.total is not None:
        grade = college.calculate_grade(float(result.total))
    
    # Get pass mark
    pass_mark = criteria.get('pass_mark', 50.0)
    retake = False
    retake_reason = None
    
    if not result.cat_marks and not result.exam_marks:
        retake = True
        retake_reason = 'No marks entered'
    elif result.total is not None and float(result.total) < pass_mark:
        retake = True
        retake_reason = f'Below pass mark ({pass_mark})'
    
    return JsonResponse({
        'success': True,
        'result': {
            'id': result.id,
            'enrollment_id': enrollment.id,
            'cat_marks': float(result.cat_marks) if result.cat_marks is not None else None,
            'exam_marks': float(result.exam_marks) if result.exam_marks is not None else None,
            'total': float(result.total) if result.total is not None else None,
            'grade': grade,
            'status': result.status,
            'retake': retake,
            'retake_reason': retake_reason
        }
    })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_bulk_submit_marks(request, college_slug, unit_id):
    """API endpoint for bulk submit all marks for a unit"""
    try:
        college = get_college_from_slug(college_slug)
        if not college:
            return JsonResponse({'error': 'College not found'}, status=404)
        
        verify_user_college_access(request, college)
        
        try:
            unit = CollegeUnit.objects.get(pk=unit_id, college=college)
        except CollegeUnit.DoesNotExist:
            return JsonResponse({'error': 'Unit not found'}, status=404)
        
        # Lecturers can only submit their assigned units
        if request.user.is_lecturer() and unit.assigned_lecturer != request.user:
            return JsonResponse({'error': 'You do not have permission to submit results for this unit'}, status=403)
        
        # Parse request body - handle empty body
        try:
            if request.body:
                data = json.loads(request.body)
            else:
                data = {}
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Get academic year - use provided value or default to college's current academic year
        academic_year = data.get('academic_year')
        if academic_year:
            academic_year = str(academic_year).strip()
            if not academic_year:
                academic_year = None
        if not academic_year:
            academic_year = college.current_academic_year
        
        # Get semester filter if provided
        semester_filter = data.get('semester')
        if semester_filter:
            semester_filter = str(semester_filter).strip()
            if not semester_filter:
                semester_filter = None
        
        if not academic_year:
            current_year = timezone.now().year
            academic_year = f"{current_year}/{current_year + 1}"
        
        # Get enrollments for this unit
        enrollments = Enrollment.objects.filter(
            unit=unit,
            academic_year=academic_year,
            exam_registered=True
        )
        
        if semester_filter:
            try:
                semester = int(semester_filter)
                enrollments = enrollments.filter(semester=semester)
            except ValueError:
                pass
        
        # Prefetch results
        from django.db.models import Prefetch
        enrollments = enrollments.prefetch_related(
            Prefetch('result', queryset=Result.objects.select_related('entered_by'))
        )
        
        submitted_count = 0
        errors = []
        
        for enrollment in enrollments:
            try:
                result, created = Result.objects.get_or_create(enrollment=enrollment)
                
                # If result was just created, set entered_by
                if created:
                    result.entered_by = request.user
                    result.save()
                
                # Check permission
                if not result.can_edit(request.user):
                    student_id = getattr(enrollment.student, 'admission_number', 'Unknown')
                    errors.append(f"Cannot submit result for {student_id}: Permission denied")
                    continue
                
                # Only submit draft results
                if result.status == 'submitted':
                    continue
                
                # Validate that at least one mark is entered
                if result.cat_marks is None and result.exam_marks is None:
                    student_id = getattr(enrollment.student, 'admission_number', 'Unknown')
                    errors.append(f"Cannot submit result for {student_id}: At least one mark (CAT or Exam) must be entered")
                    continue
                
                # Set status to submitted
                result.status = 'submitted'
                result.submitted_at = timezone.now()
                # Ensure entered_by is set
                if not result.entered_by:
                    result.entered_by = request.user
                result.save()
                submitted_count += 1
            except Exception as e:
                import traceback
                student_id = getattr(enrollment.student, 'admission_number', 'Unknown') if 'enrollment' in locals() else 'Unknown'
                error_msg = f"Error submitting result for {student_id}: {str(e)}"
                errors.append(error_msg)
                # Log the full traceback for debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error in bulk submit for enrollment {getattr(enrollment, 'id', 'Unknown')}: {traceback.format_exc()}")
                continue
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully submitted {submitted_count} result(s)',
            'submitted_count': submitted_count,
            'errors': errors if errors else None
        })
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Critical error in api_bulk_submit_marks: {traceback.format_exc()}")
        return JsonResponse({
            'error': f'An error occurred while submitting results: {str(e)}',
            'success': False
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_results_export_csv(request, college_slug):
    """
    API endpoint for exporting results to CSV with field selection
    Applies same filters as api_results_list but exports all matching results (no pagination)
    """
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Get filter parameters
    search = request.GET.get('search', '')
    unit_filter = request.GET.get('unit', '')
    semester_filter = request.GET.get('semester', '')
    academic_year_filter = request.GET.get('academic_year', '')
    show_submitted = request.GET.get('show_submitted', 'true').lower() == 'true'
    status_filter = request.GET.get('status', 'all')  # all, draft, submitted
    
    # Get selected fields
    fields_param = request.GET.get('fields', '')
    if not fields_param:
        return JsonResponse({'error': 'No fields selected for export'}, status=400)
    
    selected_fields = [f.strip() for f in fields_param.split(',') if f.strip()]
    if not selected_fields:
        return JsonResponse({'error': 'No valid fields selected for export'}, status=400)
    
    # Field mapping: frontend field name -> (data key, display name)
    field_mapping = {
        'student_name': ('student_name', 'Student Name'),
        'admission_number': ('student_admission', 'Admission Number'),
        'student_id': ('student_id', 'Student ID'),
        'unit_code': ('unit_code', 'Unit Code'),
        'unit_name': ('unit_name', 'Unit Name'),
        'unit_id': ('unit_id', 'Unit ID'),
        'academic_year': ('academic_year', 'Academic Year'),
        'semester': ('semester', 'Semester'),
        'cat_marks': ('cat_marks', 'CAT Marks'),
        'exam_marks': ('exam_marks', 'Exam Marks'),
        'total_marks': ('total', 'Total Marks'),
        'grade': ('grade', 'Grade'),
        'status': ('status', 'Status'),
        'submitted_at': ('submitted_at', 'Submitted At'),
        'entered_by': ('entered_by', 'Entered By'),
    }
    
    # Validate selected fields
    valid_fields = []
    for field in selected_fields:
        if field in field_mapping:
            valid_fields.append(field)
    
    if not valid_fields:
        return JsonResponse({'error': 'No valid fields selected'}, status=400)
    
    # Use provided academic_year or default to college's current_academic_year
    academic_year = academic_year_filter if academic_year_filter else college.current_academic_year
    if not academic_year:
        from django.utils import timezone
        current_year = timezone.now().year
        academic_year = f"{current_year}/{current_year + 1}"
    
    # Start with enrollments filtered by exam_registered=True and academic year
    enrollments = Enrollment.objects.filter(
        unit__college=college,
        exam_registered=True,
        academic_year=academic_year
    ).select_related('student', 'unit', 'unit__assigned_lecturer')
    
    # Filter by semester if provided
    if semester_filter:
        try:
            semester = int(semester_filter)
            enrollments = enrollments.filter(semester=semester)
        except ValueError:
            pass
    
    # Lecturers: filter by assigned units only
    if request.user.is_lecturer():
        enrollments = enrollments.filter(unit__assigned_lecturer=request.user)
    
    if search:
        enrollments = enrollments.filter(
            Q(student__full_name__icontains=search) |
            Q(student__admission_number__icontains=search) |
            Q(unit__code__icontains=search)
        )
    
    if unit_filter:
        enrollments = enrollments.filter(unit_id=unit_filter)
    
    # Prefetch results
    from django.db.models import Prefetch
    enrollments = enrollments.prefetch_related(
        Prefetch('result', queryset=Result.objects.select_related('entered_by'))
    )
    
    # Build results list
    results_list = []
    for enrollment in enrollments:
        try:
            result = enrollment.result
        except Result.DoesNotExist:
            result = None
        
        # Apply visibility rules based on user role
        # - Lecturers: Only see draft results for their assigned units
        # - Registrar/Principal: Only see submitted results
        if request.user.is_lecturer():
            # Lecturers only see draft results or no result yet
            if result and result.status != 'draft':
                continue
        elif request.user.is_registrar() or request.user.is_principal():
            # Registrar and Principal only see submitted results
            if not result or result.status != 'submitted':
                continue
        else:
            # For other roles, apply status filter
            if status_filter == 'draft':
                if not result or result.status != 'draft':
                    continue
            elif status_filter == 'submitted':
                if not result or result.status != 'submitted':
                    continue
            # If status_filter is 'all', include all results (respecting show_submitted)
            elif status_filter == 'all':
                # Exclude submitted results unless show_submitted=True
                if result and result.status == 'submitted' and not show_submitted:
                    continue
        
        # Calculate grade
        grade = 'N/A'
        if result and result.total is not None:
            grade = college.calculate_grade(float(result.total))
        
        # Build result data
        result_data = {
            'student_name': enrollment.student.full_name,
            'student_admission': enrollment.student.admission_number,
            'student_id': enrollment.student.id,
            'unit_id': enrollment.unit.id,
            'unit_code': enrollment.unit.code,
            'unit_name': enrollment.unit.name,
            'cat_marks': float(result.cat_marks) if result and result.cat_marks else None,
            'exam_marks': float(result.exam_marks) if result and result.exam_marks else None,
            'total': float(result.total) if result and result.total else None,
            'grade': grade,
            'academic_year': enrollment.academic_year,
            'semester': enrollment.semester,
            'status': result.status if result else 'draft',
            'submitted_at': result.submitted_at.isoformat() if result and result.submitted_at else None,
            'entered_by': result.entered_by.get_full_name() if result and result.entered_by else None
        }
        
        results_list.append(result_data)
    
    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header row
    headers = [field_mapping[field][1] for field in valid_fields]
    writer.writerow(headers)
    
    # Write data rows
    for result_data in results_list:
        row = []
        for field in valid_fields:
            data_key = field_mapping[field][0]
            value = result_data.get(data_key)
            
            # Format values
            if value is None:
                row.append('')
            elif isinstance(value, float):
                # Format decimal numbers to 1 decimal place
                row.append(f"{value:.1f}")
            elif isinstance(value, int):
                row.append(str(value))
            elif isinstance(value, str) and 'T' in value and ':' in value:
                # Date/time string - format for CSV
                try:
                    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    row.append(dt.strftime('%Y-%m-%d %H:%M'))
                except (ValueError, AttributeError):
                    row.append(value)
            else:
                row.append(str(value))
        
        writer.writerow(row)
    
    # Create HTTP response
    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8-sig')
    
    # Generate filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"results_export_{slugify(college.name)}_{timestamp}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_admin_export_teachers(request, college_slug):
    """API endpoint for exporting teachers/lecturers to CSV"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Only college admins can export
    if not request.user.is_college_admin():
        return JsonResponse({'error': 'Only college administrators can export data'}, status=403)
    
    # Get filter parameters
    role = request.GET.get('role', '')
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    
    # Query users (exclude super_admin and director - director should not be visible to other users)
    users = CustomUser.objects.filter(college=college).exclude(role='super_admin').exclude(role='director')
    
    if role:
        users = users.filter(role=role)
    
    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )
    
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)
    
    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    headers = ['ID', 'Username', 'First Name', 'Last Name', 'Full Name', 'Email', 'Phone', 'Role', 'Status', 'Assigned Units Count']
    writer.writerow(headers)
    
    # Write data
    for user in users:
        assigned_units_count = CollegeUnit.objects.filter(college=college, assigned_lecturer=user).count()
        writer.writerow([
            user.id,
            user.username,
            user.first_name or '',
            user.last_name or '',
            f"{user.first_name} {user.last_name}".strip() or user.username,
            user.email or '',
            user.phone or '',
            user.get_role_display(),
            'Active' if user.is_active else 'Inactive',
            assigned_units_count
        ])
    
    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8-sig')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"teachers_export_{slugify(college.name)}_{timestamp}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_admin_export_units(request, college_slug):
    """API endpoint for exporting units to CSV"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Only college admins can export
    if not request.user.is_college_admin():
        return JsonResponse({'error': 'Only college administrators can export data'}, status=403)
    
    # Get filter parameters
    course_id = request.GET.get('course_id', '')
    academic_year = request.GET.get('academic_year', '')
    semester = request.GET.get('semester', '')
    search = request.GET.get('search', '')
    
    # Query units
    units = CollegeUnit.objects.filter(college=college)
    
    if course_id:
        # Get units through course-unit relationships
        course_unit_ids = CollegeCourseUnit.objects.filter(
            course_id=int(course_id)
        ).values_list('unit_id', flat=True)
        units = units.filter(id__in=course_unit_ids)
    
    if academic_year:
        # Filter by enrollments in that academic year
        enrollment_unit_ids = Enrollment.objects.filter(
            academic_year=academic_year,
            unit__college=college
        ).values_list('unit_id', flat=True).distinct()
        units = units.filter(id__in=enrollment_unit_ids)
    
    if semester:
        try:
            semester_int = int(semester)
            enrollment_unit_ids = Enrollment.objects.filter(
                semester=semester_int,
                unit__college=college
            ).values_list('unit_id', flat=True).distinct()
            units = units.filter(id__in=enrollment_unit_ids)
        except ValueError:
            pass
    
    if search:
        units = units.filter(
            Q(code__icontains=search) |
            Q(name__icontains=search)
        )
    
    units = units.select_related('assigned_lecturer', 'global_unit').distinct()
    
    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    headers = ['ID', 'Code', 'Name', 'Assigned Lecturer', 'Lecturer Email', 'Global Unit Code', 'Global Unit Name', 'Course Count']
    writer.writerow(headers)
    
    # Write data
    for unit in units:
        course_count = CollegeCourseUnit.objects.filter(unit=unit).count()
        writer.writerow([
            unit.id,
            unit.code,
            unit.name,
            unit.assigned_lecturer.get_full_name() if unit.assigned_lecturer else '',
            unit.assigned_lecturer.email if unit.assigned_lecturer else '',
            unit.global_unit.code if unit.global_unit else '',
            unit.global_unit.name if unit.global_unit else '',
            course_count
        ])
    
    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8-sig')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"units_export_{slugify(college.name)}_{timestamp}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_admin_export_courses(request, college_slug):
    """API endpoint for exporting courses to CSV"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Only college admins can export
    if not request.user.is_college_admin():
        return JsonResponse({'error': 'Only college administrators can export data'}, status=403)
    
    # Get filter parameters
    academic_year = request.GET.get('academic_year', '')
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    
    # Query courses
    courses = CollegeCourse.objects.filter(college=college)
    
    if search:
        courses = courses.filter(name__icontains=search)
    
    if academic_year:
        # Filter courses that have enrollments in that academic year
        enrollment_course_ids = Enrollment.objects.filter(
            academic_year=academic_year,
            student__college=college
        ).values_list('student__course_id', flat=True).distinct()
        courses = courses.filter(id__in=enrollment_course_ids)
    
    # Status filter (courses don't have explicit status, but we can check if they have active enrollments)
    if status == 'active':
        # Courses with recent enrollments
        from django.utils import timezone
        current_year = timezone.now().year
        current_academic_year = f"{current_year}/{current_year + 1}"
        enrollment_course_ids = Enrollment.objects.filter(
            academic_year=current_academic_year,
            student__college=college
        ).values_list('student__course_id', flat=True).distinct()
        courses = courses.filter(id__in=enrollment_course_ids)
    elif status == 'inactive':
        # Courses without recent enrollments
        from django.utils import timezone
        current_year = timezone.now().year
        current_academic_year = f"{current_year}/{current_year + 1}"
        enrollment_course_ids = Enrollment.objects.filter(
            academic_year=current_academic_year,
            student__college=college
        ).values_list('student__course_id', flat=True).distinct()
        courses = courses.exclude(id__in=enrollment_course_ids)
    
    courses = courses.select_related('global_course').distinct()
    
    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    headers = ['ID', 'Code', 'Name', 'Duration (Years)', 'Global Course', 'Global Course Level', 'Student Count', 'Unit Count', 'Admission Requirements']
    writer.writerow(headers)
    
    # Write data
    for course in courses:
        student_count = Student.objects.filter(college=college, course=course).count()
        unit_count = CollegeCourseUnit.objects.filter(course=course).count()
        writer.writerow([
            course.id,
            course.code,
            course.name,
            course.duration_years or '',
            course.global_course.name if course.global_course else '',
            course.global_course.get_level_display() if course.global_course else '',
            student_count,
            unit_count,
            course.admission_requirements or ''
        ])
    
    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8-sig')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"courses_export_{slugify(college.name)}_{timestamp}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_admin_export_students(request, college_slug):
    """API endpoint for exporting students to CSV"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Only college admins can export
    if not request.user.is_college_admin():
        return JsonResponse({'error': 'Only college administrators can export data'}, status=403)
    
    # Check if simple format is requested (only name and admission number)
    export_format = request.GET.get('format', 'full')
    student_ids_param = request.GET.get('student_ids', '')
    
    # If student_ids are provided, use them directly
    if student_ids_param:
        try:
            student_ids = [int(id) for id in student_ids_param.split(',') if id.strip()]
            students = Student.objects.filter(id__in=student_ids, college=college).order_by('admission_number')
        except ValueError:
            return JsonResponse({'error': 'Invalid student IDs format'}, status=400)
    else:
        # Get filter parameters
        course_id = request.GET.get('course_id', '')
        academic_year = request.GET.get('academic_year', '')
        year_of_study = request.GET.get('year_of_study', '')
        search = request.GET.get('search', '')
        status = request.GET.get('status', '')
        
        # Query students
        students = Student.objects.filter(college=college)
        
        if course_id:
            students = students.filter(course_id=int(course_id))
        
        if academic_year:
            # Filter students with enrollments in that academic year
            enrollment_student_ids = Enrollment.objects.filter(
                academic_year=academic_year,
                student__college=college
            ).values_list('student_id', flat=True).distinct()
            students = students.filter(id__in=enrollment_student_ids)
        
        if year_of_study:
            try:
                year_int = int(year_of_study)
                # Filter by year_of_study field if it exists, otherwise filter by enrollments
                if hasattr(Student, 'year_of_study'):
                    students = students.filter(year_of_study=year_int)
                else:
                    # Fallback: filter by students with enrollments in that year
                    enrollment_student_ids = Enrollment.objects.filter(
                        student__college=college
                    ).values_list('student_id', flat=True).distinct()
                    students = students.filter(id__in=enrollment_student_ids)
            except ValueError:
                pass
        
        if search:
            students = students.filter(
                Q(full_name__icontains=search) |
                Q(admission_number__icontains=search)
            )
        
        if status == 'active':
            students = students.filter(status='active')
        elif status == 'graduated':
            students = students.filter(status='graduated')
        elif status == 'inactive':
            # Include suspended and deferred as inactive
            students = students.filter(status__in=['suspended', 'deferred'])
        
        students = students.select_related('course').distinct()
    
    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header based on format
    if export_format == 'simple':
        headers = ['Admission Number', 'Full Name']
        writer.writerow(headers)
        
        # Write data - only admission number and full name
        for student in students:
            writer.writerow([
                student.admission_number,
                student.full_name
            ])
    else:
        # Full format with all fields
        headers = ['ID', 'Admission Number', 'Full Name', 'Email', 'Phone', 'Gender', 'Course', 'Year of Study', 'Status', 'Graduation Date', 'Created At']
        writer.writerow(headers)
        
        # Write data
        for student in students:
            # Get year of study from student model
            year_of_study = student.year_of_study if hasattr(student, 'year_of_study') else ''
            
            writer.writerow([
                student.id,
                student.admission_number,
                student.full_name,
                student.email or '',
                student.phone or '',
                student.get_gender_display() if hasattr(student, 'get_gender_display') else (student.gender if hasattr(student, 'gender') else ''),
                student.course.name if student.course else '',
                year_of_study,
                student.get_status_display() if hasattr(student, 'get_status_display') else student.status,
                student.graduation_date.strftime('%Y-%m-%d') if hasattr(student, 'graduation_date') and student.graduation_date else '',
                student.created_at.strftime('%Y-%m-%d') if hasattr(student, 'created_at') and student.created_at else ''
            ])
    
    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8-sig')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"students_export_{slugify(college.name)}_{timestamp}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_admin_export_students_pdf(request, college_slug):
    """API endpoint for exporting student list to PDF"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Only college admins can export
    if not request.user.is_college_admin():
        return JsonResponse({'error': 'Only college administrators can export data'}, status=403)
    
    # Get student IDs
    student_ids_param = request.GET.get('student_ids', '')
    if not student_ids_param:
        return JsonResponse({'error': 'No students selected'}, status=400)
    
    try:
        student_ids = [int(id) for id in student_ids_param.split(',') if id.strip()]
        students = Student.objects.filter(id__in=student_ids, college=college).order_by('admission_number')
    except ValueError:
        return JsonResponse({'error': 'Invalid student IDs format'}, status=400)
    
    if not students.exists():
        return JsonResponse({'error': 'No students found'}, status=404)
    
    # Get report type (default to transcript)
    report_type = request.GET.get('report_type', 'transcript')
    
    try:
        # Get template for the report type
        template = get_template_for_report_type(college, report_type)
        
        if not template:
            # If no template, generate a simple table-based PDF
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib import colors
            from io import BytesIO
            
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
            
            # Container for the 'Flowable' objects
            elements = []
            styles = getSampleStyleSheet()
            
            # Title
            title = Paragraph(f"<b>Student List - {college.name}</b>", styles['Title'])
            elements.append(title)
            elements.append(Spacer(1, 0.2*inch))
            
            # Create table data
            data = [['Admission Number', 'Full Name']]
            for student in students:
                data.append([student.admission_number or '-', student.full_name or '-'])
            
            # Create table
            table = Table(data, colWidths=[2*inch, 4*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            
            elements.append(table)
            
            # Build PDF
            doc.build(elements)
            
            # Get the value of the BytesIO buffer
            pdf = buffer.getvalue()
            buffer.close()
            
            # Create HTTP response
            response = HttpResponse(pdf, content_type='application/pdf')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"student_list_{slugify(college.name)}_{timestamp}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        else:
            # Use template to generate PDF for each student
            # For now, generate a simple combined PDF
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib import colors
            from io import BytesIO
            
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
            
            elements = []
            styles = getSampleStyleSheet()
            
            # Title
            title = Paragraph(f"<b>Student List - {college.name}</b>", styles['Title'])
            elements.append(title)
            elements.append(Spacer(1, 0.2*inch))
            
            # Create table data
            data = [['Admission Number', 'Full Name']]
            for student in students:
                data.append([student.admission_number or '-', student.full_name or '-'])
            
            # Create table
            table = Table(data, colWidths=[2*inch, 4*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            
            elements.append(table)
            doc.build(elements)
            
            pdf = buffer.getvalue()
            buffer.close()
            
            response = HttpResponse(pdf, content_type='application/pdf')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"student_list_{slugify(college.name)}_{timestamp}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating student list PDF: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'Error generating PDF: {str(e)}'
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_dashboard_overview(request, college_slug):
    """API endpoint for dashboard overview statistics - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        # Calculate statistics
        total_students = Student.objects.filter(college=college).count()
        total_courses = CollegeCourse.objects.filter(college=college).count()
        total_lecturers = CustomUser.objects.filter(college=college, role='lecturer').count()
        total_units = CollegeUnit.objects.filter(college=college).count()
        
        # Count unique departments (using first word of course names as department)
        # Optimize: Use values_list to get only names, reducing memory usage
        course_names = CollegeCourse.objects.filter(college=college).values_list('name', flat=True)
        seen_departments = set()
        for course_name in course_names:
            dept_name = course_name.split()[0] if course_name else 'General'
            seen_departments.add(dept_name)
        total_departments = len(seen_departments)
        
        # Get recent students (last 5, ordered by created_at)
        recent_students = Student.objects.filter(college=college).select_related('course').order_by('-created_at')[:5]
        recent_students_list = []
        for student in recent_students:
            recent_students_list.append({
                'id': student.id,
                'admission_number': student.admission_number,
                'full_name': student.full_name,
                'created_at': student.created_at.strftime('%Y-%m-%d') if student.created_at else None
            })
        
        # Get recent activities (last 5 enrollments)
        recent_enrollments = Enrollment.objects.filter(unit__college=college).select_related(
            'student', 'unit'
        ).order_by('-enrolled_at')[:5]
        recent_activities = []
        for enrollment in recent_enrollments:
            recent_activities.append({
                'type': 'enrollment',
                'student_name': enrollment.student.full_name,
                'unit_code': enrollment.unit.code,
                'academic_year': enrollment.academic_year,
                'date': enrollment.enrolled_at.strftime('%Y-%m-%d') if enrollment.enrolled_at else None
            })
        
        return JsonResponse({
            'total_students': total_students,
            'total_departments': total_departments,
            'total_courses': total_courses,
            'total_lecturers': total_lecturers,
            'total_units': total_units,
            'recent_students': recent_students_list,
            'recent_activities': recent_activities
        })


# ============================================
# Student Portal API Endpoints
# ============================================

def verify_student_access(request, college_slug):
    """Helper to verify student is authenticated and belongs to college"""
    try:
        college = get_college_from_slug(college_slug)
        if not college:
            return JsonResponse({'error': 'College not found'}, status=404), None, None
        
        student_id = request.session.get('student_id')
        if not student_id:
            return JsonResponse({'error': 'Authentication required'}, status=401), None, None
        
        try:
            student = Student.objects.get(pk=student_id, college=college)
        except Student.DoesNotExist:
            return JsonResponse({'error': 'Invalid session'}, status=401), None, None
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error retrieving student in verify_student_access: {str(e)}", exc_info=True)
            return JsonResponse({'error': 'Error retrieving student'}, status=500), None, None
        
        return None, student, college
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in verify_student_access: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Error verifying access'}, status=500), None, None


@csrf_exempt
@require_http_methods(["GET"])
def api_student_dashboard_overview(request, college_slug):
    """API endpoint for student dashboard overview"""
    try:
        error_response, student, college = verify_student_access(request, college_slug)
        if error_response:
            return error_response
        
        # Get enrolled units count
        total_enrolled_units = Enrollment.objects.filter(student=student).count()
        
        # Get current semester (can be derived from enrollments or set default)
        current_semester = 1  # Default, can be enhanced later
        
        # Get recent results with proper select_related
        recent_results = Result.objects.filter(
            enrollment__student=student
        ).select_related('enrollment', 'enrollment__unit').order_by('-enrollment__academic_year', '-enrollment__semester')[:5]
        
        recent_results_list = []
        for result in recent_results:
            # Skip if enrollment or unit is None (deleted)
            if not result.enrollment or not result.enrollment.unit:
                continue
            # Calculate grade
            grade = None
            if result.total is not None:
                try:
                    grade = college.calculate_grade(float(result.total))
                except Exception:
                    grade = None
            
            recent_results_list.append({
                'unit_code': result.enrollment.unit.code,
                'unit_name': result.enrollment.unit.name,
                'total': float(result.total) if result.total else None,
                'grade': grade,
                'academic_year': result.enrollment.academic_year,
                'semester': result.enrollment.semester
            })
        
        # Get enrolled units for current academic year
        from django.utils import timezone
        current_year = timezone.now().year
        current_enrollments = Enrollment.objects.filter(
            student=student,
            academic_year=str(current_year)
        ).select_related('unit', 'unit__assigned_lecturer')
        
        enrolled_units_list = []
        for enrollment in current_enrollments:
            # Skip if unit is None (deleted unit)
            if not enrollment.unit:
                continue
            enrolled_units_list.append({
                'unit_code': enrollment.unit.code,
                'unit_name': enrollment.unit.name,
                'semester': enrollment.semester,
                'lecturer': f"{enrollment.unit.assigned_lecturer.first_name} {enrollment.unit.assigned_lecturer.last_name}".strip() if enrollment.unit.assigned_lecturer else None
            })
        
        # Get student's current semester
        student_current_semester = student.current_semester if student.current_semester else 1
        
        return JsonResponse({
            'total_enrolled_units': total_enrolled_units,
            'current_semester': student_current_semester,
            'current_year': student.year_of_study,
            'course_name': student.course.name if student.course else None,
            'recent_results': recent_results_list,
            'current_enrollments': enrolled_units_list[:5]  # Last 5
        })
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in api_student_dashboard_overview: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'An error occurred while loading dashboard data'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET", "PUT"])
def api_student_profile(request, college_slug):
    """API endpoint for student profile"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    if request.method == 'GET':
        return JsonResponse({
            'id': student.id,
            'admission_number': student.admission_number,
            'full_name': student.full_name,
            'email': student.email or '',
            'phone': student.phone or '',
            'gender': student.gender,
            'date_of_birth': student.date_of_birth.strftime('%Y-%m-%d') if student.date_of_birth else None,
            'year_of_study': student.year_of_study,
            'course_id': student.course.id if student.course else None,
            'course_name': student.course.name if student.course else None,
            'college_name': college.name
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Allow updating email and phone only
        if 'email' in data:
            student.email = data['email']
        if 'phone' in data:
            student.phone = data['phone']
        
        student.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Profile updated successfully',
            'student': {
                'id': student.id,
                'admission_number': student.admission_number,
                'full_name': student.full_name,
                'email': student.email or '',
                'phone': student.phone or ''
            }
        })


@csrf_exempt
@require_http_methods(["GET"])
def api_student_courses(request, college_slug):
    """API endpoint for student's enrolled courses"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    courses = []
    if student.course:
        courses.append({
            'id': student.course.id,
            'name': student.course.name,
            'duration_years': student.course.duration_years,
            'year_of_study': student.year_of_study
        })
    
    return JsonResponse({
        'courses': courses
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_student_units(request, college_slug):
    """API endpoint for student's enrolled units"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    academic_year = request.GET.get('academic_year', '')
    semester = request.GET.get('semester', '')
    
    enrollments = Enrollment.objects.filter(student=student)
    
    if academic_year:
        enrollments = enrollments.filter(academic_year=academic_year)
    if semester:
        enrollments = enrollments.filter(semester=int(semester))
    
    enrollments = enrollments.order_by('-academic_year', '-semester', 'unit__code')
    
    units_list = []
    for enrollment in enrollments:
        # Get year_of_study from CollegeCourseUnit if student has a course
        year_of_study = None
        if student.course:
            try:
                course_unit = CollegeCourseUnit.objects.get(
                    course=student.course,
                    unit=enrollment.unit,
                    semester=enrollment.semester
                )
                year_of_study = course_unit.year_of_study
            except CollegeCourseUnit.DoesNotExist:
                # Try to find any assignment for this unit in the course
                course_unit = CollegeCourseUnit.objects.filter(
                    course=student.course,
                    unit=enrollment.unit
                ).first()
                if course_unit:
                    year_of_study = course_unit.year_of_study
        
        units_list.append({
            'id': enrollment.unit.id,
            'enrollment_id': enrollment.id,
            'code': enrollment.unit.code,
            'name': enrollment.unit.name,
            'semester': enrollment.semester,
            'year_of_study': year_of_study,
            'academic_year': enrollment.academic_year,
            'lecturer_name': enrollment.unit.assigned_lecturer.get_full_name() if enrollment.unit.assigned_lecturer else None,
            'lecturer_email': enrollment.unit.assigned_lecturer.email if enrollment.unit.assigned_lecturer else None,
            'enrolled_at': enrollment.enrolled_at.strftime('%Y-%m-%d') if enrollment.enrolled_at else None,
            'exam_registered': enrollment.exam_registered,
            'exam_registered_at': enrollment.exam_registered_at.isoformat() if enrollment.exam_registered_at else None
        })
    
    return JsonResponse({
        'units': units_list,
        'count': len(units_list)
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_student_course_units(request, college_slug):
    """API endpoint for student's course units (assigned to course, not enrolled)
    - For 'My Units': Shows units up to current semester
    - For exam registration: Shows current + previous semesters (for retakes)
    """
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    if not student.course:
        return JsonResponse({
            'units': [],
            'count': 0,
            'message': 'No course assigned'
        })
    
    # Get filters
    year = request.GET.get('year', '')
    semester = request.GET.get('semester', '')
    up_to_current = request.GET.get('up_to_current', 'false').lower() == 'true'
    for_exam_registration = request.GET.get('for_exam_registration', 'false').lower() == 'true'
    
    # Get course units assigned to student's course
    course_units = CollegeCourseUnit.objects.filter(
        course=student.course,
        college=college
    ).select_related('unit', 'unit__assigned_lecturer')
    
    # Filter by year of study if provided
    if year:
        course_units = course_units.filter(year_of_study=int(year))
    
    # Filter by semester if provided
    if semester:
        course_units = course_units.filter(semester=int(semester))
    
    # For "My Units" - show only units up to current semester
    if up_to_current:
        current_year = student.year_of_study
        current_sem = student.current_semester or student.get_current_semester() or 1
        
        # Show units where:
        # - year_of_study < current_year, OR
        # - year_of_study == current_year AND semester <= current_sem
        course_units = course_units.filter(
            Q(year_of_study__lt=current_year) |
            Q(year_of_study=current_year, semester__lte=current_sem)
        )
    
    # For exam registration - show current semester + all previous semesters
    if for_exam_registration:
        current_year = student.year_of_study
        current_sem = student.current_semester or student.get_current_semester() or 1
        
        # Show units where:
        # - year_of_study < current_year, OR
        # - year_of_study == current_year AND semester <= current_sem
        course_units = course_units.filter(
            Q(year_of_study__lt=current_year) |
            Q(year_of_study=current_year, semester__lte=current_sem)
        )
    
    course_units = course_units.order_by('year_of_study', 'semester', 'unit__code')
    
    units_list = []
    for cu in course_units:
        # Check if student has enrolled for this unit (for current academic year)
        current_year = timezone.now().year
        current_academic_year = f"{current_year}/{current_year + 1}"
        
        enrollment = Enrollment.objects.filter(
            student=student,
            unit=cu.unit,
            semester=cu.semester,
            academic_year=current_academic_year
        ).first()
        
        units_list.append({
            'id': cu.unit.id,
            'course_unit_id': cu.id,
            'code': cu.unit.code,
            'name': cu.unit.name,
            'year_of_study': cu.year_of_study,
            'semester': cu.semester,
            'lecturer_name': cu.unit.assigned_lecturer.get_full_name() if cu.unit.assigned_lecturer else None,
            'lecturer_email': cu.unit.assigned_lecturer.email if cu.unit.assigned_lecturer else None,
            'is_enrolled': enrollment is not None,
            'enrollment_id': enrollment.id if enrollment else None,
            'exam_registered': enrollment.exam_registered if enrollment else False,
            'exam_registered_at': enrollment.exam_registered_at.isoformat() if enrollment and enrollment.exam_registered_at else None
        })
    
    return JsonResponse({
        'units': units_list,
        'count': len(units_list),
        'course_name': student.course.name if student.course else None,
        'student_year': student.year_of_study,
        'student_semester': student.current_semester or student.get_current_semester() or 1
    })


@login_required
@csrf_exempt
def api_student_results_academic_years(request, college_slug):
    """Get distinct academic years from student's enrollments that have results"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    # Get distinct academic years from enrollments that have results
    years = Enrollment.objects.filter(
        student=student
    ).filter(
        result__isnull=False
    ).values_list('academic_year', flat=True).distinct().order_by('-academic_year')
    
    years_list = list(years)
    
    # If no years exist, include current_academic_year as fallback
    if not years_list and college.current_academic_year:
        years_list = [college.current_academic_year]
    
    return JsonResponse({'academic_years': years_list})


@csrf_exempt
@require_http_methods(["GET"])
def api_student_results(request, college_slug):
    """API endpoint for student's results"""
    try:
        error_response, student, college = verify_student_access(request, college_slug)
        if error_response:
            return error_response
        
        unit_filter = request.GET.get('unit', '')
        academic_year = request.GET.get('academic_year', '')
        semester = request.GET.get('semester', '')
        
        enrollments = Enrollment.objects.filter(student=student).select_related('unit')
        
        if unit_filter:
            try:
                enrollments = enrollments.filter(unit_id=int(unit_filter))
            except ValueError:
                return JsonResponse({'error': 'Invalid unit filter'}, status=400)
        if academic_year:
            enrollments = enrollments.filter(academic_year=academic_year)
            if semester:
                try:
                    enrollments = enrollments.filter(semester=int(semester))
                except ValueError:
                    return JsonResponse({'error': 'Invalid semester filter'}, status=400)
        
        results_list = []
        for enrollment in enrollments:
            # Handle case where unit might be None (deleted unit)
            if not enrollment.unit:
                continue  # Skip enrollments with deleted units
            
            try:
                result = Result.objects.get(enrollment=enrollment)
                # Calculate grade
                grade = None
                if result.total is not None:
                    try:
                        grade = college.calculate_grade(float(result.total))
                    except Exception:
                        grade = None
                
                results_list.append({
                    'unit_code': enrollment.unit.code,
                    'unit_name': enrollment.unit.name,
                    'total': float(result.total) if result.total else None,
                    'grade': grade,
                    'academic_year': enrollment.academic_year,  # Keep for sorting
                    'semester': enrollment.semester  # Keep for sorting
                })
            except Result.DoesNotExist:
                # No result yet
                results_list.append({
                    'unit_code': enrollment.unit.code,
                    'unit_name': enrollment.unit.name,
                    'total': None,
                    'grade': None,
                    'academic_year': enrollment.academic_year,  # Keep for sorting
                    'semester': enrollment.semester  # Keep for sorting
                })
        
        # Sort by academic year and semester
        results_list.sort(key=lambda x: (x.get('academic_year', ''), x.get('semester', 0)), reverse=True)
        
        # Remove sorting fields from response (optional - frontend can ignore them)
        # for result in results_list:
        #     result.pop('academic_year', None)
        #     result.pop('semester', None)
        
        return JsonResponse({
            'results': results_list,
            'count': len(results_list)
        })
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in api_student_results: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'An error occurred while fetching results'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_student_exam_register(request, college_slug):
    """API endpoint for student exam registration
    Allows registration for current semester and previous semesters (for retakes)
    """
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    try:
        data = json.loads(request.body)
        enrollment_ids = data.get('enrollment_ids', [])
        unit_ids = data.get('unit_ids', [])  # For units not yet enrolled
        
        if not enrollment_ids and not unit_ids:
            return JsonResponse({'error': 'enrollment_ids or unit_ids array is required'}, status=400)
        
        # Get current academic year
        from django.utils import timezone
        current_year = timezone.now().year
        current_academic_year = f"{current_year}/{current_year + 1}"
        
        registered_enrollments = []
        now = timezone.now()
        
        # Process existing enrollments
        if enrollment_ids:
            # Filter enrollments: must belong to student, current or previous semesters, current academic year, and college
            # Allow current semester and previous semesters for retakes
            enrollments = Enrollment.objects.filter(
                id__in=enrollment_ids,
                student=student,
                academic_year=current_academic_year,
                unit__college=college
            )
            
            for enrollment in enrollments:
                enrollment.exam_registered = True
                enrollment.exam_registered_at = now
                enrollment.save()
                
                registered_enrollments.append({
                    'id': enrollment.id,
                    'unit_id': enrollment.unit.id,
                    'unit_code': enrollment.unit.code,
                    'unit_name': enrollment.unit.name,
                    'semester': enrollment.semester,
                    'academic_year': enrollment.academic_year,
                    'exam_registered_at': enrollment.exam_registered_at.isoformat() if enrollment.exam_registered_at else None
                })
        
        # Process new enrollments for units not yet enrolled
        if unit_ids:
            for unit_data in unit_ids:
                unit_id = unit_data.get('unit_id') if isinstance(unit_data, dict) else unit_data
                course_unit_id = unit_data.get('course_unit_id') if isinstance(unit_data, dict) else None
                
                try:
                    unit = CollegeUnit.objects.get(id=unit_id, college=college)
                    
                    # Get semester from course unit assignment
                    semester = None
                    if course_unit_id:
                        try:
                            course_unit = CollegeCourseUnit.objects.get(id=course_unit_id, course=student.course)
                            semester = course_unit.semester
                        except CollegeCourseUnit.DoesNotExist:
                            pass
                    
                    # If no semester from course unit, try to get from unit or use current semester
                    if not semester:
                        semester = unit.semester or student.get_current_semester() or 1
                    
                    # Check if enrollment already exists
                    enrollment, created = Enrollment.objects.get_or_create(
                        student=student,
                        unit=unit,
                        semester=semester,
                        academic_year=current_academic_year,
                        defaults={'exam_registered': True, 'exam_registered_at': now}
                    )
                    
                    if not created:
                        # Update existing enrollment
                        enrollment.exam_registered = True
                        enrollment.exam_registered_at = now
                        enrollment.save()
                    
                    registered_enrollments.append({
                        'id': enrollment.id,
                        'unit_id': enrollment.unit.id,
                        'unit_code': enrollment.unit.code,
                        'unit_name': enrollment.unit.name,
                        'semester': enrollment.semester,
                        'academic_year': enrollment.academic_year,
                        'exam_registered_at': enrollment.exam_registered_at.isoformat() if enrollment.exam_registered_at else None
                    })
                except CollegeUnit.DoesNotExist:
                    continue
        
        if not registered_enrollments:
            return JsonResponse({'error': 'No valid units found for registration'}, status=400)
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully registered for {len(registered_enrollments)} exam(s)',
            'enrollments': registered_enrollments,
            'count': len(registered_enrollments)
        })
    
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_student_exam_registrations(request, college_slug):
    """API endpoint for student exam registrations list"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    # Get current semester
    current_semester = student.get_current_semester()
    
    # Get current academic year
    from django.utils import timezone
    current_year = timezone.now().year
    current_academic_year = f"{current_year}/{current_year + 1}"
    
    # Get enrollments where exam_registered=True for current student and current semester
    enrollments = Enrollment.objects.filter(
        student=student,
        exam_registered=True,
        semester=current_semester,
        academic_year=current_academic_year,
        unit__college=college
    ).select_related('unit').order_by('unit__code')
    
    registrations_list = []
    for enrollment in enrollments:
        registrations_list.append({
            'id': enrollment.id,
            'unit_id': enrollment.unit.id,
            'unit_code': enrollment.unit.code,
            'unit_name': enrollment.unit.name,
            'semester': enrollment.semester,
            'academic_year': enrollment.academic_year,
            'exam_registered': enrollment.exam_registered,
            'exam_registered_at': enrollment.exam_registered_at.isoformat() if enrollment.exam_registered_at else None,
            'lecturer': enrollment.unit.assigned_lecturer.get_full_name() if enrollment.unit.assigned_lecturer else None
        })
    
    return JsonResponse({
        'registrations': registrations_list,
        'count': len(registrations_list),
        'current_semester': current_semester,
        'current_academic_year': current_academic_year
    })


# ============================================
# Timetable API Endpoints
# ============================================

@login_required
@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_timetables_list(request, college_slug):
    """API endpoint for timetables list and create - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    # Only college admins can manage timetables
    if request.method == 'POST' and not request.user.is_college_admin():
        return JsonResponse({'error': 'Only college administrators can upload timetables'}, status=403)
    
    if request.method == 'GET':
        # Get filters
        course_id = request.GET.get('course_id', '')
        timetable_type = request.GET.get('timetable_type', '')
        academic_year = request.GET.get('academic_year', '')
        semester = request.GET.get('semester', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 10)), 50)
        
        # Build query
        timetables = CollegeTimetable.objects.filter(college=college, is_active=True)
        
        if course_id:
            timetables = timetables.filter(course_id=int(course_id))
        elif timetable_type == 'general':
            timetables = timetables.filter(course__isnull=True)
        elif timetable_type == 'course_specific':
            timetables = timetables.filter(course__isnull=False)
        
        if academic_year:
            timetables = timetables.filter(academic_year=academic_year)
        if semester:
            timetables = timetables.filter(semester=int(semester))
        
        timetables = timetables.select_related('course', 'uploaded_by').order_by('-uploaded_at')
        
        # Format data
        timetables_list = []
        for tt in timetables:
            timetables_list.append({
                'id': tt.id,
                'course_id': tt.course.id if tt.course else None,
                'course_name': tt.course.name if tt.course else None,
                'timetable_type': tt.get_timetable_type(),
                'image_url': tt.image.url if tt.image else None,
                'uploaded_by': tt.uploaded_by.get_full_name() if tt.uploaded_by else 'Unknown',
                'uploaded_by_id': tt.uploaded_by.id if tt.uploaded_by else None,
                'uploaded_at': tt.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if tt.uploaded_at else None,
                'academic_year': tt.academic_year,
                'semester': tt.semester,
                'description': tt.description,
                'is_active': tt.is_active
            })
        
        # Paginate
        paginator = Paginator(timetables_list, page_size)
        page_obj = paginator.get_page(page)
        
        return JsonResponse({
            'count': paginator.count,
            'results': list(page_obj),
            'next': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'page': page_obj.number,
            'total_pages': paginator.num_pages
        })
    
    elif request.method == 'POST':
        # Create new timetable
        if 'image' not in request.FILES:
            return JsonResponse({'error': 'Image file is required'}, status=400)
        
        image_file = request.FILES['image']
        
        # Validate file type
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        if image_file.content_type not in allowed_types:
            return JsonResponse({'error': 'Invalid file type. Please upload JPG, PNG, GIF, or WebP image'}, status=400)
        
        # Validate file size (max 10MB)
        if image_file.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'File size exceeds 10MB limit'}, status=400)
        
        # Get optional fields
        course_id = request.POST.get('course_id', '').strip()
        academic_year = request.POST.get('academic_year', '').strip() or None
        semester = request.POST.get('semester', '').strip() or None
        description = request.POST.get('description', '').strip()
        
        course = None
        if course_id:
            try:
                course = CollegeCourse.objects.get(pk=int(course_id), college=college)
            except (CollegeCourse.DoesNotExist, ValueError):
                return JsonResponse({'error': 'Invalid course ID'}, status=400)
        
        if semester:
            try:
                semester = int(semester)
                max_semester = college.get_max_semester()
                if semester < 1 or semester > max_semester:
                    return JsonResponse({'error': f'Semester must be between 1 and {max_semester}'}, status=400)
            except ValueError:
                return JsonResponse({'error': 'Invalid semester value'}, status=400)
        
        # Check for duplicate
        duplicate = CollegeTimetable.objects.filter(
            college=college,
            course=course,
            academic_year=academic_year,
            semester=semester,
            is_active=True
        ).first()
        
        if duplicate:
            # Update existing instead of creating new
            duplicate.image = image_file
            duplicate.uploaded_by = request.user
            duplicate.description = description
            duplicate.save()
            timetable = duplicate
        else:
            # Create new
            timetable = CollegeTimetable.objects.create(
                college=college,
                course=course,
                image=image_file,
                uploaded_by=request.user,
                academic_year=academic_year,
                semester=semester,
                description=description
            )
        
        return JsonResponse({
            'id': timetable.id,
            'course_id': timetable.course.id if timetable.course else None,
            'course_name': timetable.course.name if timetable.course else None,
            'timetable_type': timetable.get_timetable_type(),
            'image_url': timetable.image.url if timetable.image else None,
            'uploaded_by': timetable.uploaded_by.get_full_name() if timetable.uploaded_by else 'Unknown',
            'uploaded_at': timetable.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if timetable.uploaded_at else None,
            'academic_year': timetable.academic_year,
            'semester': timetable.semester,
            'description': timetable.description,
            'message': 'Timetable uploaded successfully'
        }, status=201)


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def api_timetable_detail(request, college_slug, pk):
    """API endpoint for timetable detail, update, delete - ENFORCES COLLEGE ISOLATION"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    try:
        timetable = CollegeTimetable.objects.get(pk=pk, college=college)
    except CollegeTimetable.DoesNotExist:
        return JsonResponse({'error': 'Timetable not found'}, status=404)
    
    if request.method == 'GET':
        # Only college admins can view details in admin portal
        if not request.user.is_college_admin():
            return JsonResponse({'error': 'Only college administrators can view timetable details'}, status=403)
        
        return JsonResponse({
            'id': timetable.id,
            'course_id': timetable.course.id if timetable.course else None,
            'course_name': timetable.course.name if timetable.course else None,
            'timetable_type': timetable.get_timetable_type(),
            'image_url': timetable.image.url if timetable.image else None,
            'uploaded_by': timetable.uploaded_by.get_full_name() if timetable.uploaded_by else 'Unknown',
            'uploaded_by_id': timetable.uploaded_by.id if timetable.uploaded_by else None,
            'uploaded_at': timetable.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if timetable.uploaded_at else None,
            'academic_year': timetable.academic_year,
            'semester': timetable.semester,
            'description': timetable.description,
            'is_active': timetable.is_active
        })
    
    elif request.method == 'PUT':
        # Only college admins can update
        if not request.user.is_college_admin():
            return JsonResponse({'error': 'Only college administrators can update timetables'}, status=403)
        
        # Get fields to update
        course_id = request.POST.get('course_id', '').strip()
        academic_year = request.POST.get('academic_year', '').strip() or None
        semester = request.POST.get('semester', '').strip() or None
        description = request.POST.get('description', '').strip()
        
        # Update image if provided
        if 'image' in request.FILES:
            image_file = request.FILES['image']
            # Validate file type
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
            if image_file.content_type not in allowed_types:
                return JsonResponse({'error': 'Invalid file type. Please upload JPG, PNG, GIF, or WebP image'}, status=400)
            # Validate file size
            if image_file.size > 10 * 1024 * 1024:
                return JsonResponse({'error': 'File size exceeds 10MB limit'}, status=400)
            timetable.image = image_file
        
        # Update course
        if course_id:
            try:
                course = CollegeCourse.objects.get(pk=int(course_id), college=college)
                timetable.course = course
            except (CollegeCourse.DoesNotExist, ValueError):
                return JsonResponse({'error': 'Invalid course ID'}, status=400)
        elif course_id == '':
            timetable.course = None  # Set to general
        
        if academic_year is not None:
            timetable.academic_year = academic_year
        if semester is not None:
            try:
                semester = int(semester) if semester else None
                if semester:
                    max_semester = college.get_max_semester()
                    if semester < 1 or semester > max_semester:
                        return JsonResponse({'error': f'Semester must be between 1 and {max_semester}'}, status=400)
                timetable.semester = semester
            except ValueError:
                return JsonResponse({'error': 'Invalid semester value'}, status=400)
        
        timetable.description = description
        timetable.save()
        
        return JsonResponse({
            'id': timetable.id,
            'course_id': timetable.course.id if timetable.course else None,
            'course_name': timetable.course.name if timetable.course else None,
            'timetable_type': timetable.get_timetable_type(),
            'image_url': timetable.image.url if timetable.image else None,
            'academic_year': timetable.academic_year,
            'semester': timetable.semester,
            'description': timetable.description,
            'message': 'Timetable updated successfully'
        })
    
    elif request.method == 'DELETE':
        # Only college admins can delete
        if not request.user.is_college_admin():
            return JsonResponse({'error': 'Only college administrators can delete timetables'}, status=403)
        
        # Soft delete
        timetable.is_active = False
        timetable.save()
        
        return JsonResponse({'success': True, 'message': 'Timetable deleted successfully'}, status=200)


@csrf_exempt
@require_http_methods(["GET"])
def api_student_timetable(request, college_slug):
    """API endpoint for student's timetable - returns course-specific or general (grid or image)"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    # Get current academic year and semester from college settings (defaults)
    current_academic_year = getattr(college, 'current_academic_year', None) or None
    current_semester = getattr(college, 'current_semester', None) or None
    
    # Get optional filters (default to current if not provided)
    academic_year_param = request.GET.get('academic_year', '').strip()
    semester_param = request.GET.get('semester', '').strip()
    
    # Use provided filters, or fall back to current college settings, or None (no filter)
    academic_year = academic_year_param if academic_year_param else (current_academic_year if current_academic_year else None)
    semester_str = semester_param if semester_param else (str(current_semester) if current_semester else None)
    
    semester = None
    if semester_str:
        try:
            semester = int(semester_str)
        except (ValueError, TypeError):
            semester = None
    
    # Priority: 1. Course-specific for student's course, 2. General timetable
    timetable = None
    
    # Try to get course-specific timetable first
    if student.course:
        query = CollegeTimetable.objects.filter(
            college=college,
            course=student.course,
            is_active=True
        )
        
        if academic_year:
            query = query.filter(academic_year=academic_year)
        if semester:
            query = query.filter(semester=semester)
        
        timetable = query.order_by('-uploaded_at').first()
    
    # If no course-specific found, get general timetable
    if not timetable:
        query = CollegeTimetable.objects.filter(
            college=college,
            course__isnull=True,
            is_active=True
        )
        
        if academic_year:
            query = query.filter(academic_year=academic_year)
        if semester:
            query = query.filter(semester=semester)
        
        timetable = query.order_by('-uploaded_at').first()
    
    # Check for published TimetableRun first (structured/grid timetable)
    from timetable.models import TimetableRun, TimetableEntry
    timetable_run = None
    
    if student.course:
        query = TimetableRun.objects.filter(
            college=college,
            course=student.course,
            status='published'
        )
        if academic_year:
            query = query.filter(academic_year=academic_year)
        if semester:
            query = query.filter(semester=semester)
        timetable_run = query.order_by('-published_at').first()
    
    if not timetable_run:
        query = TimetableRun.objects.filter(
            college=college,
            course__isnull=True,
            status='published'
        )
        if academic_year:
            query = query.filter(academic_year=academic_year)
        if semester:
            query = query.filter(semester=semester)
        timetable_run = query.order_by('-published_at').first()
    
    # If structured timetable exists, return grid data
    if timetable_run:
        from timetable.views import build_timetable_table
        timetable_data = build_timetable_table(timetable_run)
        
        # Serialize for JSON
        table_rows = []
        for row in timetable_data['table_rows']:
            day_entries = []
            for entry in row['day_entries']:
                if entry:
                    day_entries.append({
                        'unit_code': entry.unit.code,
                        'unit_name': entry.unit.name,
                        'course_name': entry.course.name,
                        'lecturer_name': entry.lecturer.get_full_name() if entry.lecturer else 'TBA',
                        'classroom_name': entry.classroom.name if entry.classroom else 'TBA',
                    })
                else:
                    day_entries.append(None)
            table_rows.append({
                'time_slot_start': row['time_slot'].start_time.strftime('%H:%M'),
                'time_slot_end': row['time_slot'].end_time.strftime('%H:%M'),
                'day_entries': day_entries
            })
        
        return JsonResponse({
            'timetable_type': 'grid',
            'course_name': timetable_run.course.name if timetable_run.course else None,
            'academic_year': timetable_run.academic_year,
            'semester': timetable_run.semester,
            'days': [{'id': d.id, 'name': d.name} for d in timetable_data['days']],
            'table_rows': table_rows,
            'image_url': None,
        })
    
    if not timetable:
        return JsonResponse({
            'timetable_type': None,
            'message': 'No timetable has been published yet.'
        })
    
    return JsonResponse({
        'timetable_type': timetable.get_timetable_type(),
        'course_name': timetable.course.name if timetable.course else None,
        'image_url': timetable.get_file_url(),
        'academic_year': timetable.academic_year,
        'semester': timetable.semester,
        'description': timetable.description,
        'uploaded_at': timetable.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if timetable.uploaded_at else None
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_student_announcements(request, college_slug):
    """API endpoint for student announcements"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    from django.db.models import Q
    from django.utils import timezone
    
    # Get announcements visible to this student
    announcements = Announcement.objects.filter(
        college=college,
        is_active=True
    ).filter(
        Q(target_type='all_students') | 
        Q(target_type='individual', targeted_students=student)
    ).exclude(
        expires_at__lt=timezone.now()
    ).distinct().order_by('-priority', '-created_at')[:50]
    
    # Filter using the model's visibility method
    visible_announcements = []
    for ann in announcements:
        if ann.is_visible_to_student(student):
            visible_announcements.append(ann)
    
    announcements_list = []
    for ann in visible_announcements:
        announcements_list.append({
            'id': ann.id,
            'title': ann.title,
            'content': ann.content,
            'priority': ann.priority,
            'created_at': ann.created_at.isoformat(),
            'expires_at': ann.expires_at.isoformat() if ann.expires_at else None,
            'created_by': ann.created_by.get_full_name() if ann.created_by else None
        })
    
    return JsonResponse({
        'announcements': announcements_list,
        'count': len(announcements_list)
    })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_lecturer_announcements(request, college_slug):
    """API endpoint for lecturer/college admin announcements"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Get announcements targeted to all lecturers or this specific user
    from django.utils import timezone
    from django.db.models import Q
    
    # Filter announcements that are visible to this user
    announcements = Announcement.objects.filter(
        college=college,
        is_active=True
    ).filter(
        Q(target_type='all_lecturers') | 
        Q(targeted_users=request.user)
    ).exclude(
        expires_at__lt=timezone.now()
    ).distinct().order_by('-priority', '-created_at')[:20]
    
    # Filter using the model's visibility method
    visible_announcements = []
    for ann in announcements:
        if ann.is_visible_to_user(request.user):
            visible_announcements.append(ann)
    
    announcements_list = []
    for ann in visible_announcements:
        announcements_list.append({
            'id': ann.id,
            'title': ann.title,
            'content': ann.content,
            'priority': ann.priority,
            'created_at': ann.created_at.isoformat(),
            'expires_at': ann.expires_at.isoformat() if ann.expires_at else None,
            'created_by': ann.created_by.get_full_name() if ann.created_by else None
        })
    
    return JsonResponse({
        'announcements': announcements_list,
        'count': len(announcements_list)
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_student_new_announcements_count(request, college_slug):
    """API endpoint for student new announcements count"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    from django.db.models import Q
    from django.utils import timezone
    from datetime import timedelta
    
    # Get announcements from last 7 days
    seven_days_ago = timezone.now() - timedelta(days=7)
    
    announcements = Announcement.objects.filter(
        college=college,
        is_active=True,
        created_at__gte=seven_days_ago
    ).filter(
        Q(target_type='all_students') | 
        Q(target_type='individual', targeted_students=student)
    ).exclude(
        expires_at__lt=timezone.now()
    ).distinct()
    
    # Filter using the model's visibility method
    visible_count = 0
    for ann in announcements:
        if ann.is_visible_to_student(student):
            visible_count += 1
    
    return JsonResponse({
        'new_count': visible_count
    })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_lecturer_new_announcements_count(request, college_slug):
    """API endpoint for lecturer/college admin new announcements count"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    from django.db.models import Q
    from django.utils import timezone
    from datetime import timedelta
    
    # Get announcements from last 7 days
    seven_days_ago = timezone.now() - timedelta(days=7)
    
    announcements = Announcement.objects.filter(
        college=college,
        is_active=True,
        created_at__gte=seven_days_ago
    ).filter(
        Q(target_type='all_lecturers') | 
        Q(targeted_users=request.user)
    ).exclude(
        expires_at__lt=timezone.now()
    ).distinct()
    
    # Filter using the model's visibility method
    visible_count = 0
    for ann in announcements:
        if ann.is_visible_to_user(request.user):
            visible_count += 1
    
    return JsonResponse({
        'new_count': visible_count
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_student_fees(request, college_slug):
    """API endpoint for student fees - shows expected fees up to current semester, payments, and balance"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    # Calculate expected fees up to current semester
    fee_info = calculate_expected_fees(student)
    expected_total = fee_info['expected_total']
    current_semester = fee_info['current_semester']
    fee_breakdown = fee_info['fee_breakdown']
    
    # Get all payments for this student
    payments = Payment.objects.filter(student=student).order_by('-date_paid')
    total_payments = payments.aggregate(
        total=Sum('amount_paid')
    )['total'] or Decimal('0.00')
    
    # Calculate outstanding balance
    outstanding = expected_total - total_payments
    
    # Format payment history
    payment_history = [
        {
            'id': p.id,
            'amount': float(p.amount_paid),
            'method': p.get_payment_method_display(),
            'date': p.date_paid.strftime('%Y-%m-%d'),
            'receipt_number': p.receipt_number or 'N/A',
            'notes': p.notes or ''
        }
        for p in payments[:20]  # Last 20 payments
    ]
    
    # Format fee breakdown by semester
    semester_breakdown = []
    for sem_num in sorted(fee_breakdown.keys()):
        sem_data = fee_breakdown[sem_num]
        semester_breakdown.append({
            'semester': sem_num,
            'total': float(sem_data['total']),
            'fees': sem_data['fees']
        })
    
    # Get bank account details if bank transfers are enabled
    bank_details = None
    try:
        from accounts.models import DarajaSettings
        daraja_settings = DarajaSettings.objects.filter(college=college, bank_transfers_enabled=True).first()
        if daraja_settings:
            bank_details = {
                'bank_name': daraja_settings.bank_name or '',
                'account_name': daraja_settings.bank_account_name or '',
                'account_number': daraja_settings.bank_account_number or '',
                'branch': daraja_settings.bank_branch or '',
                'swift_code': daraja_settings.bank_swift_code or '',
                'instructions': daraja_settings.bank_transfer_instructions or ''
            }
    except (ImportError, AttributeError):
        # Bank details are optional, continue without them
        pass
    
    return JsonResponse({
        'expected_total': float(expected_total),
        'total_paid': float(total_payments),
        'outstanding': float(outstanding),
        'current_semester': current_semester,
        'semester_breakdown': semester_breakdown,
        'payment_history': payment_history,
        'has_course': student.course is not None,
        'bank_details': bank_details
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_student_initiate_mpesa_payment(request, college_slug):
    """API endpoint for student to initiate M-Pesa payment via Daraja STK Push"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    try:
        data = json.loads(request.body)
        amount = Decimal(str(data.get('amount', 0)))
        phone_number = data.get('phone_number', '').strip()
        invoice_id = data.get('invoice_id')
        
        # Validate amount
        if amount <= 0:
            return JsonResponse({
                'success': False,
                'error': 'Invalid payment amount'
            }, status=400)
        
        # Validate phone number
        if not phone_number:
            return JsonResponse({
                'success': False,
                'error': 'Phone number is required'
            }, status=400)
        
        # Check if Daraja is configured
        from accounts.models import DarajaSettings
        try:
            daraja_settings = DarajaSettings.objects.get(college=college, is_active=True)
        except DarajaSettings.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'M-Pesa payments are not configured for this college'
            }, status=400)
        
        # Get invoice if provided
        invoice = None
        if invoice_id:
            from accounts.models import StudentInvoice
            try:
                invoice = StudentInvoice.objects.get(id=invoice_id, student=student)
            except StudentInvoice.DoesNotExist:
                pass
        
        # Initiate STK Push
        from accounts.daraja_service import DarajaService
        try:
            daraja_service = DarajaService(college)
            result = daraja_service.initiate_stk_push(
                student=student,
                amount=amount,
                phone_number=phone_number,
                invoice=invoice
            )
            
            if result.get('success'):
                return JsonResponse({
                    'success': True,
                    'message': result.get('response_description', 'Payment request sent successfully'),
                    'merchant_request_id': result.get('merchant_request_id'),
                    'checkout_request_id': result.get('checkout_request_id')
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': result.get('error', 'Failed to initiate payment')
                }, status=400)
                
        except ValueError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Payment initiation failed: {str(e)}'
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["PUT"])
def api_student_change_password(request, college_slug):
    """API endpoint for student to change password"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    
    if not new_password:
        return JsonResponse({'error': 'New password is required'}, status=400)
    
    # If student has a password, verify current password
    if student.has_usable_password():
        if not current_password:
            return JsonResponse({'error': 'Current password is required'}, status=400)
        if not student.check_password(current_password):
            return JsonResponse({'error': 'Current password is incorrect'}, status=400)
    
    # Set new password
    student.set_password(new_password)
    
    return JsonResponse({
        'success': True,
        'message': 'Password changed successfully'
    })


# ============================================
# Course-Unit Assignment API Endpoints
# ============================================

@login_required
@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_courseunits_list(request, college_slug):
    """API endpoint for course-unit assignments list, create, update, delete"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        # Get filters
        course_id = request.GET.get('course', '')
        year = request.GET.get('year', '')
        semester = request.GET.get('semester', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 10)), 50)
        
        # Build query
        courseunits = CollegeCourseUnit.objects.filter(college=college)
        
        if course_id:
            courseunits = courseunits.filter(course_id=int(course_id))
        if year:
            courseunits = courseunits.filter(year_of_study=int(year))
        if semester:
            courseunits = courseunits.filter(semester=int(semester))
        
        courseunits = courseunits.select_related('course', 'unit', 'unit__assigned_lecturer').order_by('course', 'year_of_study', 'semester', 'unit__code')
        
        # Format data
        courseunits_list = []
        for cu in courseunits:
            courseunits_list.append({
                'id': cu.id,
                'course_id': cu.course.id,
                'course_name': cu.course.name,
                'unit_id': cu.unit.id,
                'unit_code': cu.unit.code,
                'unit_name': cu.unit.name,
                'year_of_study': cu.year_of_study,
                'semester': cu.semester,
                'lecturer_id': cu.unit.assigned_lecturer.id if cu.unit.assigned_lecturer else None,
                'lecturer_name': cu.unit.assigned_lecturer.get_full_name() if cu.unit.assigned_lecturer else None,
                'created_at': cu.created_at.strftime('%Y-%m-%d') if cu.created_at else None
            })
        
        # Paginate
        paginator = Paginator(courseunits_list, page_size)
        page_obj = paginator.get_page(page)
        
        return JsonResponse({
            'count': paginator.count,
            'results': list(page_obj),
            'next': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'page': page_obj.number,
            'total_pages': paginator.num_pages
        })
    
    elif request.method == 'POST':
        # Create new assignment
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Validate required fields
        required_fields = ['course_id', 'unit_id', 'year_of_study', 'semester']
        for field in required_fields:
            if field not in data:
                return JsonResponse({'error': f'{field} is required'}, status=400)
        
        try:
            course = CollegeCourse.objects.get(pk=data['course_id'], college=college)
            unit = CollegeUnit.objects.get(pk=data['unit_id'], college=college)
        except (CollegeCourse.DoesNotExist, CollegeUnit.DoesNotExist):
            return JsonResponse({'error': 'Course or unit not found'}, status=404)
        
        # Validate year doesn't exceed course duration
        if data['year_of_study'] > course.duration_years:
            return JsonResponse({
                'error': f'Year of study ({data["year_of_study"]}) cannot exceed course duration ({course.duration_years} years)'
            }, status=400)
        
        # Validate semester
        if data['semester'] < 1 or data['semester'] > 4:
            return JsonResponse({'error': 'Semester must be between 1 and 4'}, status=400)
        
        # Check if assignment already exists
        if CollegeCourseUnit.objects.filter(
            course=course,
            unit=unit,
            year_of_study=data['year_of_study'],
            semester=data['semester']
        ).exists():
            return JsonResponse({'error': 'This unit is already assigned to this course for the specified year and semester'}, status=400)
        
        # Create assignment
        courseunit = CollegeCourseUnit.objects.create(
            course=course,
            unit=unit,
            year_of_study=data['year_of_study'],
            semester=data['semester'],
            college=college
        )
        
        return JsonResponse({
            'id': courseunit.id,
            'course_id': courseunit.course.id,
            'course_name': courseunit.course.name,
            'unit_id': courseunit.unit.id,
            'unit_code': courseunit.unit.code,
            'unit_name': courseunit.unit.name,
            'year_of_study': courseunit.year_of_study,
            'semester': courseunit.semester,
            'lecturer_id': courseunit.unit.assigned_lecturer.id if courseunit.unit.assigned_lecturer else None,
            'lecturer_name': courseunit.unit.assigned_lecturer.get_full_name() if courseunit.unit.assigned_lecturer else None
        }, status=201)
    
    elif request.method in ['PUT', 'PATCH']:
        # Update assignment
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        courseunit_id = data.get('id')
        
        if not courseunit_id:
            return JsonResponse({'error': 'ID is required for update'}, status=400)
        
        try:
            courseunit = CollegeCourseUnit.objects.get(pk=courseunit_id, college=college)
        except CollegeCourseUnit.DoesNotExist:
            return JsonResponse({'error': 'Assignment not found'}, status=404)
        
        # Update fields
        if 'year_of_study' in data:
            if data['year_of_study'] > courseunit.course.duration_years:
                return JsonResponse({
                    'error': f'Year of study ({data["year_of_study"]}) cannot exceed course duration ({courseunit.course.duration_years} years)'
                }, status=400)
            courseunit.year_of_study = data['year_of_study']
        
        if 'semester' in data:
            if data['semester'] < 1 or data['semester'] > 4:
                return JsonResponse({'error': 'Semester must be between 1 and 4'}, status=400)
            courseunit.semester = data['semester']
        
        if 'unit_id' in data:
            try:
                unit = CollegeUnit.objects.get(pk=data['unit_id'], college=college)
                courseunit.unit = unit
            except CollegeUnit.DoesNotExist:
                return JsonResponse({'error': 'Unit not found'}, status=404)
        
        # Check for duplicate if changing key fields
        if 'year_of_study' in data or 'semester' in data or 'unit_id' in data:
            if CollegeCourseUnit.objects.filter(
                course=courseunit.course,
                unit=courseunit.unit,
                year_of_study=courseunit.year_of_study,
                semester=courseunit.semester
            ).exclude(pk=courseunit.id).exists():
                return JsonResponse({'error': 'This assignment already exists'}, status=400)
        
        courseunit.save()
        
        return JsonResponse({
            'id': courseunit.id,
            'course_id': courseunit.course.id,
            'course_name': courseunit.course.name,
            'unit_id': courseunit.unit.id,
            'unit_code': courseunit.unit.code,
            'unit_name': courseunit.unit.name,
            'year_of_study': courseunit.year_of_study,
            'semester': courseunit.semester,
            'lecturer_id': courseunit.unit.assigned_lecturer.id if courseunit.unit.assigned_lecturer else None,
            'lecturer_name': courseunit.unit.assigned_lecturer.get_full_name() if courseunit.unit.assigned_lecturer else None
        })
    
    elif request.method == 'DELETE':
        # Delete assignment
        data = json.loads(request.body) if request.body else {}
        courseunit_id = data.get('id')
        
        if not courseunit_id:
            return JsonResponse({'error': 'ID is required for deletion'}, status=400)
        
        try:
            courseunit = CollegeCourseUnit.objects.get(pk=courseunit_id, college=college)
            courseunit.delete()
            return JsonResponse({'success': True}, status=204)
        except CollegeCourseUnit.DoesNotExist:
            return JsonResponse({'error': 'Assignment not found'}, status=404)


# ============================================
# Announcements API Endpoints
# ============================================

@login_required
@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_announcements_list(request, college_slug):
    """API endpoint for listing and creating announcements"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))
        search = request.GET.get('search', '')
        target_type = request.GET.get('target_type', '')
        priority = request.GET.get('priority', '')
        is_active = request.GET.get('is_active', '')
        
        announcements = Announcement.objects.filter(college=college)
        
        if search:
            announcements = announcements.filter(
                Q(title__icontains=search) | Q(content__icontains=search)
            )
        
        if target_type:
            announcements = announcements.filter(target_type=target_type)
        
        if priority:
            announcements = announcements.filter(priority=priority)
        
        if is_active != '':
            announcements = announcements.filter(is_active=is_active.lower() == 'true')
        
        announcements = announcements.order_by('-created_at')
        
        paginator = Paginator(announcements, page_size)
        page_obj = paginator.get_page(page)
        
        results = []
        for ann in page_obj:
            results.append({
                'id': ann.id,
                'title': ann.title,
                'content': ann.content,
                'target_type': ann.target_type,
                'priority': ann.priority,
                'created_by': ann.created_by.get_full_name() if ann.created_by else 'Unknown',
                'created_at': ann.created_at.isoformat(),
                'updated_at': ann.updated_at.isoformat(),
                'is_active': ann.is_active,
                'expires_at': ann.expires_at.isoformat() if ann.expires_at else None,
                'is_expired': ann.expires_at and ann.expires_at < timezone.now() if ann.expires_at else False,
                'targeted_students': list(ann.targeted_students.values_list('id', flat=True)),
                'targeted_users': list(ann.targeted_users.values_list('id', flat=True)),
            })
        
        return JsonResponse({
            'count': paginator.count,
            'results': results,
            'page': page_obj.number,
            'total_pages': paginator.num_pages,
            'next': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
        })
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        expires_at = None
        if data.get('expires_at'):
            try:
                expires_at = timezone.datetime.fromisoformat(data.get('expires_at').replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                expires_at = None
        
        announcement = Announcement.objects.create(
            college=college,
            title=data.get('title', ''),
            content=data.get('content', ''),
            target_type=data.get('target_type', 'all_students'),
            priority=data.get('priority', 'normal'),
            created_by=request.user,
            is_active=True,
            expires_at=expires_at
        )
        
        # Handle individual targeting
        if data.get('target_type') == 'individual':
            if data.get('targeted_students'):
                announcement.targeted_students.set(data.get('targeted_students', []))
            if data.get('targeted_users'):
                announcement.targeted_users.set(data.get('targeted_users', []))
        
        return JsonResponse({
            'id': announcement.id,
            'title': announcement.title,
            'content': announcement.content,
            'target_type': announcement.target_type,
            'priority': announcement.priority,
            'created_by': announcement.created_by.get_full_name() if announcement.created_by else 'Unknown',
            'created_at': announcement.created_at.isoformat(),
            'is_active': announcement.is_active,
        }, status=201)


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def api_announcement_detail(request, college_slug, pk):
    """API endpoint for announcement detail, update, delete"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    try:
        announcement = Announcement.objects.get(pk=pk, college=college)
    except Announcement.DoesNotExist:
        return JsonResponse({'error': 'Announcement not found'}, status=404)
    
    if request.method == 'GET':
        return JsonResponse({
            'id': announcement.id,
            'title': announcement.title,
            'content': announcement.content,
            'target_type': announcement.target_type,
            'priority': announcement.priority,
            'created_by': announcement.created_by.get_full_name() if announcement.created_by else 'Unknown',
            'created_at': announcement.created_at.isoformat(),
            'updated_at': announcement.updated_at.isoformat(),
            'is_active': announcement.is_active,
            'expires_at': announcement.expires_at.isoformat() if announcement.expires_at else None,
            'is_expired': announcement.expires_at and announcement.expires_at < timezone.now() if announcement.expires_at else False,
            'targeted_students': list(announcement.targeted_students.values_list('id', flat=True)),
            'targeted_users': list(announcement.targeted_users.values_list('id', flat=True)),
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        announcement.title = data.get('title', announcement.title)
        announcement.content = data.get('content', announcement.content)
        announcement.target_type = data.get('target_type', announcement.target_type)
        announcement.priority = data.get('priority', announcement.priority)
        announcement.is_active = data.get('is_active', announcement.is_active)
        
        if data.get('expires_at'):
            try:
                announcement.expires_at = timezone.datetime.fromisoformat(data.get('expires_at').replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
        elif 'expires_at' in data and data.get('expires_at') is None:
            announcement.expires_at = None
        
        announcement.save()
        
        # Update individual targeting
        if data.get('target_type') == 'individual':
            if 'targeted_students' in data:
                announcement.targeted_students.set(data.get('targeted_students', []))
            if 'targeted_users' in data:
                announcement.targeted_users.set(data.get('targeted_users', []))
        else:
            announcement.targeted_students.clear()
            announcement.targeted_users.clear()
        
        return JsonResponse({
            'id': announcement.id,
            'title': announcement.title,
            'content': announcement.content,
            'target_type': announcement.target_type,
            'priority': announcement.priority,
            'created_by': announcement.created_by.get_full_name() if announcement.created_by else 'Unknown',
            'created_at': announcement.created_at.isoformat(),
            'is_active': announcement.is_active,
        })
    
    elif request.method == 'DELETE':
        announcement.is_active = False
        announcement.save()
        return JsonResponse({'success': True}, status=204)


# ============================================
# Semester Nominal Roll Sign-In API Endpoints
# ============================================

@csrf_exempt
@require_http_methods(["POST"])
def api_student_semester_signin(request, college_slug):
    """API endpoint for student to sign in for semester"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    # Check if feature is enabled
    if not college.can_students_sign_in():
        return JsonResponse({
            'success': False,
            'error': 'Semester sign-in is currently disabled. Please contact your college administration.'
        }, status=403)
    
    # Get current academic year and semester from college settings
    academic_year = college.current_academic_year
    semester = college.current_semester
    
    if not academic_year or not semester:
        return JsonResponse({
            'success': False,
            'error': 'Academic year or semester not configured. Please contact your college administration.'
        }, status=400)
    
    # Process sign-in
    success, message, signin_record = student.sign_in_to_semester(academic_year, semester)
    
    if success:
        return JsonResponse({
            'success': True,
            'message': message,
            'signin': {
                'id': signin_record.id,
                'academic_year': signin_record.academic_year,
                'semester': signin_record.semester,
                'signed_in_at': signin_record.signed_in_at.isoformat(),
                'year_of_study_at_signin': signin_record.year_of_study_at_signin,
                'next_year_of_study': signin_record.next_year_of_study,
                'next_semester': signin_record.next_semester
            },
            'student': {
                'year_of_study': student.year_of_study,
                'current_semester': student.current_semester
            }
        }, status=201)
    else:
        return JsonResponse({
            'success': False,
            'error': message
        }, status=400)


@csrf_exempt
@require_http_methods(["GET"])
def api_student_signin_status(request, college_slug):
    """API endpoint to get student's current sign-in status"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    # Check if feature is enabled
    feature_enabled = college.can_students_sign_in()
    current_academic_year = college.current_academic_year
    current_semester = college.current_semester
    
    # Check if student has signed in for current semester
    has_signed_in = False
    signin_record = None
    if feature_enabled and current_academic_year and current_semester:
        has_signed_in = student.has_signed_in_for_semester(current_academic_year, current_semester)
        if has_signed_in:
            signin_record = StudentSemesterSignIn.objects.filter(
                student=student,
                academic_year=current_academic_year,
                semester=current_semester
            ).first()
    
    return JsonResponse({
        'feature_enabled': feature_enabled,
        'current_academic_year': current_academic_year,
        'current_semester': current_semester,
        'has_signed_in': has_signed_in,
        'can_sign_in': feature_enabled and not has_signed_in and student.is_active(),
        'signin': {
            'id': signin_record.id,
            'signed_in_at': signin_record.signed_in_at.isoformat(),
            'year_of_study_at_signin': signin_record.year_of_study_at_signin,
            'next_year_of_study': signin_record.next_year_of_study,
            'next_semester': signin_record.next_semester
        } if signin_record else None,
        'student': {
            'year_of_study': student.year_of_study,
            'current_semester': student.current_semester,
            'last_signin_date': student.last_signin_date.isoformat() if student.last_signin_date else None,
            'last_signin_academic_year': student.last_signin_academic_year
        }
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_student_academic_settings(request, college_slug):
    """API endpoint for students to get academic settings (read-only)"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    return JsonResponse({
        'semesters_per_year': college.semesters_per_year,
        'current_academic_year': college.current_academic_year,
        'current_semester': college.current_semester,
        'semester_choices': college.get_semester_choices()
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_student_signin_history(request, college_slug):
    """API endpoint to get student's sign-in history"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    # Get sign-in history
    signins = StudentSemesterSignIn.objects.filter(student=student).order_by('-signed_in_at')
    
    signin_list = []
    for signin in signins:
        signin_list.append({
            'id': signin.id,
            'academic_year': signin.academic_year,
            'semester': signin.semester,
            'signed_in_at': signin.signed_in_at.isoformat(),
            'year_of_study_at_signin': signin.year_of_study_at_signin,
            'semester_of_study_at_signin': signin.semester_of_study_at_signin,
            'next_year_of_study': signin.next_year_of_study,
            'next_semester': signin.next_semester,
            'is_processed': signin.is_processed,
            'processed_at': signin.processed_at.isoformat() if signin.processed_at else None
        })
    
    return JsonResponse({
        'signins': signin_list,
        'count': len(signin_list)
    })


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT"])
def api_admin_academic_settings(request, college_slug):
    """API endpoint for admin to get/update academic settings"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        return JsonResponse({
            'semesters_per_year': college.semesters_per_year,
            'current_academic_year': college.current_academic_year,
            'current_semester': college.current_semester,
            'semester_choices': college.get_semester_choices()
        })
    
    elif request.method == 'PUT':
        # Only college admins can update settings
        if not request.user.is_college_admin():
            return JsonResponse({'error': 'Only college administrators can update academic settings'}, status=403)
        
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Update semesters_per_year
        if 'semesters_per_year' in data:
            try:
                semesters = int(data['semesters_per_year'])
                if semesters < 1 or semesters > 12:
                    return JsonResponse({'error': 'Semesters per year must be between 1 and 12'}, status=400)
                
                # Validate that current_semester doesn't exceed new max
                if college.current_semester and college.current_semester > semesters:
                    return JsonResponse({
                        'error': f'Cannot reduce semesters per year. Current semester ({college.current_semester}) exceeds new maximum ({semesters})'
                    }, status=400)
                
                college.semesters_per_year = semesters
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid semesters_per_year value'}, status=400)
        
        # Update current_academic_year
        if 'current_academic_year' in data:
            academic_year = data['current_academic_year'].strip() if data['current_academic_year'] else None
            if academic_year and not re.match(r'^\d{4}/\d{4}$', academic_year):
                return JsonResponse({'error': 'Academic year must be in format YYYY/YYYY (e.g., 2024/2025)'}, status=400)
            college.current_academic_year = academic_year
        
        # Update current_semester
        if 'current_semester' in data:
            semester = data['current_semester']
            if semester:
                try:
                    semester = int(semester)
                    max_semester = college.semesters_per_year
                    if semester < 1 or semester > max_semester:
                        return JsonResponse({'error': f'Semester must be between 1 and {max_semester}'}, status=400)
                    college.current_semester = semester
                except (ValueError, TypeError):
                    return JsonResponse({'error': 'Invalid semester value'}, status=400)
            else:
                college.current_semester = None
        
        college.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Academic settings updated successfully',
            'settings': {
                'semesters_per_year': college.semesters_per_year,
                'current_academic_year': college.current_academic_year,
                'current_semester': college.current_semester,
                'semester_choices': college.get_semester_choices()
            }
        })


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT"])
def api_admin_grading_system(request, college_slug):
    """API endpoint for admin to get/update grading system settings"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    if request.method == 'GET':
        # Allow lecturers to read grading criteria (needed for marks entry)
        criteria = college.get_grading_criteria()
        return JsonResponse({
            'grading_criteria': criteria
        })
    
    elif request.method == 'PUT':
        # Only college admins can update settings
        if not request.user.is_college_admin():
            return JsonResponse({'error': 'Only college admins can update grading system'}, status=403)
        
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Validate and update grading criteria
        cat_weight = data.get('cat_weight', 30.0)
        exam_weight = data.get('exam_weight', 70.0)
        pass_mark = data.get('pass_mark', 40.0)
        grades = data.get('grades', {})
        
        # Validate weights sum to 100
        total_weight = cat_weight + exam_weight
        if abs(total_weight - 100.0) > 0.01:  # Allow small floating point differences
            return JsonResponse({'error': f'CAT and Exam weights must sum to 100% (current: {total_weight}%)'}, status=400)
        
        # Validate weights are positive
        if cat_weight < 0 or exam_weight < 0:
            return JsonResponse({'error': 'Weights must be positive'}, status=400)
        
        # Validate pass mark
        if pass_mark < 0 or pass_mark > 100:
            return JsonResponse({'error': 'Pass mark must be between 0 and 100'}, status=400)
        
        # Validate grades structure
        if not isinstance(grades, dict):
            return JsonResponse({'error': 'Grades must be a dictionary'}, status=400)
        
        # Validate each grade has min and max
        for grade_name, grade_data in grades.items():
            if not isinstance(grade_data, dict) or 'min' not in grade_data or 'max' not in grade_data:
                return JsonResponse({'error': f'Grade {grade_name} must have min and max values'}, status=400)
            if grade_data['min'] < 0 or grade_data['max'] > 100:
                return JsonResponse({'error': f'Grade {grade_name} min/max must be between 0 and 100'}, status=400)
            if grade_data['min'] > grade_data['max']:
                return JsonResponse({'error': f'Grade {grade_name} min cannot be greater than max'}, status=400)
        
        # Check for overlapping ranges (basic check)
        sorted_grades = sorted(grades.items(), key=lambda x: x[1]['min'])
        for i in range(len(sorted_grades) - 1):
            current_max = sorted_grades[i][1]['max']
            next_min = sorted_grades[i + 1][1]['min']
            if current_max >= next_min:
                return JsonResponse({
                    'error': f'Grade ranges overlap: {sorted_grades[i][0]} and {sorted_grades[i + 1][0]}'
                }, status=400)
        
        # Update grading criteria
        college.grading_criteria = {
            'cat_weight': float(cat_weight),
            'exam_weight': float(exam_weight),
            'pass_mark': float(pass_mark),
            'grades': grades
        }
        college.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Grading system updated successfully',
            'grading_criteria': college.grading_criteria
        })


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT"])
def api_admin_nominal_roll_settings(request, college_slug):
    """API endpoint for admin to get/update nominal roll sign-in settings"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Only college admins can manage settings
    if not request.user.is_college_admin():
        return JsonResponse({'error': 'Only college administrators can manage nominal roll settings'}, status=403)
    
    if request.method == 'GET':
        # Include academic settings and stats in the response for combined loading
        include_stats = request.GET.get('include_stats', 'false').lower() == 'true'
        
        response_data = {
            'nominal_roll_signin_enabled': college.nominal_roll_signin_enabled,
            'can_students_sign_in': college.can_students_sign_in(),
            'current_semester': college.current_semester,
            # Include academic settings
            'academic_settings': {
                'semesters_per_year': college.semesters_per_year,
                'current_academic_year': college.current_academic_year,
                'current_semester': college.current_semester,
                'semester_choices': college.get_semester_choices()
            }
        }
        
        # Include stats if requested and nominal roll is enabled
        if include_stats and college.nominal_roll_signin_enabled:
            academic_year = college.current_academic_year
            semester = college.current_semester
            
            if academic_year and semester:
                # Get total active students
                total_students = Student.objects.filter(college=college, status='active').count()
                
                # Get signed-in students for current semester
                signed_in_count = StudentSemesterSignIn.objects.filter(
                    student__college=college,
                    academic_year=academic_year,
                    semester=semester
                ).count()
                
                not_signed_in_count = total_students - signed_in_count
                signin_percentage = (signed_in_count / total_students * 100) if total_students > 0 else 0
                
                response_data['stats'] = {
                    'total_students': total_students,
                    'signed_in_count': signed_in_count,
                    'not_signed_in_count': not_signed_in_count,
                    'signin_percentage': round(signin_percentage, 2)
                }
            else:
                response_data['stats'] = {
                    'total_students': 0,
                    'signed_in_count': 0,
                    'not_signed_in_count': 0,
                    'signin_percentage': 0,
                    'message': 'Academic year or semester not configured'
                }
        
        return JsonResponse(response_data)
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Update settings
        if 'nominal_roll_signin_enabled' in data:
            college.nominal_roll_signin_enabled = data['nominal_roll_signin_enabled']
        
        college.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Settings updated successfully',
            'settings': {
                'nominal_roll_signin_enabled': college.nominal_roll_signin_enabled,
                'can_students_sign_in': college.can_students_sign_in()
            }
        })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_admin_nominal_roll_list(request, college_slug):
    """API endpoint for admin to get list of signed-in students"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Only college admins can view
    if not request.user.is_college_admin():
        return JsonResponse({'error': 'Only college administrators can view nominal roll'}, status=403)
    
    # Get filters
    academic_year = request.GET.get('academic_year', '').strip() or college.current_academic_year
    semester = request.GET.get('semester', '').strip()
    course_id = request.GET.get('course_id', '').strip()
    year_of_study = request.GET.get('year_of_study', '').strip()
    page = int(request.GET.get('page', 1))
    page_size = min(int(request.GET.get('page_size', 20)), 100)
    
    if semester:
        try:
            semester = int(semester)
        except ValueError:
            semester = None
    else:
        semester = college.current_semester
    
    # Build query
    signins = StudentSemesterSignIn.objects.filter(
        student__college=college
    ).select_related('student', 'student__course')
    
    if academic_year:
        signins = signins.filter(academic_year=academic_year)
    if semester:
        signins = signins.filter(semester=semester)
    if course_id:
        signins = signins.filter(student__course_id=int(course_id))
    if year_of_study:
        signins = signins.filter(year_of_study_at_signin=int(year_of_study))
    
    signins = signins.order_by('-signed_in_at')
    
    # Format data
    signin_list = []
    for signin in signins:
        signin_list.append({
            'id': signin.id,
            'student_id': signin.student.id,
            'admission_number': signin.student.admission_number,
            'full_name': signin.student.full_name,
            'course_id': signin.student.course.id if signin.student.course else None,
            'course_name': signin.student.course.name if signin.student.course else None,
            'academic_year': signin.academic_year,
            'semester': signin.semester,
            'signed_in_at': signin.signed_in_at.isoformat(),
            'year_of_study_at_signin': signin.year_of_study_at_signin,
            'next_year_of_study': signin.next_year_of_study,
            'next_semester': signin.next_semester,
            'is_processed': signin.is_processed
        })
    
    # Paginate
    paginator = Paginator(signin_list, page_size)
    page_obj = paginator.get_page(page)
    
    return JsonResponse({
        'count': paginator.count,
        'results': list(page_obj),
        'next': page_obj.next_page_number() if page_obj.has_next() else None,
        'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
        'page': page_obj.number,
        'total_pages': paginator.num_pages
    })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_admin_nominal_roll_filters(request, college_slug):
    """API endpoint for admin to get all filter data for nominal roll (academic years, courses, semester data)"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Only college admins can view
    if not request.user.is_college_admin():
        return JsonResponse({'error': 'Only college administrators can view filters'}, status=403)
    
    # Get academic years from enrollments
    years = Enrollment.objects.filter(
        unit__college=college
    ).values_list('academic_year', flat=True).distinct().order_by('-academic_year')
    
    years_list = list(years)
    
    # If no years exist, include current_academic_year as fallback
    if not years_list and college.current_academic_year:
        years_list = [college.current_academic_year]
    
    # Get courses
    courses = CollegeCourse.objects.filter(college=college)
    courses_list = []
    for course in courses:
        courses_list.append({
            'id': course.id,
            'name': course.name,
            'code': getattr(course, 'code', f'COURSE{course.id}'),
        })
    
    return JsonResponse({
        'academic_years': years_list,
        'courses': courses_list,
        'semester_data': {
            'semesters_per_year': college.semesters_per_year,
            'current_semester': college.current_semester,
            'semester_choices': college.get_semester_choices()
        }
    })


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT"])
def api_admin_profile(request, college_slug):
    """API endpoint for admin/lecturer profile management"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    user = request.user
    
    if request.method == 'GET':
        return JsonResponse({
            'id': user.id,
            'username': user.username,
            'email': user.email or '',
            'phone': user.phone or '',
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'role': user.role,
            'is_college_admin': user.is_college_admin()
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Allow updating email, phone, first_name, last_name
        if 'email' in data:
            user.email = data['email']
        if 'phone' in data:
            user.phone = data['phone']
        if 'first_name' in data:
            user.first_name = data['first_name']
        if 'last_name' in data:
            user.last_name = data['last_name']
        
        # Handle password change if provided
        if 'password' in data and data['password']:
            user.set_password(data['password'])
        
        user.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Profile updated successfully',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email or '',
                'phone': user.phone or '',
                'first_name': user.first_name or '',
                'last_name': user.last_name or ''
            }
        })


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT"])
def api_college_info(request, college_slug):
    """API endpoint for college information - GET and UPDATE"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    # Verify user has access to this college
    verify_user_college_access(request, college)
    
    # Only college admins can update
    if request.method == 'PUT' and not request.user.is_college_admin():
        return JsonResponse({'error': 'Only college administrators can update college information'}, status=403)
    
    if request.method == 'GET':
        return JsonResponse({
            'id': college.id,
            'name': college.name,
            'address': college.address,
            'county': college.county,
            'email': college.email,
            'phone': college.phone,
            'principal_name': college.principal_name,
            'registration_status': college.registration_status,
            'created_at': college.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': college.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            
            # Validate required fields
            required_fields = ['name', 'address', 'county', 'email', 'phone', 'principal_name']
            for field in required_fields:
                if field not in data or not data[field]:
                    return JsonResponse({'error': f'{field.replace("_", " ").title()} is required'}, status=400)
            
            # Check if email is being changed and if it's already taken
            if data.get('email') != college.email:
                if College.objects.filter(email=data['email']).exclude(id=college.id).exists():
                    return JsonResponse({'error': 'Email address is already registered to another college'}, status=400)
            
            # Update college fields
            college.name = data['name']
            college.address = data['address']
            college.county = data['county']
            college.email = data['email']
            college.phone = data['phone']
            college.principal_name = data['principal_name']
            
            # Note: registration_status is intentionally not updatable via this endpoint
            # It should only be changed by super admin
            
            college.save()
            
            return JsonResponse({
                'id': college.id,
                'name': college.name,
                'address': college.address,
                'county': college.county,
                'email': college.email,
                'phone': college.phone,
                'principal_name': college.principal_name,
                'registration_status': college.registration_status,
                'message': 'College information updated successfully'
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_admin_nominal_roll_stats(request, college_slug):
    """API endpoint for admin to get nominal roll statistics"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Only college admins can view
    if not request.user.is_college_admin():
        return JsonResponse({'error': 'Only college administrators can view statistics'}, status=403)
    
    # Get current academic year and semester
    academic_year = request.GET.get('academic_year', '').strip() or college.current_academic_year
    semester = request.GET.get('semester', '').strip()
    
    if semester:
        try:
            semester = int(semester)
        except ValueError:
            semester = None
    else:
        semester = college.current_semester
    
    if not academic_year or not semester:
        return JsonResponse({
            'total_students': 0,
            'signed_in_count': 0,
            'not_signed_in_count': 0,
            'signin_percentage': 0,
            'message': 'Academic year or semester not configured'
        })
    
    # Get total active students
    total_students = Student.objects.filter(college=college, status='active').count()
    
    # Get signed-in students for current semester
    signed_in_count = StudentSemesterSignIn.objects.filter(
        student__college=college,
        academic_year=academic_year,
        semester=semester
    ).count()
    
    not_signed_in_count = total_students - signed_in_count
    signin_percentage = (signed_in_count / total_students * 100) if total_students > 0 else 0
    
    # Get breakdown by course
    course_breakdown = []
    courses = CollegeCourse.objects.filter(college=college)
    for course in courses:
        course_total = Student.objects.filter(college=college, course=course, status='active').count()
        course_signed_in = StudentSemesterSignIn.objects.filter(
            student__college=college,
            student__course=course,
            academic_year=academic_year,
            semester=semester
        ).count()
        course_breakdown.append({
            'course_id': course.id,
            'course_name': course.name,
            'total_students': course_total,
            'signed_in': course_signed_in,
            'not_signed_in': course_total - course_signed_in,
            'percentage': (course_signed_in / course_total * 100) if course_total > 0 else 0
        })
    
    return JsonResponse({
        'academic_year': academic_year,
        'semester': semester,
        'total_students': total_students,
        'signed_in_count': signed_in_count,
        'not_signed_in_count': not_signed_in_count,
        'signin_percentage': round(signin_percentage, 2),
        'course_breakdown': course_breakdown
    })


# ============================================
# Transcript Template & Generation API Endpoints
# ============================================

@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT"])
def api_report_template_mapping(request, college_slug):
    """API endpoint for managing report template mappings"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    # Only college admins can manage mappings
    if not request.user.is_college_admin():
        return JsonResponse({'error': 'Only college administrators can manage report template mappings'}, status=403)
    
    if request.method == 'GET':
        # Get or create mapping
        mapping, created = ReportTemplateMapping.objects.get_or_create(college=college)
        
        # Get all available templates for dropdowns
        templates = ReportTemplate.objects.filter(college=college, is_active=True).order_by('name')
        templates_data = [{
            'id': t.id,
            'name': t.name,
            'report_type': t.report_type
        } for t in templates]
        
        return JsonResponse({
            'mapping': {
                'transcript_template_id': mapping.transcript_template.id if mapping.transcript_template else None,
                'fee_structure_template_id': mapping.fee_structure_template.id if mapping.fee_structure_template else None,
                'exam_card_template_id': mapping.exam_card_template.id if mapping.exam_card_template else None,
            },
            'templates': templates_data
        })
    
    elif request.method == 'PUT':
        # Update mapping
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Get or create mapping
        mapping, created = ReportTemplateMapping.objects.get_or_create(college=college)
        
        # Update template assignments
        if 'transcript_template_id' in data:
            template_id = data['transcript_template_id']
            if template_id:
                try:
                    template = ReportTemplate.objects.get(pk=template_id, college=college)
                    mapping.transcript_template = template
                except ReportTemplate.DoesNotExist:
                    return JsonResponse({'error': 'Transcript template not found'}, status=404)
            else:
                mapping.transcript_template = None
        
        if 'fee_structure_template_id' in data:
            template_id = data['fee_structure_template_id']
            if template_id:
                try:
                    template = ReportTemplate.objects.get(pk=template_id, college=college)
                    mapping.fee_structure_template = template
                except ReportTemplate.DoesNotExist:
                    return JsonResponse({'error': 'Fee structure template not found'}, status=404)
            else:
                mapping.fee_structure_template = None
        
        if 'exam_card_template_id' in data:
            template_id = data['exam_card_template_id']
            if template_id:
                try:
                    template = ReportTemplate.objects.get(pk=template_id, college=college)
                    mapping.exam_card_template = template
                except ReportTemplate.DoesNotExist:
                    return JsonResponse({'error': 'Exam card template not found'}, status=404)
            else:
                mapping.exam_card_template = None
        
        mapping.updated_by = request.user
        mapping.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Report template mappings updated successfully',
            'mapping': {
                'transcript_template_id': mapping.transcript_template.id if mapping.transcript_template else None,
                'fee_structure_template_id': mapping.fee_structure_template.id if mapping.fee_structure_template else None,
                'exam_card_template_id': mapping.exam_card_template.id if mapping.exam_card_template else None,
            }
        })


# Removed: api_transcript_template - TranscriptTemplate has been removed
# Removed: api_generate_transcript - Use student download endpoints instead


@csrf_exempt
@require_http_methods(["GET"])
def api_student_download_transcript_pdf(request, college_slug):
    """API endpoint for student to download their transcript PDF"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    try:
        # Get academic year and semester filters
        academic_year = request.GET.get('academic_year', None)
        semester = request.GET.get('semester', None)
        if semester:
            semester = int(semester)
        
        # Get template for transcript
        from .utils.student_pdf_generator import get_template_for_report_type, generate_student_results_pdf
        template = get_template_for_report_type(college, 'transcript')
        if not template:
            return JsonResponse({
                'error': 'No report template configured for Transcript. Please configure a template in Academic Configuration → Reports.'
            }, status=404)
        
        # Generate PDF (transcript uses same data as results but with all academic periods)
        pdf_buffer = generate_student_results_pdf(student, template, academic_year, semester)
        
        # Create HTTP response
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        filename = f"transcript_{student.admission_number}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating transcript PDF: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'Error generating PDF: {str(e)}'
        }, status=500)


# ============================================
# Admin Portal API Endpoints (without college_slug)
# These endpoints get the college from the logged-in user
# ============================================

@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_admin_dashboard_stats(request):
    """API endpoint for admin dashboard statistics - gets college from logged-in user"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Get college from user
    if not hasattr(request.user, 'college') or not request.user.college:
        return JsonResponse({'error': 'User must be associated with a college'}, status=403)
    
    college = request.user.college
    
    # Calculate statistics
    total_students = Student.objects.filter(college=college).count()
    total_courses = CollegeCourse.objects.filter(college=college).count()
    total_lecturers = CustomUser.objects.filter(college=college, role='lecturer').count()
    total_units = CollegeUnit.objects.filter(college=college).count()
    
    # Count unique departments (using first word of course names as department)
    courses = CollegeCourse.objects.filter(college=college)
    seen_departments = set()
    for course in courses:
        dept_name = course.name.split()[0] if course.name else 'General'
        seen_departments.add(dept_name)
    total_departments = len(seen_departments)
    
    # Calculate changes (this month vs last month)
    from datetime import timedelta
    now = timezone.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_start = (start_of_month - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    students_this_month = Student.objects.filter(college=college, created_at__gte=start_of_month).count()
    students_last_month = Student.objects.filter(college=college, created_at__gte=last_month_start, created_at__lt=start_of_month).count()
    students_change = students_this_month - students_last_month if students_last_month > 0 else students_this_month
    
    courses_this_month = CollegeCourse.objects.filter(college=college, created_at__gte=start_of_month).count()
    courses_last_month = CollegeCourse.objects.filter(college=college, created_at__gte=last_month_start, created_at__lt=start_of_month).count()
    courses_change = courses_this_month - courses_last_month if courses_last_month > 0 else courses_this_month
    
    lecturers_this_month = CustomUser.objects.filter(college=college, role='lecturer', date_joined__gte=start_of_month).count()
    lecturers_last_month = CustomUser.objects.filter(college=college, role='lecturer', date_joined__gte=last_month_start, date_joined__lt=start_of_month).count()
    lecturers_change = lecturers_this_month - lecturers_last_month if lecturers_last_month > 0 else lecturers_this_month
    
    units_this_month = CollegeUnit.objects.filter(college=college, created_at__gte=start_of_month).count()
    units_last_month = CollegeUnit.objects.filter(college=college, created_at__gte=last_month_start, created_at__lt=start_of_month).count()
    units_change = units_this_month - units_last_month if units_last_month > 0 else units_this_month
    
    return JsonResponse({
        'total_students': total_students,
        'total_departments': total_departments,
        'total_courses': total_courses,
        'total_lecturers': total_lecturers,
        'total_units': total_units,
        'students_change': students_change,
        'courses_change': courses_change,
        'lecturers_change': lecturers_change,
        'units_change': units_change,
        'departments_change': 0  # Departments are derived from courses
    })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_admin_announcements_recent(request):
    """API endpoint for recent announcements - gets college from logged-in user"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Get college from user
    if not hasattr(request.user, 'college') or not request.user.college:
        return JsonResponse({'error': 'User must be associated with a college'}, status=403)
    
    college = request.user.college
    
    # Get recent announcements (last 10, ordered by created_at)
    from django.db.models import Q
    announcements = Announcement.objects.filter(
        college=college,
        is_active=True
    ).exclude(
        expires_at__lt=timezone.now()
    ).order_by('-created_at')[:10]
    
    announcements_list = []
    for ann in announcements:
        announcements_list.append({
            'id': ann.id,
            'title': ann.title,
            'content': ann.content[:100] + '...' if len(ann.content) > 100 else ann.content,
            'priority': ann.priority,
            'created_at': ann.created_at.isoformat(),
            'created_by': ann.created_by.get_full_name() if ann.created_by else 'Unknown',
            'target_type': ann.target_type
        })
    
    return JsonResponse({
        'announcements': announcements_list,
        'count': len(announcements_list)
    })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_admin_activity_recent(request):
    """API endpoint for recent system activity - gets college from logged-in user"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Get college from user
    if not hasattr(request.user, 'college') or not request.user.college:
        return JsonResponse({'error': 'User must be associated with a college'}, status=403)
    
    college = request.user.college
    
    # Get recent activities (enrollments, new students, etc.)
    recent_activities = []
    
    # Recent enrollments (last 10)
    recent_enrollments = Enrollment.objects.filter(unit__college=college).order_by('-enrolled_at')[:10]
    for enrollment in recent_enrollments:
        recent_activities.append({
            'type': 'enrollment',
            'icon': 'fa-user-graduate',
            'color': 'blue',
            'title': f'{enrollment.student.full_name} enrolled in {enrollment.unit.code}',
            'description': f'Semester {enrollment.semester}, {enrollment.academic_year}',
            'timestamp': enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None
        })
    
    # Recent students (last 5)
    recent_students = Student.objects.filter(college=college).order_by('-created_at')[:5]
    for student in recent_students:
        recent_activities.append({
            'type': 'student_added',
            'icon': 'fa-user-plus',
            'color': 'green',
            'title': f'New student: {student.full_name}',
            'description': f'Admission: {student.admission_number}',
            'timestamp': student.created_at.isoformat() if student.created_at else None
        })
    
    # Recent results submitted (last 5)
    recent_results = Result.objects.filter(enrollment__unit__college=college, status='submitted').order_by('-updated_at')[:5]
    for result in recent_results:
        recent_activities.append({
            'type': 'result_submitted',
            'icon': 'fa-file-check',
            'color': 'purple',
            'title': f'Results submitted for {result.enrollment.unit.code}',
            'description': f'Student: {result.enrollment.student.full_name}',
            'timestamp': result.updated_at.isoformat() if result.updated_at else None
        })
    
    # Sort by timestamp (most recent first) and limit to 15
    recent_activities.sort(key=lambda x: x['timestamp'] or '', reverse=True)
    recent_activities = recent_activities[:15]
    
    return JsonResponse({
        'activities': recent_activities,
        'count': len(recent_activities)
    })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_admin_user_profile(request):
    """API endpoint for current user profile - gets college from logged-in user"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    user = request.user
    
    # Get college info if available
    college_info = None
    if hasattr(user, 'college') and user.college:
        college_info = {
            'id': user.college.id,
            'name': user.college.name,
            'slug': user.college.slug
        }
    
    return JsonResponse({
        'id': user.id,
        'username': user.username,
        'email': user.email or '',
        'phone': user.phone or '',
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'full_name': user.get_full_name() or user.username,
        'role': user.role,
        'is_college_admin': user.is_college_admin(),
        'is_lecturer': user.is_lecturer(),
        'college': college_info
    })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_admin_logout(request):
    """API endpoint for admin logout"""
    from django.contrib.auth import logout
    
    # Logout the user
    logout(request)
    
    return JsonResponse({
        'success': True,
        'message': 'Logged out successfully'
    })


@login_required
@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_report_templates_list(request, college_slug):
    """API endpoint for listing and creating report templates"""
    try:
        college = get_college_from_slug(college_slug)
        if not college:
            return JsonResponse({'error': 'College not found'}, status=404)
        
        verify_user_college_access(request, college)
        
        if request.method == 'GET':
            try:
                # Check permissions: all users can view, but only principal/registrar can edit
                can_edit = request.user.is_principal() or request.user.is_registrar()
                
                # Query templates with error handling
                try:
                    templates = ReportTemplate.objects.filter(college=college).order_by('-created_at')
                except Exception as query_error:
                    # If query fails (e.g., table doesn't exist), return empty list
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f'Error querying ReportTemplate: {str(query_error)}')
                    return JsonResponse({
                        'templates': [],
                        'can_edit': can_edit,
                        'warning': 'Templates table may not be initialized. Please run migrations.'
                    })
                
                templates_data = []
                for template in templates:
                    try:
                        # Handle page_size field - default to A4 if not set (for backward compatibility)
                        # Use getattr to safely access the field in case migration hasn't been fully applied
                        try:
                            page_size = getattr(template, 'page_size', 'A4')
                            # If page_size is None or empty, default to A4
                            if not page_size:
                                page_size = 'A4'
                        except (AttributeError, ValueError, TypeError):
                            page_size = 'A4'
                        
                        templates_data.append({
                            'id': template.id,
                            'name': template.name,
                            'report_type': template.report_type,
                            'description': template.description or '',
                            'page_size': page_size,
                            'canvas_width': template.canvas_width,
                            'canvas_height': template.canvas_height,
                            'elements': template.elements or [],
                            'is_active': template.is_active,
                            'created_by': template.created_by.get_full_name() if template.created_by else 'Unknown',
                            'created_at': template.created_at.isoformat() if template.created_at else None,
                            'updated_at': template.updated_at.isoformat() if template.updated_at else None,
                        })
                    except Exception as e:
                        # Log error but continue with other templates
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f'Error processing template {template.id if hasattr(template, "id") else "unknown"}: {str(e)}')
                        continue
                
                return JsonResponse({
                    'templates': templates_data,
                    'can_edit': can_edit
                })
            except Exception as e:
                import traceback
                return JsonResponse({
                    'error': f'Error loading templates: {str(e)}',
                    'traceback': traceback.format_exc()
                }, status=500)
        
        elif request.method == 'POST':
            try:
                # Only principal and registrar can create/edit templates
                if not (request.user.is_principal() or request.user.is_registrar()):
                    return JsonResponse({'error': 'Only Principal and Registrar can create report templates'}, status=403)
                
                data = json.loads(request.body)
                name = data.get('name', '').strip()
                report_type = data.get('report_type', 'custom')
                description = data.get('description', '').strip()
                page_size = data.get('page_size', 'A4')
                elements = data.get('elements', [])
                is_active = data.get('is_active', True)
                
                # Validate page size
                valid_page_sizes = ['A4', 'A3', 'A5', 'Letter']
                if page_size not in valid_page_sizes:
                    page_size = 'A4'
                
                # Get dimensions for selected page size
                # PAGE_DIMENSIONS is a class attribute, access it directly
                PAGE_DIMENSIONS = {
                    'A4': (794, 1123),
                    'A3': (1123, 1587),
                    'A5': (559, 794),
                    'Letter': (816, 1056)
                }
                width, height = PAGE_DIMENSIONS.get(page_size, PAGE_DIMENSIONS['A4'])
                
                # Use provided canvas dimensions if specified, otherwise use page size dimensions
                canvas_width = int(data.get('canvas_width', width))
                canvas_height = int(data.get('canvas_height', height))
                
                if not name:
                    return JsonResponse({'error': 'Template name is required'}, status=400)
                
                template = ReportTemplate.objects.create(
                    college=college,
                    name=name,
                    report_type=report_type,
                    description=description,
                    page_size=page_size,
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                    elements=elements,
                    is_active=is_active,
                    created_by=request.user
                )
                
                return JsonResponse({
                    'success': True,
                    'message': 'Report template created successfully',
                    'template': {
                        'id': template.id,
                        'name': template.name,
                        'report_type': template.report_type,
                        'description': template.description,
                        'page_size': template.page_size,
                        'canvas_width': template.canvas_width,
                        'canvas_height': template.canvas_height,
                        'elements': template.elements,
                        'is_active': template.is_active,
                        'created_at': template.created_at.isoformat(),
                        'updated_at': template.updated_at.isoformat(),
                    }
                }, status=201)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON data'}, status=400)
            except Exception as e:
                import traceback
                return JsonResponse({
                    'error': f'Error creating template: {str(e)}',
                    'traceback': traceback.format_exc()
                }, status=500)
    except Exception as e:
        import traceback
        return JsonResponse({
            'error': f'Unexpected error: {str(e)}',
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def api_report_template_detail(request, college_slug, template_id):
    """API endpoint for getting, updating, or deleting a specific report template"""
    college = get_college_from_slug(college_slug)
    if not college:
        return JsonResponse({'error': 'College not found'}, status=404)
    
    verify_user_college_access(request, college)
    
    try:
        template = ReportTemplate.objects.get(id=template_id, college=college)
    except ReportTemplate.DoesNotExist:
        return JsonResponse({'error': 'Report template not found'}, status=404)
    
    if request.method == 'GET':
        # All users can view
        can_edit = request.user.is_principal() or request.user.is_registrar()
        
        # Handle page_size field - default to A4 if not set (for backward compatibility)
        try:
            page_size = getattr(template, 'page_size', 'A4')
        except (AttributeError, ValueError):
            page_size = 'A4'
        
        return JsonResponse({
            'id': template.id,
            'name': template.name,
            'report_type': template.report_type,
            'description': template.description,
            'page_size': page_size,
            'canvas_width': template.canvas_width,
            'canvas_height': template.canvas_height,
            'elements': template.elements,
            'is_active': template.is_active,
            'created_by': template.created_by.get_full_name() if template.created_by else 'Unknown',
            'created_at': template.created_at.isoformat(),
            'updated_at': template.updated_at.isoformat(),
            'can_edit': can_edit
        })
    
    elif request.method == 'PUT':
        # Only principal and registrar can update
        if not (request.user.is_principal() or request.user.is_registrar()):
            return JsonResponse({'error': 'Only Principal and Registrar can edit report templates'}, status=403)
        
        try:
            data = json.loads(request.body)
            
            # Update fields
            if 'name' in data:
                template.name = data['name'].strip()
            if 'report_type' in data:
                template.report_type = data['report_type']
            if 'description' in data:
                template.description = data['description'].strip()
            if 'page_size' in data:
                # Validate page size
                valid_page_sizes = ['A4', 'A3', 'A5', 'Letter']
                page_size = data['page_size']
                if page_size in valid_page_sizes:
                    template.page_size = page_size
                    # Update canvas dimensions to match page size if not explicitly provided
                    if 'canvas_width' not in data and 'canvas_height' not in data:
                        PAGE_DIMENSIONS = {
                            'A4': (794, 1123),
                            'A3': (1123, 1587),
                            'A5': (559, 794),
                            'Letter': (816, 1056)
                        }
                        width, height = PAGE_DIMENSIONS.get(page_size, PAGE_DIMENSIONS['A4'])
                        template.canvas_width = width
                        template.canvas_height = height
            if 'canvas_width' in data:
                template.canvas_width = int(data['canvas_width'])
            if 'canvas_height' in data:
                template.canvas_height = int(data['canvas_height'])
            if 'elements' in data:
                template.elements = data['elements']
            if 'is_active' in data:
                template.is_active = data['is_active']
            
            template.save()
            
            # Get page_size safely
            try:
                page_size = template.page_size if hasattr(template, 'page_size') else 'A4'
            except (AttributeError, ValueError):
                page_size = 'A4'
            
            return JsonResponse({
                'success': True,
                'message': 'Report template updated successfully',
                'template': {
                    'id': template.id,
                    'name': template.name,
                    'report_type': template.report_type,
                    'description': template.description,
                    'page_size': page_size,
                    'canvas_width': template.canvas_width,
                    'canvas_height': template.canvas_height,
                    'elements': template.elements,
                    'is_active': template.is_active,
                    'updated_at': template.updated_at.isoformat(),
                }
            })
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    elif request.method == 'DELETE':
        # Only principal and registrar can delete
        if not (request.user.is_principal() or request.user.is_registrar()):
            return JsonResponse({'error': 'Only Principal and Registrar can delete report templates'}, status=403)
        
        template.delete()
        return JsonResponse({
            'success': True,
            'message': 'Report template deleted successfully'
        })


@csrf_exempt
@require_http_methods(["GET"])
def api_student_download_results_pdf(request, college_slug):
    """API endpoint for student to download their results PDF"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    try:
        # Get academic year and semester filters
        academic_year = request.GET.get('academic_year', None)
        semester = request.GET.get('semester', None)
        if semester:
            semester = int(semester)
        
        # Get template for exam card (results are shown on exam card)
        from .utils.student_pdf_generator import get_template_for_report_type
        template = get_template_for_report_type(college, 'exam_card')
        if not template:
            return JsonResponse({
                'error': 'No report template configured for Exam Card. Please configure a template in Academic Configuration → Reports.'
            }, status=404)
        
        # Generate PDF
        pdf_buffer = generate_student_results_pdf(student, template, academic_year, semester)
        
        # Create HTTP response
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        filename = f"results_{student.admission_number}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating results PDF: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'Error generating PDF: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_student_download_registered_units_pdf(request, college_slug):
    """API endpoint for student to download their registered units (Exam Card) PDF"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    try:
        # Get academic year and semester filters
        academic_year = request.GET.get('academic_year', None)
        semester = request.GET.get('semester', None)
        if semester:
            semester = int(semester)
        
        # Get template for registered units (exam card)
        from .utils.student_pdf_generator import get_template_for_report_type
        template = get_template_for_report_type(college, 'exam_card')
        if not template:
            return JsonResponse({
                'error': 'No report template configured for Exam Card. Please configure a template in Academic Configuration → Reports.'
            }, status=404)
        
        # Generate PDF
        pdf_buffer = generate_student_registered_units_pdf(student, template, academic_year, semester)
        
        # Create HTTP response
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        filename = f"exam_card_{student.admission_number}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating registered units PDF: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'Error generating PDF: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_student_download_fee_structure_pdf(request, college_slug):
    """API endpoint for student to download their fee structure PDF"""
    error_response, student, college = verify_student_access(request, college_slug)
    if error_response:
        return error_response
    
    try:
        # Get template for registered units (exam card)
        from .utils.student_pdf_generator import get_template_for_report_type
        template = get_template_for_report_type(college, 'exam_card')
        if not template:
            return JsonResponse({
                'error': 'No report template configured for Exam Card. Please configure a template in Academic Configuration → Reports.'
            }, status=404)
        
        # Generate PDF
        pdf_buffer = generate_student_fee_structure_pdf(student, template)
        
        # Create HTTP response
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        filename = f"fee_structure_{student.admission_number}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating fee structure PDF: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'Error generating PDF: {str(e)}'
        }, status=500)
