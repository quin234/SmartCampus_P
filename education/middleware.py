from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.core.exceptions import PermissionDenied


class CollegeAccessMiddleware:
    """Middleware to enforce college-level data isolation"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip middleware for Django admin URLs to avoid interference
        if request.path.startswith('/django-admin/'):
            return self.get_response(request)
        
        # Store user's college in request for easy access
        if request.user.is_authenticated:
            if hasattr(request.user, 'college') and request.user.college:
                request.user_college = request.user.college
            else:
                request.user_college = None
        else:
            request.user_college = None
        
        response = self.get_response(request)
        return response


def college_required(view_func):
    """Decorator to ensure user belongs to a college (not super admin)"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if request.user.is_super_admin():
            # Super admin can access, but should be careful
            return view_func(request, *args, **kwargs)
        
        if not hasattr(request.user, 'college') or not request.user.college:
            raise PermissionDenied("You must be associated with a college to access this resource.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def super_admin_required(view_func):
    """Decorator to ensure user is super admin"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if not request.user.is_super_admin():
            raise PermissionDenied("Super admin access required.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def college_admin_required(view_func):
    """Decorator to ensure user is college admin"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if not (request.user.is_college_admin() or request.user.is_super_admin()):
            raise PermissionDenied("College admin access required.")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def lecturer_required(view_func):
    """Decorator to ensure user is lecturer or above"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if not (request.user.is_lecturer() or request.user.is_college_admin() or request.user.is_super_admin()):
            raise PermissionDenied("Lecturer access required.")
        
        return view_func(request, *args, **kwargs)
    return wrapper

