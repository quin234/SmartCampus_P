"""
Super Admin API Views
Handles all API endpoints for Super Admin functionality
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone
from django.shortcuts import get_object_or_404
from datetime import timedelta
import json

from education.models import College, CustomUser, Student, CollegeCourse, CollegeUnit, SchoolRegistration


def check_superadmin(request):
    """Helper to verify user is super admin"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    if not request.user.is_super_admin():
        # Return 403 for API calls (frontend will handle redirect)
        return JsonResponse({
            'error': 'Super Admin access required',
            'redirect': '/admin/login/' if not (hasattr(request.user, 'college') and request.user.college) 
                       else f'/{request.user.college.get_slug()}/dashboard/'
        }, status=403)
    return None


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_overview(request):
    """API endpoint for dashboard overview statistics"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    # Calculate statistics
    total_colleges = College.objects.count()
    active_colleges = College.objects.filter(registration_status='active').count()
    pending_colleges = College.objects.filter(registration_status='pending').count()
    suspended_colleges = College.objects.filter(registration_status='inactive').count()
    total_students = Student.objects.count()
    total_lecturers = CustomUser.objects.filter(role='lecturer').count()
    total_departments = CollegeCourse.objects.values('name').distinct().count()
    
    # Calculate colleges added this month
    now = timezone.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    colleges_this_month = College.objects.filter(created_at__gte=start_of_month).count()
    
    # Get recent colleges
    recent_colleges = College.objects.order_by('-created_at')[:10]
    recent_colleges_data = [{
        'id': college.id,
        'name': college.name,
        'owner': college.principal_name,
        'email': college.email,
        'phone': college.phone,
        'location': college.county,
        'type': 'College',  # Default type
        'date_registered': college.created_at.strftime('%Y-%m-%d'),
        'status': college.registration_status,
    } for college in recent_colleges]
    
    # Calculate colleges growth by month (last 12 months)
    growth_data = []
    for i in range(11, -1, -1):
        month_start = (now - timedelta(days=30*i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if i == 0:
            month_end = now
        else:
            month_end = (now - timedelta(days=30*(i-1))).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        count = College.objects.filter(
            created_at__gte=month_start,
            created_at__lt=month_end
        ).count()
        growth_data.append({
            'month': month_start.strftime('%b %Y'),
            'count': count
        })
    
    # Calculate student distribution by college
    distribution_data = Student.objects.values('college__name').annotate(
        student_count=Count('id')
    ).order_by('-student_count')[:10]
    distribution_list = [{
        'college': item['college__name'] or 'Unknown',
        'students': item['student_count']
    } for item in distribution_data]
    
    return JsonResponse({
        'total_colleges': total_colleges,
        'active_colleges': active_colleges,
        'pending_colleges': pending_colleges,
        'suspended_colleges': suspended_colleges,
        'total_students': total_students,
        'total_lecturers': total_lecturers,
        'total_departments': total_departments,
        'colleges_change': colleges_this_month,
        'recent_colleges': recent_colleges_data,
        'growth_data': growth_data,
        'distribution_data': distribution_list,
    })


@login_required
@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_colleges(request):
    """API endpoint for colleges list with pagination and filters, and create new college"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    if request.method == 'POST':
        # Create new college
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['name', 'owner_email']
        for field in required_fields:
            if field not in data or not data[field]:
                return JsonResponse({
                    'success': False,
                    'error': f'{field.replace("_", " ").title()} is required'
                }, status=400)
        
        # Check if email already exists
        if College.objects.filter(email=data['owner_email']).exists():
            return JsonResponse({
                'success': False,
                'error': 'A college with this email already exists'
            }, status=400)
        
        # Create college
        college = College.objects.create(
            name=data['name'],
            principal_name=data.get('owner_name', ''),
            email=data['owner_email'],
            phone=data.get('owner_phone', ''),
            county=data.get('location', ''),
            address=data.get('address', ''),
            registration_status=data.get('status', 'pending')
        )
        
        return JsonResponse({
            'success': True,
            'message': 'College created successfully',
            'college': {
                'id': college.id,
                'name': college.name,
                'owner': college.principal_name,
                'email': college.email,
                'phone': college.phone,
                'location': college.county,
                'status': college.registration_status,
                'status_display': college.get_registration_status_display(),
            }
        }, status=201)
    
    # GET method - List colleges
    # Get query parameters
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 10))
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    
    # Build query
    colleges = College.objects.all()
    
    if search:
        colleges = colleges.filter(
            Q(name__icontains=search) |
            Q(principal_name__icontains=search) |
            Q(email__icontains=search) |
            Q(county__icontains=search)
        )
    
    if status_filter:
        colleges = colleges.filter(registration_status=status_filter)
    
    # Note: Type filter would need to be added to College model if needed
    # For now, we'll skip it
    
    # Order by creation date (newest first)
    colleges = colleges.order_by('-created_at')
    
    # Paginate
    paginator = Paginator(colleges, page_size)
    page_obj = paginator.get_page(page)
    
    # Format data
    colleges_data = [{
        'id': college.id,
        'name': college.name,
        'owner': college.principal_name,
        'email': college.email,
        'phone': college.phone,
        'location': college.county,
        'address': college.address,
        'type': 'College',  # Default
        'date_registered': college.created_at.strftime('%Y-%m-%d'),
        'status': college.registration_status,
        'status_display': college.get_registration_status_display(),
    } for college in page_obj]
    
    return JsonResponse({
        'count': paginator.count,
        'page': page,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'results': colleges_data,
        'next': page_obj.next_page_number() if page_obj.has_next() else None,
        'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
    })


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def api_college_detail(request, college_id):
    """API endpoint for individual college operations (GET, PUT, DELETE)"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    college = get_object_or_404(College, id=college_id)
    
    if request.method == 'GET':
        # Return single college details
        return JsonResponse({
            'id': college.id,
            'name': college.name,
            'owner': college.principal_name,
            'email': college.email,
            'phone': college.phone,
            'location': college.county,
            'address': college.address,
            'type': 'College',  # Default
            'date_registered': college.created_at.strftime('%Y-%m-%d'),
            'status': college.registration_status,
            'status_display': college.get_registration_status_display(),
        })
    
    elif request.method == 'PUT':
        # Update college
        data = json.loads(request.body)
        
        # Update fields
        if 'name' in data:
            college.name = data['name']
        if 'owner_name' in data:
            college.principal_name = data['owner_name']
        if 'owner_email' in data:
            college.email = data['owner_email']
        if 'owner_phone' in data:
            college.phone = data['owner_phone']
        if 'location' in data:
            college.county = data['location']
        if 'address' in data:
            college.address = data['address']
        if 'status' in data:
            college.registration_status = data['status']
        
        college.save()
        
        return JsonResponse({
            'success': True,
            'message': 'College updated successfully',
            'college': {
                'id': college.id,
                'name': college.name,
                'owner': college.principal_name,
                'email': college.email,
                'phone': college.phone,
                'location': college.county,
                'status': college.registration_status,
                'status_display': college.get_registration_status_display(),
            }
        })
    
    elif request.method == 'DELETE':
        # Delete college
        college.delete()
        return JsonResponse({
            'success': True,
            'message': 'College deleted successfully'
        }, status=200)


@login_required
@csrf_exempt
@require_http_methods(["PUT"])
def api_college_approve(request, college_id):
    """API endpoint to approve a college"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    college = get_object_or_404(College, id=college_id)
    
    # Validate state transition
    if college.registration_status == 'active':
        return JsonResponse({
            'success': False,
            'error': 'College is already active'
        }, status=400)
    
    college.registration_status = 'active'
    college.save()
    
    return JsonResponse({
        'success': True,
        'message': 'College approved successfully',
        'college': {
            'id': college.id,
            'name': college.name,
            'status': college.registration_status,
            'status_display': college.get_registration_status_display(),
        }
    })


@login_required
@csrf_exempt
@require_http_methods(["PUT"])
def api_college_suspend(request, college_id):
    """API endpoint to suspend a college"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    college = get_object_or_404(College, id=college_id)
    
    # Validate state transition
    if college.registration_status == 'inactive':
        return JsonResponse({
            'success': False,
            'error': 'College is already suspended'
        }, status=400)
    
    college.registration_status = 'inactive'
    college.save()
    
    return JsonResponse({
        'success': True,
        'message': 'College suspended successfully',
        'college': {
            'id': college.id,
            'name': college.name,
            'status': college.registration_status,
            'status_display': college.get_registration_status_display(),
        }
    })


@login_required
@csrf_exempt
@require_http_methods(["PUT"])
def api_colleges_bulk_approve(request):
    """API endpoint to bulk approve colleges"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    data = json.loads(request.body)
    college_ids = data.get('ids', [])
    
    if not college_ids:
        return JsonResponse({
            'success': False,
            'error': 'No college IDs provided'
        }, status=400)
    
    # Get colleges
    colleges = College.objects.filter(id__in=college_ids)
    approved_count = 0
    
    for college in colleges:
        if college.registration_status != 'active':
            college.registration_status = 'active'
            college.save()
            approved_count += 1
    
    return JsonResponse({
        'success': True,
        'message': f'{approved_count} college(s) approved successfully',
        'approved_count': approved_count
    })


@login_required
@csrf_exempt
@require_http_methods(["PUT"])
def api_colleges_bulk_suspend(request):
    """API endpoint to bulk suspend colleges"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    data = json.loads(request.body)
    college_ids = data.get('ids', [])
    
    if not college_ids:
        return JsonResponse({
            'success': False,
            'error': 'No college IDs provided'
        }, status=400)
    
    # Get colleges
    colleges = College.objects.filter(id__in=college_ids)
    suspended_count = 0
    
    for college in colleges:
        if college.registration_status != 'inactive':
            college.registration_status = 'inactive'
            college.save()
            suspended_count += 1
    
    return JsonResponse({
        'success': True,
        'message': f'{suspended_count} college(s) suspended successfully',
        'suspended_count': suspended_count
    })


@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def api_colleges_bulk_delete(request):
    """API endpoint to bulk delete colleges"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    data = json.loads(request.body)
    college_ids = data.get('ids', [])
    
    if not college_ids:
        return JsonResponse({
            'success': False,
            'error': 'No college IDs provided'
        }, status=400)
    
    # Get and delete colleges
    colleges = College.objects.filter(id__in=college_ids)
    deleted_count = colleges.count()
    colleges.delete()
    
    return JsonResponse({
        'success': True,
        'message': f'{deleted_count} college(s) deleted successfully',
        'deleted_count': deleted_count
    })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_analytics(request):
    """API endpoint for comprehensive analytics data"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    now = timezone.now()
    
    # Overview statistics
    total_colleges = College.objects.count()
    total_students = Student.objects.count()
    total_lecturers = CustomUser.objects.filter(role='lecturer').count()
    total_courses = CollegeCourse.objects.count()
    total_units = CollegeUnit.objects.count()
    
    # Status breakdown
    active_colleges = College.objects.filter(registration_status='active').count()
    pending_colleges = College.objects.filter(registration_status='pending').count()
    inactive_colleges = College.objects.filter(registration_status='inactive').count()
    
    # Growth trends - Colleges by month (last 12 months)
    colleges_growth = []
    for i in range(11, -1, -1):
        month_start = (now - timedelta(days=30*i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if i == 0:
            month_end = now
        else:
            month_end = (now - timedelta(days=30*(i-1))).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        count = College.objects.filter(
            created_at__gte=month_start,
            created_at__lt=month_end
        ).count()
        colleges_growth.append({
            'month': month_start.strftime('%b %Y'),
            'count': count
        })
    
    # Students growth by month
    students_growth = []
    for i in range(11, -1, -1):
        month_start = (now - timedelta(days=30*i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if i == 0:
            month_end = now
        else:
            month_end = (now - timedelta(days=30*(i-1))).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        count = Student.objects.filter(
            created_at__gte=month_start,
            created_at__lt=month_end
        ).count()
        students_growth.append({
            'month': month_start.strftime('%b %Y'),
            'count': count
        })
    
    # Student distribution by college (top 10)
    student_distribution = Student.objects.values('college__name').annotate(
        student_count=Count('id')
    ).order_by('-student_count')[:10]
    student_distribution_list = [{
        'college': item['college__name'] or 'Unknown',
        'students': item['student_count']
    } for item in student_distribution]
    
    # Lecturers per college
    lecturers_by_college = CustomUser.objects.filter(role='lecturer').values('college__name').annotate(
        lecturer_count=Count('id')
    ).order_by('-lecturer_count')[:10]
    lecturers_by_college_list = [{
        'college': item['college__name'] or 'No College',
        'lecturers': item['lecturer_count']
    } for item in lecturers_by_college]
    
    # Top colleges by student count
    top_colleges = College.objects.annotate(
        students_count=Count('students'),
        lecturers_count=Count('staff', filter=Q(staff__role='lecturer')),
        courses_count=Count('courses')
    ).order_by('-students_count')[:10]
    
    top_colleges_list = [{
        'id': college.id,
        'name': college.name,
        'students_count': college.students_count,
        'lecturers_count': college.lecturers_count,
        'courses_count': college.courses_count,
        'status': college.registration_status
    } for college in top_colleges]
    
    # Recent registrations (last 10)
    recent_registrations = SchoolRegistration.objects.order_by('-created_at')[:10]
    recent_registrations_list = [{
        'id': reg.id,
        'school_name': reg.school_name,
        'school_type': reg.school_type,
        'owner_name': reg.owner_full_name,
        'email': reg.owner_email,
        'date': reg.created_at.strftime('%Y-%m-%d'),
        'status': reg.status
    } for reg in recent_registrations]
    
    return JsonResponse({
        'overview': {
            'total_colleges': total_colleges,
            'total_students': total_students,
            'total_lecturers': total_lecturers,
            'total_courses': total_courses,
            'total_units': total_units
        },
        'status_breakdown': {
            'active': active_colleges,
            'pending': pending_colleges,
            'inactive': inactive_colleges
        },
        'growth_trends': {
            'colleges': colleges_growth,
            'students': students_growth
        },
        'distributions': {
            'students_by_college': student_distribution_list,
            'lecturers_by_college': lecturers_by_college_list
        },
        'top_colleges': top_colleges_list,
        'recent_registrations': recent_registrations_list
    })


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT"])
def api_settings(request):
    """API endpoint for system settings"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    if request.method == 'GET':
        # Return current settings (in production, these would be stored in database)
        # For now, return defaults
        return JsonResponse({
            'platform_name': 'SmartCampus',
            'logo_url': '',
            'default_registration_status': 'pending',
            'system_email': 'admin@smartcampus.com',
            'maintenance_mode': False,
            'smtp_host': '',
            'smtp_port': 587,
            'smtp_username': '',
            'smtp_password': '',
            'password_min_length': 8,
            'session_timeout': 3600,
        })
    
    elif request.method == 'PUT':
        # Update settings
        data = json.loads(request.body)
        # In a real implementation, save to database or settings file
        # For now, just return success
        return JsonResponse({
            'success': True,
            'message': 'Settings updated successfully',
            'settings': data
        })


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT", "POST"])
def api_profile(request):
    """API endpoint for super admin profile"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    if request.method == 'GET':
        # Return current profile with last login info
        last_login = request.user.last_login.strftime('%Y-%m-%d %H:%M:%S') if request.user.last_login else 'Never'
        
        return JsonResponse({
            'id': request.user.id,
            'username': request.user.username,
            'email': request.user.email,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'phone': getattr(request.user, 'phone', ''),
            'last_login': last_login,
            'date_joined': request.user.date_joined.strftime('%Y-%m-%d %H:%M:%S') if request.user.date_joined else None,
        })
    
    elif request.method == 'PUT':
        # Update profile
        data = json.loads(request.body)
        user = request.user
        
        if 'first_name' in data:
            user.first_name = data['first_name']
        if 'last_name' in data:
            user.last_name = data['last_name']
        if 'email' in data:
            user.email = data['email']
        if 'phone' in data:
            user.phone = data['phone']
        
        user.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Profile updated successfully'
        })
    
    elif request.method == 'POST':
        # Change password
        data = json.loads(request.body)
        user = request.user
        
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        if not current_password or not new_password or not confirm_password:
            return JsonResponse({
                'success': False,
                'error': 'All password fields are required'
            }, status=400)
        
        if new_password != confirm_password:
            return JsonResponse({
                'success': False,
                'error': 'New passwords do not match'
            }, status=400)
        
        if not user.check_password(current_password):
            return JsonResponse({
                'success': False,
                'error': 'Current password is incorrect'
            }, status=400)
        
        user.set_password(new_password)
        user.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Password changed successfully'
        })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_students_detail(request):
    """API endpoint for detailed students list with college information"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    # Get query parameters
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))
    search = request.GET.get('search', '')
    
    # Build query
    students = Student.objects.select_related('college', 'course').all()
    
    if search:
        students = students.filter(
            Q(admission_number__icontains=search) |
            Q(full_name__icontains=search) |
            Q(email__icontains=search) |
            Q(college__name__icontains=search) |
            Q(course__name__icontains=search)
        )
    
    # Order by college name, then admission number
    students = students.order_by('college__name', 'admission_number')
    
    # Paginate
    paginator = Paginator(students, page_size)
    page_obj = paginator.get_page(page)
    
    # Format data
    students_data = []
    for student in page_obj:
        students_data.append({
            'id': student.id,
            'admission_number': student.admission_number,
            'full_name': student.full_name,
            'email': student.email or '',
            'phone': student.phone or '',
            'course': student.course.name if student.course else 'Not Assigned',
            'year': student.year_of_study,
            'gender': student.get_gender_display(),
            'college_id': student.college.id,
            'college_name': student.college.name,
            'college_email': student.college.email,
            'college_location': student.college.county,
            'college_address': student.college.address,
        })
    
    return JsonResponse({
        'total': paginator.count,
        'page': page,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'students': students_data,
        'next': page_obj.next_page_number() if page_obj.has_next() else None,
        'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
    })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_lecturers_detail(request):
    """API endpoint for detailed lecturers list with college information"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    # Get query parameters
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))
    search = request.GET.get('search', '')
    
    # Build query
    lecturers = CustomUser.objects.filter(role='lecturer').select_related('college')
    
    if search:
        lecturers = lecturers.filter(
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(college__name__icontains=search)
        )
    
    # Annotate with assigned units count
    lecturers = lecturers.annotate(
        assigned_units_count=Count('assigned_units')
    )
    
    # Order by college name, then name
    lecturers = lecturers.order_by('college__name', 'first_name', 'last_name')
    
    # Paginate
    paginator = Paginator(lecturers, page_size)
    page_obj = paginator.get_page(page)
    
    # Format data
    lecturers_data = []
    for lecturer in page_obj:
        lecturers_data.append({
            'id': lecturer.id,
            'username': lecturer.username,
            'full_name': f"{lecturer.first_name} {lecturer.last_name}".strip() or lecturer.username,
            'email': lecturer.email or '',
            'phone': lecturer.phone or '',
            'college_id': lecturer.college.id if lecturer.college else None,
            'college_name': lecturer.college.name if lecturer.college else 'No College',
            'college_email': lecturer.college.email if lecturer.college else '',
            'college_location': lecturer.college.county if lecturer.college else '',
            'assigned_units_count': lecturer.assigned_units_count,
        })
    
    return JsonResponse({
        'total': paginator.count,
        'page': page,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'lecturers': lecturers_data,
        'next': page_obj.next_page_number() if page_obj.has_next() else None,
        'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
    })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_colleges_detail(request):
    """API endpoint for detailed colleges list with statistics"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    # Get query parameters
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))
    search = request.GET.get('search', '')
    
    # Build query
    colleges = College.objects.all()
    
    if search:
        colleges = colleges.filter(
            Q(name__icontains=search) |
            Q(principal_name__icontains=search) |
            Q(email__icontains=search) |
            Q(county__icontains=search)
        )
    
    # Annotate with counts
    colleges = colleges.annotate(
        students_count=Count('students'),
        lecturers_count=Count('staff', filter=Q(staff__role='lecturer'))
    )
    
    # Order by name
    colleges = colleges.order_by('name')
    
    # Paginate
    paginator = Paginator(colleges, page_size)
    page_obj = paginator.get_page(page)
    
    # Format data
    colleges_data = []
    for college in page_obj:
        colleges_data.append({
            'id': college.id,
            'name': college.name,
            'principal_name': college.principal_name,
            'email': college.email,
            'phone': college.phone,
            'location': college.county,
            'address': college.address,
            'status': college.registration_status,
            'status_display': college.get_registration_status_display(),
            'students_count': college.students_count,
            'lecturers_count': college.lecturers_count,
        })
    
    return JsonResponse({
        'total': paginator.count,
        'page': page,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'colleges': colleges_data,
        'next': page_obj.next_page_number() if page_obj.has_next() else None,
        'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
    })


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_colleges_cards(request):
    """API endpoint for colleges cards view - returns owner name and active students count"""
    check_result = check_superadmin(request)
    if check_result:
        return check_result
    
    # Get query parameters
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    search = request.GET.get('search', '')
    
    # Build query - only get main colleges (not branches)
    colleges = College.objects.filter(parent_college__isnull=True)
    
    if search:
        colleges = colleges.filter(
            Q(name__icontains=search) |
            Q(principal_name__icontains=search) |
            Q(email__icontains=search) |
            Q(county__icontains=search)
        )
    
    # Annotate with active students count
    colleges = colleges.annotate(
        active_students_count=Count('students', filter=Q(students__status='active'))
    )
    
    # Order by name
    colleges = colleges.order_by('name')
    
    # Paginate
    paginator = Paginator(colleges, page_size)
    page_obj = paginator.get_page(page)
    
    # Format data for cards
    colleges_data = []
    for college in page_obj:
        colleges_data.append({
            'id': college.id,
            'name': college.name,
            'owner_name': college.principal_name,
            'active_students': college.active_students_count,
            'status': college.registration_status,
            'status_display': college.get_registration_status_display(),
            'email': college.email,
            'phone': college.phone,
            'location': college.county,
            'address': college.address,
        })
    
    return JsonResponse({
        'total': paginator.count,
        'page': page,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'colleges': colleges_data,
        'next': page_obj.next_page_number() if page_obj.has_next() else None,
        'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
    })