"""
Decorators for enforcing college-level data isolation
"""
from functools import wraps
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.utils.text import slugify
from .models import College


def get_college_from_slug(college_slug):
    """Helper to get college from slug"""
    try:
        college = College.objects.get(slug=college_slug) if hasattr(College, 'slug') else None
        if not college:
            # Fallback: try to get from slugified name
            for c in College.objects.all():
                if slugify(c.name) == college_slug:
                    return c
        return college
    except College.DoesNotExist:
        return None


def verify_college_access(view_func):
    """
    Decorator to verify user has access to the college specified in URL.
    STRICT: Super admins are BLOCKED from accessing college-specific pages.
    Only college admins and lecturers can access their own college data.
    Also checks if college is suspended and stores status in request.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        # STRICT: Super admin CANNOT access college-specific pages
        # They must use the superadmin interface only
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data. Please use the Super Admin dashboard.')
            return redirect('superadmin:dashboard')
        
        # Get college from slug if present in kwargs
        college_slug = kwargs.get('college_slug')
        if college_slug:
            college = get_college_from_slug(college_slug)
            if not college:
                raise Http404("College not found")
            
            # Verify user belongs to this college
            if not hasattr(request.user, 'college') or not request.user.college:
                raise PermissionDenied("You must be associated with a college to access this resource.")
            
            if request.user.college.id != college.id:
                raise PermissionDenied("You don't have access to this college.")
            
            # Store verified college in request for easy access
            request.verified_college = college
            # Check if college is suspended
            request.college_is_suspended = (college.registration_status == 'inactive')
            request.college = college
        
        # If no college_slug but user has college, use user's college
        elif hasattr(request.user, 'college') and request.user.college:
            request.verified_college = request.user.college
            college = request.user.college
            # Check if college is suspended
            request.college_is_suspended = (college.registration_status == 'inactive')
            request.college = college
        else:
            raise PermissionDenied("You must be associated with a college to access this resource.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def ensure_college_access(model_class, college_field='college', pk_param='pk'):
    """
    Decorator to ensure user can only access objects from their college.
    STRICT: Super admins are BLOCKED from accessing college-specific data.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('admin_login')
            
            # STRICT: Super admin CANNOT access college-specific data
            if request.user.is_super_admin():
                from django.contrib import messages
                messages.error(request, 'Super Admin cannot access individual college data.')
                return redirect('superadmin:dashboard')
            
            # Others must have a college
            if not hasattr(request.user, 'college') or not request.user.college:
                raise PermissionDenied("You must be associated with a college.")
            
            # If accessing a specific object (pk in kwargs), verify it belongs to user's college
            if pk_param in kwargs:
                pk = kwargs[pk_param]
                try:
                    obj = model_class.objects.get(pk=pk)
                    obj_college = getattr(obj, college_field, None)
                    
                    if obj_college and obj_college.id != request.user.college.id:
                        raise PermissionDenied("You don't have access to this resource.")
                except model_class.DoesNotExist:
                    raise Http404("Resource not found")
            
            # Store user's college for filtering
            request.user_college = request.user.college
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def filter_by_college(model_class, college_field='college'):
    """
    Decorator to automatically filter querysets by user's college.
    STRICT: Super admins are BLOCKED from accessing college-specific data.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('admin_login')
            
            # STRICT: Super admin CANNOT access college-specific data
            if request.user.is_super_admin():
                from django.contrib import messages
                messages.error(request, 'Super Admin cannot access individual college data.')
                return redirect('superadmin:dashboard')
            
            # Others must have a college
            if not hasattr(request.user, 'college') or not request.user.college:
                raise PermissionDenied("You must be associated with a college.")
            
            # Store user's college for filtering
            request.user_college = request.user.college
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def college_required(view_func):
    """
    Decorator to ensure user belongs to a college.
    STRICT: Super admins are BLOCKED - they must use superadmin interface.
    Also checks if college is suspended and stores status in request.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        # STRICT: Super admin CANNOT access college-specific pages
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data. Please use the Super Admin dashboard.')
            return redirect('superadmin:dashboard')
        
        if not hasattr(request.user, 'college') or not request.user.college:
            raise PermissionDenied("You must be associated with a college to access this resource.")
        
        # Check if college is suspended (inactive)
        college = request.user.college
        request.college_is_suspended = (college.registration_status == 'inactive')
        request.college = college
        
        return view_func(request, *args, **kwargs)
    return wrapper


def super_admin_required(view_func):
    """Decorator to ensure user is super admin"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if not request.user.is_super_admin():
            raise PermissionDenied("Super admin access required.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def college_admin_required(view_func):
    """
    Decorator to ensure user is college admin (Principal or Registrar).
    STRICT: Super admins are BLOCKED - they cannot access college admin functions.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        # STRICT: Super admin CANNOT access college admin functions
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data.')
            return redirect('superadmin:dashboard')
        
        if not request.user.is_college_admin():
            raise PermissionDenied("College admin access required.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def director_required(view_func):
    """Decorator to ensure user is Director (read-only access)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data.')
            return redirect('superadmin:dashboard')
        
        if not request.user.is_director():
            raise PermissionDenied("Director access required.")
        
        # Check if college is suspended
        if hasattr(request.user, 'college') and request.user.college:
            college = request.user.college
            request.college_is_suspended = (college.registration_status == 'inactive')
            request.college = college
        
        return view_func(request, *args, **kwargs)
    return wrapper


def principal_required(view_func):
    """Decorator to ensure user is Principal (full management)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data.')
            return redirect('superadmin:dashboard')
        
        if not request.user.is_principal():
            raise PermissionDenied("Principal access required.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def registrar_required(view_func):
    """Decorator to ensure user is Registrar (academic management)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data.')
            return redirect('superadmin:dashboard')
        
        if not request.user.is_registrar():
            raise PermissionDenied("Registrar access required.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def accounts_officer_required(view_func):
    """Decorator to ensure user is Accounts Officer (financial management)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data.')
            return redirect('superadmin:dashboard')
        
        if not request.user.is_accounts_officer():
            raise PermissionDenied("Accounts Officer access required.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def college_admin_or_accounts_required(view_func):
    """Decorator to ensure user is College Admin or Accounts Officer"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data.')
            return redirect('superadmin:dashboard')
        
        if not (request.user.role == 'college_admin' or request.user.is_accounts_officer()):
            raise PermissionDenied("College Admin or Accounts Officer access required.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def college_admin_required_for_fee_structure(view_func):
    """Decorator to ensure user is College Admin (for fee structure management)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data.')
            return redirect('superadmin:dashboard')
        
        if not request.user.can_manage_fee_structure():
            raise PermissionDenied("Director or College Admin access required to manage fee structure.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def reception_required(view_func):
    """Decorator to ensure user is Reception (student management)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data.')
            return redirect('superadmin:dashboard')
        
        if not request.user.is_reception():
            raise PermissionDenied("Reception access required.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def can_edit_academic(view_func):
    """Decorator to ensure user can edit academic content (Principal or Registrar)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data.')
            return redirect('superadmin:dashboard')
        
        if not request.user.can_edit_academic():
            raise PermissionDenied("You don't have permission to edit academic content.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def can_manage_students(view_func):
    """Decorator to ensure user can manage students (Principal or Registrar)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data.')
            return redirect('superadmin:dashboard')
        
        if not request.user.can_manage_students():
            raise PermissionDenied("You don't have permission to manage students.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def can_enter_all_marks(view_func):
    """Decorator to ensure user can enter marks for all units (Principal or Registrar)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data.')
            return redirect('superadmin:dashboard')
        
        if not request.user.can_enter_all_marks():
            raise PermissionDenied("You don't have permission to enter marks for all units.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def lecturer_required(view_func):
    """
    Decorator to ensure user is lecturer, principal, or registrar.
    STRICT: Super admins are BLOCKED - they cannot access lecturer functions.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        # STRICT: Super admin CANNOT access lecturer functions
        if request.user.is_super_admin():
            from django.contrib import messages
            messages.error(request, 'Super Admin cannot access individual college data.')
            return redirect('superadmin:dashboard')
        
        # Lecturers can enter marks for assigned units
        # Principal and Registrar can enter marks for all units
        if not (request.user.is_lecturer() or request.user.is_principal() or request.user.is_registrar()):
            raise PermissionDenied("Lecturer, Principal, or Registrar access required.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def student_required(view_func):
    """
    Decorator to ensure student is authenticated via session.
    Verifies student belongs to the college in the URL.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        college_slug = kwargs.get('college_slug')
        if not college_slug:
            raise Http404("College not found")
        
        # Get college from slug
        college = get_college_from_slug(college_slug)
        if not college:
            raise Http404("College not found")
        
        # Check if student is logged in (stored in session)
        student_id = request.session.get('student_id')
        if not student_id:
            return redirect('student_login', college_slug=college_slug)
        
        # Verify student exists and belongs to this college
        from .models import Student
        try:
            student = Student.objects.get(pk=student_id, college=college)
        except Student.DoesNotExist:
            # Invalid session, clear it and redirect to login
            request.session.flush()
            return redirect('student_login', college_slug=college_slug)
        
        # Check if college is suspended first
        if college.registration_status == 'inactive':
            # College is suspended - show suspended modal
            from django.shortcuts import render
            return render(request, 'education/student/college_suspended.html', {
                'student': student,
                'college': college,
            })
        
        # Check student status and handle accordingly
        if student.is_graduated():
            # Store student for congratulations page
            request.student = student
            request.verified_college = college
            # Allow access but view will show congratulations page
            return view_func(request, *args, **kwargs)
        elif student.is_suspended() or student.is_deferred():
            # Redirect to status message page
            from django.shortcuts import render
            status_message = {
                'suspended': 'Your account has been suspended. Please contact your college administration.',
                'deferred': 'Your studies have been deferred. Please contact your college administration for more information.'
            }
            return render(request, 'education/student/status_message.html', {
                'student': student,
                'college': college,
                'status': student.status,
                'message': status_message.get(student.status, 'Your account is not active.')
            })
        elif not student.is_active():
            # Clear session and redirect to login
            request.session.flush()
            return redirect('student_login', college_slug=college_slug)
        
        # Store student in request for easy access
        request.student = student
        request.verified_college = college
        
        return view_func(request, *args, **kwargs)
    return wrapper