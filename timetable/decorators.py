"""
Decorators for timetable access control
"""
from functools import wraps
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied
from django.contrib import messages


def registrar_required_for_timetable(view_func):
    """Decorator to ensure only Registrar can access timetable management"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if not request.user.is_registrar():
            messages.error(request, 'Only Registrar can manage timetables.')
            raise PermissionDenied("Registrar access required for timetable management.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def director_blocked_from_timetable(view_func):
    """Decorator to block Director from viewing/editing timetables"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        if request.user.is_director():
            messages.error(request, 'Director cannot view or edit timetables.')
            raise PermissionDenied("Director access is not allowed for timetables.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def student_timetable_access(view_func):
    """Decorator to ensure students can only view their own course timetable"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        
        # This is for admin portal - students use student portal
        # But we can check if it's a student trying to access admin timetable
        if hasattr(request.user, 'role') and request.user.role == 'student':
            # Students should use student portal for timetable viewing
            messages.error(request, 'Please use the student portal to view your timetable.')
            return redirect('student_dashboard', college_slug=kwargs.get('college_slug', ''))
        
        return view_func(request, *args, **kwargs)
    return wrapper

