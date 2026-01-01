from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import login, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Avg
from django.core.paginator import Paginator
from django.http import JsonResponse, Http404, HttpResponseForbidden
from django.core.exceptions import PermissionDenied, ValidationError
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import json
import time
import random
import re
from .models import (
    College, CustomUser, GlobalCourse, GlobalUnit, GlobalCourseUnit,
    CollegeCourse, CollegeUnit, CollegeCourseUnit, Student, Enrollment, Result,
    SchoolRegistration, Announcement, StudentSemesterSignIn, PasswordResetCode
)
from accounts.models import Payment, FeeStructure, DarajaSettings
from accounts.daraja_service import DarajaService
from accounts.views import calculate_expected_fees
from decimal import Decimal
from django.db.models import Sum
from superadmin.models import CollegePaymentConfig, CollegePayment
from .middleware import (
    college_required, super_admin_required, college_admin_required, lecturer_required
)
from .decorators import ensure_college_access, verify_college_access, get_college_from_slug, student_required, director_required
from .forms import (
    CollegeRegistrationForm, UserRegistrationForm, StudentForm,
    CollegeCourseForm, CollegeUnitForm, EnrollmentForm, ResultForm,
    PasswordResetRequestForm, PasswordResetVerifyForm, PasswordResetForm
)


def permission_denied_view(request, exception=None):
    """
    Custom 403 Permission Denied error handler
    Renders a nice error page with logout link
    """
    return render(request, '403.html', {
        'exception': str(exception) if exception else None,
        'user': request.user if hasattr(request, 'user') else None
    }, status=403)


def page_not_found_view(request, exception=None):
    """
    Custom 404 Page Not Found error handler
    """
    return render(request, '404.html', {
        'exception': str(exception) if exception else None,
        'user': request.user if hasattr(request, 'user') else None
    }, status=404)


def server_error_view(request):
    """
    Custom 500 Server Error handler
    """
    return render(request, '500.html', {
        'user': request.user if hasattr(request, 'user') else None
    }, status=500)


def landing_page(request):
    """Render the landing page - redirects authenticated users appropriately"""
    if request.user.is_authenticated:
        if request.user.is_super_admin():
            return redirect('superadmin:dashboard')
        elif request.user.is_director() and hasattr(request.user, 'college') and request.user.college:
            return redirect('director_dashboard')
        elif request.user.role == 'college_admin' and hasattr(request.user, 'college') and request.user.college:
            return redirect('director_dashboard')
        else:
            return redirect('admin_login')
    return render(request, 'landing.html')


def register_page(request):
    """Render college registration page"""
    return render(request, 'education/register.html')


def admin_login_page(request):
    """College Admin login page - redirects super admins to super admin login"""
    # Redirect if already authenticated
    if request.user.is_authenticated:
        if request.user.is_super_admin():
            return redirect('superadmin:dashboard')
        elif request.user.is_director() and hasattr(request.user, 'college') and request.user.college:
            return redirect('director_dashboard')
        elif request.user.role == 'college_admin' and hasattr(request.user, 'college') and request.user.college:
            return redirect('director_dashboard')
        elif hasattr(request.user, 'college') and request.user.college:
            return redirect('college_landing', college_slug=request.user.college.get_slug())
        else:
            return redirect('admin_login')

    # Handle POST request
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            if user.is_super_admin():
                # Super admin should use super admin login
                return redirect('superadmin:login')
            # Director - redirect to director dashboard (check before other roles)
            elif user.is_director() and hasattr(user, 'college') and user.college:
                return redirect('director_dashboard')
            # College admin - redirect to director dashboard
            elif user.role == 'college_admin' and hasattr(user, 'college') and user.college:
                return redirect('director_dashboard')
            # Lecturer and other roles - redirect to landing page
            elif hasattr(user, 'college') and user.college:
                return redirect('college_landing', college_slug=user.college.get_slug())
            else:
                return render(request, 'admin/login.html', {'error': 'No college associated with your account.'})
        else:
            return render(request, 'admin/login.html', {'error': 'Invalid username or password.'})

    return render(request, 'admin/login.html')


def generate_reset_code():
    """Generate a 6-digit random code"""
    return str(random.randint(100000, 999999))


def send_reset_code_email(email, code):
    """Send password reset code via email"""
    try:
        subject = 'Password Reset Code - SmartCampus'
        message = f'''
Hello,

You have requested to reset your password for your SmartCampus account.

Your password reset code is: {code}

This code will expire in 15 minutes.

If you did not request this password reset, please ignore this email.

Best regards,
SmartCampus Team
        '''.strip()
        
        send_mail(
            subject,
            message,
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@smartcampus.com'),
            [email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def send_reset_code_sms(phone, code):
    """Send password reset code via SMS (placeholder - implement with actual SMS service)"""
    # TODO: Integrate with actual SMS service (e.g., Twilio, AWS SNS, etc.)
    # For now, this is a placeholder
    try:
        # In production, replace this with actual SMS sending logic
        print(f"SMS Code for {phone}: {code}")
        # Example with Twilio:
        # from twilio.rest import Client
        # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # client.messages.create(
        #     body=f'Your SmartCampus password reset code is: {code}',
        #     from_=settings.TWILIO_PHONE_NUMBER,
        #     to=phone
        # )
        return True
    except Exception as e:
        print(f"Error sending SMS: {e}")
        return False


def is_email(identifier):
    """Check if identifier is an email address"""
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_pattern, identifier) is not None


def password_reset_request(request):
    """Handle password reset request - send code to email or phone"""
    if request.user.is_authenticated:
        return redirect('admin_login')
    
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data['identifier']
            
            # Find user by email or phone
            user = None
            is_email_address = is_email(identifier)
            
            if is_email_address:
                # Search by email in CustomUser
                try:
                    user = CustomUser.objects.get(email=identifier)
                except CustomUser.DoesNotExist:
                    # Also check if it's a college email (for directors)
                    try:
                        college = College.objects.get(email=identifier)
                        # Find director user for this college
                        user = CustomUser.objects.filter(college=college, role='director').first()
                    except College.DoesNotExist:
                        pass
            else:
                # Search by phone
                try:
                    user = CustomUser.objects.get(phone=identifier)
                except CustomUser.DoesNotExist:
                    # Also check if it's a college phone (for directors)
                    try:
                        college = College.objects.get(phone=identifier)
                        # Find director user for this college
                        user = CustomUser.objects.filter(college=college, role='director').first()
                    except College.DoesNotExist:
                        pass
            
            if not user:
                messages.error(request, 'No account found with that email or phone number.')
                return render(request, 'admin/password_reset_request.html', {'form': form})
            
            # Generate reset code
            code = generate_reset_code()
            expires_at = timezone.now() + timezone.timedelta(minutes=15)
            
            # Create or update reset code
            reset_code, created = PasswordResetCode.objects.update_or_create(
                user=user,
                is_verified=False,
                defaults={
                    'code': code,
                    'email': user.email if is_email_address else '',
                    'phone': identifier if not is_email_address else '',
                    'expires_at': expires_at
                }
            )
            
            # Send code via email or SMS
            if is_email_address:
                if send_reset_code_email(user.email, code):
                    messages.success(request, f'A password reset code has been sent to {user.email}')
                    return redirect('password_reset_verify', user_id=user.id)
                else:
                    messages.error(request, 'Failed to send email. Please try again later.')
            else:
                if send_reset_code_sms(identifier, code):
                    messages.success(request, f'A password reset code has been sent to {identifier}')
                    return redirect('password_reset_verify', user_id=user.id)
                else:
                    messages.error(request, 'Failed to send SMS. Please try again later.')
    else:
        form = PasswordResetRequestForm()
    
    return render(request, 'admin/password_reset_request.html', {'form': form})


def password_reset_verify(request, user_id):
    """Verify the reset code"""
    if request.user.is_authenticated:
        return redirect('admin_login')
    
    try:
        user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        messages.error(request, 'Invalid reset request.')
        return redirect('password_reset_request')
    
    # Get the latest unverified reset code
    reset_code = PasswordResetCode.objects.filter(
        user=user,
        is_verified=False
    ).order_by('-created_at').first()
    
    if not reset_code or reset_code.is_expired():
        messages.error(request, 'Reset code has expired. Please request a new one.')
        return redirect('password_reset_request')
    
    if request.method == 'POST':
        form = PasswordResetVerifyForm(request.POST)
        if form.is_valid():
            entered_code = form.cleaned_data['code']
            
            if reset_code.code == entered_code:
                # Mark code as verified
                reset_code.is_verified = True
                reset_code.save()
                
                # Store user_id in session for password reset
                request.session['password_reset_user_id'] = user.id
                messages.success(request, 'Code verified successfully. Please set your new password.')
                return redirect('password_reset_confirm')
            else:
                messages.error(request, 'Invalid code. Please try again.')
    else:
        form = PasswordResetVerifyForm()
    
    return render(request, 'admin/password_reset_verify.html', {
        'form': form,
        'user': user,
        'reset_code': reset_code
    })


def password_reset_confirm(request):
    """Confirm password reset"""
    if request.user.is_authenticated:
        return redirect('admin_login')
    
    user_id = request.session.get('password_reset_user_id')
    if not user_id:
        messages.error(request, 'Invalid reset session. Please start over.')
        return redirect('password_reset_request')
    
    try:
        user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        messages.error(request, 'Invalid reset request.')
        return redirect('password_reset_request')
    
    # Verify that there's a verified reset code
    reset_code = PasswordResetCode.objects.filter(
        user=user,
        is_verified=True
    ).order_by('-created_at').first()
    
    if not reset_code or reset_code.is_expired():
        messages.error(request, 'Reset session expired. Please request a new code.')
        del request.session['password_reset_user_id']
        return redirect('password_reset_request')
    
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            
            # Update password
            user.set_password(new_password)
            user.save()
            
            # Mark all reset codes for this user as used
            PasswordResetCode.objects.filter(user=user).update(is_verified=True)
            
            # Clear session
            del request.session['password_reset_user_id']
            
            messages.success(request, 'Password reset successfully! You can now login with your new password.')
            return redirect('admin_login')
    else:
        form = PasswordResetForm()
    
    return render(request, 'admin/password_reset_confirm.html', {'form': form, 'user': user})


@login_required
def admin_password_reset(request, user_id):
    """Allow directors/principals to reset passwords for other users"""
    current_user = request.user
    
    # Only directors and principals can reset passwords
    if not (current_user.is_director() or current_user.is_principal()):
        messages.error(request, 'You do not have permission to reset passwords.')
        return redirect('admin_login')
    
    try:
        target_user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('admin_login')
    
    # Directors can reset passwords for users in their college
    # Principals can reset passwords for users in their college
    if current_user.college != target_user.college:
        messages.error(request, 'You can only reset passwords for users in your college.')
        return redirect('admin_login')
    
    # Cannot reset password for directors (only directors can reset their own via email/phone)
    if target_user.is_director() and not current_user.is_director():
        messages.error(request, 'Only directors can reset director passwords.')
        return redirect('admin_login')
    
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            
            # Update password
            target_user.set_password(new_password)
            target_user.save()
            
            messages.success(request, f'Password reset successfully for {target_user.username}.')
            # Redirect back to user list or dashboard
            if hasattr(current_user, 'college') and current_user.college:
                return redirect('college_landing', college_slug=current_user.college.get_slug())
            return redirect('admin_login')
    else:
        form = PasswordResetForm()
    
    return render(request, 'admin/admin_password_reset.html', {
        'form': form,
        'target_user': target_user
    })


@csrf_exempt
@require_http_methods(["POST"])
def register_school(request):
    """API endpoint for school registration - handles both JSON and form data"""
    try:
        # Handle both JSON and form data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            # Form data
            data = request.POST.dict()
            # Handle file upload
            if 'school_logo' in request.FILES:
                data['school_logo'] = request.FILES['school_logo']
        
        # Debug: Log received data (remove in production)
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Registration data received: {list(data.keys())}")
        logger.debug(f"Content-Type: {request.content_type}")
        logger.debug(f"POST data: {dict(request.POST)}")
        
        # Set defaults - always college and director
        data['school_type'] = 'college'
        data['position'] = 'director'
        
        # Ensure website field is handled properly (optional)
        if 'school_website' not in data or not data.get('school_website'):
            data['school_website'] = ''
        
        # Handle optional numeric fields with defaults first
        if 'number_of_students' not in data or not str(data.get('number_of_students', '')).strip():
            data['number_of_students'] = '0'
        if 'number_of_teachers' not in data or not str(data.get('number_of_teachers', '')).strip():
            data['number_of_teachers'] = '0'
        
        # Validate required fields (excluding position and school_type as they're always set)
        required_fields = [
            'school_name', 'school_address', 'county_city',
            'school_contact_number', 'school_email', 'owner_full_name',
            'owner_email', 'owner_phone', 'username', 'password'
        ]
        
        # Check for missing required fields (excluding empty strings)
        missing_fields = []
        for field in required_fields:
            value = data.get(field, '')
            # Handle both string and non-string values
            if value is None or value == '' or (isinstance(value, str) and not value.strip()):
                missing_fields.append(field)
        
        if missing_fields:
            logger.error(f"Missing required fields: {missing_fields}")
            logger.error(f"Received data keys: {list(data.keys())}")
            logger.error(f"Data values: {[(k, v) for k, v in data.items() if k not in ['password', 'csrfmiddlewaretoken']]}")
            return JsonResponse({
                'success': False,
                'message': f'Missing required fields: {", ".join(missing_fields)}',
                'errors': {field: 'This field is required' for field in missing_fields},
                'debug': {
                    'missing_fields': missing_fields, 
                    'received_fields': list(data.keys()),
                    'content_type': request.content_type
                }
            }, status=400)
        
        # Validate username uniqueness
        if CustomUser.objects.filter(username=data['username']).exists():
            return JsonResponse({
                'success': False,
                'message': 'Username already exists',
                'errors': {'username': 'This username is already taken'}
            }, status=400)
        
        # Validate email uniqueness
        if CustomUser.objects.filter(email=data['owner_email']).exists():
            return JsonResponse({
                'success': False,
                'message': 'Email already registered',
                'errors': {'owner_email': 'This email is already registered'}
            }, status=400)
        
        # Create school registration (always college and director)
        registration = SchoolRegistration(
            school_name=data['school_name'],
            school_type='college',
            school_address=data['school_address'],
            county_city=data['county_city'],
            school_contact_number=data['school_contact_number'],
            school_email=data['school_email'],
            owner_full_name=data['owner_full_name'],
            owner_email=data['owner_email'],
            owner_phone=data['owner_phone'],
            position='director',
            number_of_students=int(data.get('number_of_students', 0) or 0),
            number_of_teachers=int(data.get('number_of_teachers', 0) or 0),
            school_website=data.get('school_website', '') or None,
        )
        
        # Handle file upload if present
        if 'school_logo' in request.FILES:
            registration.school_logo = request.FILES['school_logo']
        
        # Validate and save registration
        try:
            registration.full_clean()
            registration.save()
            
            # Create College from registration
            college = College(
                name=data['school_name'],
                address=data['school_address'],
                county=data['county_city'],
                email=data['school_email'],
                phone=data['school_contact_number'],
                principal_name=data['owner_full_name'],
                registration_status='pending',  # Requires approval
            )
            college.save()
            
            # Create director user account
            admin_user = CustomUser(
                username=data['username'],
                email=data['owner_email'],
                first_name=data['owner_full_name'].split()[0] if data['owner_full_name'] else '',
                last_name=' '.join(data['owner_full_name'].split()[1:]) if len(data['owner_full_name'].split()) > 1 else '',
                phone=data['owner_phone'],
                role='director',
                college=college,
                is_active=True,
            )
            admin_user.set_password(data['password'])
            admin_user.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Registration successful! Your account has been created. You can now login.',
                'registration_id': registration.id,
                'college_id': college.id
            }, status=201)
            
        except ValidationError as e:
            return JsonResponse({
                'success': False,
                'message': 'Validation error',
                'errors': e.message_dict
            }, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=500)


@login_required
@college_required
def college_landing_page(request, college_slug):
    """College landing page with section-based navigation"""
    # Redirect directors to director dashboard
    if request.user.is_director():
        return redirect('director_dashboard')
    
    college = request.user.college
    
    # Verify college exists and slug matches
    if not college:
        raise Http404("College not found")
    
    if college.get_slug() != college_slug:
        raise Http404("College not found")
    
    # Check if college is suspended
    college_is_suspended = (college.registration_status == 'inactive')
    
    # Add cache control headers to prevent caching
    response = render(request, 'education/college_landing.html', {
        'college': college,
        'user': request.user,
        'college_is_suspended': college_is_suspended,
        'timestamp': int(time.time())  # Add timestamp for cache busting
    })
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@login_required
@director_required
def director_dashboard(request):
    """Director dashboard with managerial access and analytics tabs"""
    main_college = request.user.college
    
    # Handle campus selection - default to main campus
    selected_campus_id = request.GET.get('campus_id')
    selected_campus = main_college
    
    # Get all colleges (main + branches) that director can manage
    all_colleges = [main_college]
    if main_college.is_main_college():
        all_colleges.extend(main_college.get_all_branches())
        # If campus_id is provided, validate and use it
        if selected_campus_id:
            try:
                campus = College.objects.get(id=selected_campus_id)
                # Verify it's either the main college or a branch
                if campus in all_colleges:
                    selected_campus = campus
            except College.DoesNotExist:
                pass
    
    # Use selected campus for all data filtering
    colleges_to_query = [selected_campus]
    
    # Handle POST requests for creating branches or users
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_branch':
            # Create a new branch college
            try:
                # Check if college can create more branches
                if not main_college.can_create_branch():
                    remaining = main_college.get_remaining_branches()
                    messages.error(request, f'Cannot create branch. Maximum branch limit ({main_college.max_branches}) reached. You have {remaining} remaining branches.')
                    return redirect('director_dashboard')
                
                branch = College.objects.create(
                    name=request.POST.get('name'),
                    email=request.POST.get('email'),
                    phone=request.POST.get('phone'),
                    address=request.POST.get('address'),
                    county=request.POST.get('county'),
                    principal_name=request.POST.get('principal_name'),
                    parent_college=main_college,
                    registration_status='active'  # Auto-approve branches created by director
                )
                messages.success(request, f'Branch college "{branch.name}" created successfully.')
            except Exception as e:
                messages.error(request, f'Error creating branch: {str(e)}')
            return redirect('director_dashboard')
        
        elif action == 'create_user':
            # Create a new user (Director can create Principal, Registrar, or Accountant)
            role = request.POST.get('role')
            allowed_roles = ['principal', 'registrar', 'accounts_officer']
            
            if role not in allowed_roles:
                messages.error(request, 'Invalid role. Director can only create Principal, Registrar, or Accountant.')
                return redirect('director_dashboard')
            
            try:
                password = request.POST.get('password')
                password_confirm = request.POST.get('password_confirm')
                
                if password != password_confirm:
                    messages.error(request, 'Passwords do not match.')
                    return redirect('director_dashboard')
                
                # Get college for user (can be main or branch)
                college_id = request.POST.get('college_id')
                user_college = main_college
                if college_id and college_id != str(main_college.id):
                    try:
                        user_college = College.objects.get(id=college_id, parent_college=main_college)
                    except College.DoesNotExist:
                        messages.error(request, 'Invalid college selected.')
                        return redirect('director_dashboard')
                
                # Check if username or email already exists
                if CustomUser.objects.filter(username=request.POST.get('username')).exists():
                    messages.error(request, 'Username already exists.')
                    return redirect('director_dashboard')
                
                if CustomUser.objects.filter(email=request.POST.get('email')).exists():
                    messages.error(request, 'Email already exists.')
                    return redirect('director_dashboard')
                
                user = CustomUser.objects.create_user(
                    username=request.POST.get('username'),
                    email=request.POST.get('email'),
                    password=password,
                    first_name=request.POST.get('first_name', ''),
                    last_name=request.POST.get('last_name', ''),
                    phone=request.POST.get('phone', ''),
                    role=role,
                    college=user_college
                )
                messages.success(request, f'User "{user.username}" created successfully.')
            except Exception as e:
                messages.error(request, f'Error creating user: {str(e)}')
            return redirect('director_dashboard')
    
    # Get current academic year for accounts analytics
    current_academic_year = selected_campus.current_academic_year or f"{timezone.now().year}/{timezone.now().year + 1}"
    current_semester = selected_campus.current_semester or 1
    
    # Calculate analytics for Principal tab (Academic Overview)
    principal_analytics = {
        'total_students': Student.objects.filter(college__in=colleges_to_query).count(),
        'active_students': Student.objects.filter(college__in=colleges_to_query, status='active').count(),
        'total_courses': CollegeCourse.objects.filter(college__in=colleges_to_query).count(),
        'total_units': CollegeUnit.objects.filter(college__in=colleges_to_query).count(),
        'total_lecturers': CustomUser.objects.filter(college__in=colleges_to_query, role='lecturer').count(),
        'total_enrollments': Enrollment.objects.filter(student__college__in=colleges_to_query).count(),
        'completed_results': Result.objects.filter(enrollment__student__college__in=colleges_to_query).count(),
    }
    
    # Calculate analytics for Registrar tab (Student Management)
    registrar_analytics = {
        'total_students': Student.objects.filter(college__in=colleges_to_query).count(),
        'active_students': Student.objects.filter(college__in=colleges_to_query, status='active').count(),
        'suspended_students': Student.objects.filter(college__in=colleges_to_query, status='suspended').count(),
        'deferred_students': Student.objects.filter(college__in=colleges_to_query, status='deferred').count(),
        'graduated_students': Student.objects.filter(college__in=colleges_to_query, status='graduated').count(),
        'new_students_this_month': Student.objects.filter(
            college__in=colleges_to_query,
            created_at__gte=timezone.now().replace(day=1)
        ).count(),
        'enrollments_this_semester': Enrollment.objects.filter(
            student__college__in=colleges_to_query,
            academic_year=current_academic_year,
            semester=current_semester
        ).count(),
    }
    
    # Calculate comprehensive accounts analytics (from accounts_dashboard)
    # Get active students in current semester
    active_students_in_semester = Student.objects.filter(
        college__in=colleges_to_query,
        status='active',
        enrollments__academic_year=current_academic_year,
        enrollments__semester=current_semester
    ).distinct().count()
    
    # Get all active students (for overall stats)
    total_active_students = Student.objects.filter(college__in=colleges_to_query, status='active').count()
    
    # Calculate total expected fees and outstanding using automatic calculation
    students = Student.objects.filter(college__in=colleges_to_query, status='active').select_related('course')
    total_expected = Decimal('0.00')
    total_paid_amount = Payment.objects.filter(
        student__college__in=colleges_to_query
    ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
    total_outstanding = Decimal('0.00')
    
    # Calculate expected fees for current semester only
    current_semester_expected = Decimal('0.00')
    current_semester_paid = Decimal('0.00')
    
    for student in students:
        fee_info = calculate_expected_fees(student)
        total_expected += fee_info['expected_total']
        student_payments = Payment.objects.filter(student=student).aggregate(
            total=Sum('amount_paid')
        )['total'] or Decimal('0.00')
        student_outstanding = fee_info['expected_total'] - student_payments
        if student_outstanding > 0:
            total_outstanding += student_outstanding
        
        # Calculate current semester fees
        semester_number = student.get_course_semester_number()
        if semester_number == current_semester:
            # Get fee breakdown for current semester
            fee_breakdown = student.get_fee_breakdown()
            if current_semester in fee_breakdown:
                current_semester_expected += fee_breakdown[current_semester]['amount']
    
    # Get payments for current semester
    current_semester_payments = Payment.objects.filter(
        student__college__in=colleges_to_query,
        semester_number=current_semester,
        academic_year=current_academic_year
    )
    current_semester_paid = current_semester_payments.aggregate(
        total=Sum('amount_paid')
    )['total'] or Decimal('0.00')
    
    # Calculate fee collection progress percentage
    if total_expected > 0:
        collection_progress = (total_paid_amount / total_expected) * 100
    else:
        collection_progress = 0
    
    # Current semester collection progress
    if current_semester_expected > 0:
        current_semester_progress = (current_semester_paid / current_semester_expected) * 100
    else:
        current_semester_progress = 0
    
    # Get payment data by semester for current academic year (for comparison)
    semester_payments_data = []
    semester_labels = []
    semester_amounts = []
    
    # Get all semesters in current academic year
    max_semesters = selected_campus.semesters_per_year or 2
    for sem in range(1, max_semesters + 1):
        sem_payments = Payment.objects.filter(
            student__college__in=colleges_to_query,
            semester_number=sem,
            academic_year=current_academic_year
        ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
        
        semester_labels.append(f'Semester {sem}')
        semester_amounts.append(float(sem_payments))
        semester_payments_data.append({
            'semester': sem,
            'amount': float(sem_payments),
            'count': Payment.objects.filter(
                student__college__in=colleges_to_query,
                semester_number=sem,
                academic_year=current_academic_year
            ).count()
        })
    
    # Calculate growth rate (comparing current semester with previous semester)
    growth_rate = 0
    growth_percentage = 0
    if current_semester > 1:
        previous_semester_paid = Payment.objects.filter(
            student__college__in=colleges_to_query,
            semester_number=current_semester - 1,
            academic_year=current_academic_year
        ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
        
        if previous_semester_paid > 0:
            growth_rate = float(current_semester_paid - previous_semester_paid)
            growth_percentage = (growth_rate / float(previous_semester_paid)) * 100
        elif current_semester_paid > 0:
            growth_percentage = 100  # 100% growth if previous was 0
    
    # Calculate projection for end of academic year
    total_academic_year_projected = Decimal('0.00')
    if current_semester_progress > 0 and current_semester <= max_semesters:
        remaining_semesters = max_semesters - current_semester
        if remaining_semesters > 0:
            avg_per_semester = current_semester_paid / current_semester
            total_academic_year_projected = current_semester_paid + (avg_per_semester * remaining_semesters)
        else:
            total_academic_year_projected = current_semester_paid
    
    # Get payment trends over last 6 months for chart
    from datetime import timedelta
    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_payments = []
    monthly_labels = []
    
    for i in range(6):
        month_start = six_months_ago + timedelta(days=30 * i)
        month_end = month_start + timedelta(days=30)
        month_payments = Payment.objects.filter(
            student__college__in=colleges_to_query,
            date_paid__gte=month_start,
            date_paid__lt=month_end
        ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
        monthly_payments.append(float(month_payments))
        monthly_labels.append(month_start.strftime('%b %Y'))
    
    # Payment method breakdown
    payment_methods = Payment.objects.filter(
        student__college__in=colleges_to_query
    ).values('payment_method').annotate(
        total=Sum('amount_paid'),
        count=Count('id')
    ).order_by('-total')
    
    payment_method_data = []
    payment_method_labels = []
    payment_method_amounts = []
    for method in payment_methods:
        payment_method_labels.append(method['payment_method'].replace('_', ' ').title())
        payment_method_amounts.append(float(method['total']))
        payment_method_data.append({
            'method': method['payment_method'],
            'amount': float(method['total']),
            'count': method['count']
        })
    
    # Recent payments
    recent_payments = Payment.objects.filter(
        student__college__in=colleges_to_query
    ).order_by('-date_paid')[:10]
    
    # Accounts analytics for Accountant tab (Financial Overview)
    accountant_analytics = {
        'total_expected': total_expected,
        'total_paid': total_paid_amount,
        'total_outstanding': total_outstanding,
        'collection_rate': collection_progress,
        'active_students': total_active_students,
        'payments_this_month': Payment.objects.filter(
            student__college__in=colleges_to_query,
            date_paid__gte=timezone.now().replace(day=1)
        ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00'),
        'total_payments_count': Payment.objects.filter(student__college__in=colleges_to_query).count(),
    }
    
    # Get accounts data for other tabs
    from accounts.models import Department, FeeStructure, StudentInvoice
    
    departments = Department.objects.filter(college=selected_campus).order_by('department_name')
    fee_structures = FeeStructure.objects.filter(
        college=selected_campus,
        is_current_version=True
    ).select_related('course').order_by('course', 'semester_number', 'fee_type')
    
    # Group fee structures by course and semester
    grouped_fees = {}
    for fee in fee_structures:
        if fee.semester_number:
            key = f"{fee.course.id}_{fee.semester_number}"
            if key not in grouped_fees:
                grouped_fees[key] = {
                    'course': fee.course,
                    'semester_number': fee.semester_number,
                    'fees': [],
                    'total': Decimal('0.00'),
                    'version': fee.version_number
                }
            grouped_fees[key]['fees'].append(fee)
            grouped_fees[key]['total'] += fee.amount
    
    # Get payments list (for viewing, not recording)
    payments_list = Payment.objects.filter(
        student__college__in=colleges_to_query
    ).select_related('student').order_by('-date_paid')[:20]
    
    # Get branch colleges
    branch_colleges = main_college.branch_colleges.all() if main_college.is_main_college() else []
    
    # Get users by role
    principals = CustomUser.objects.filter(college__in=all_colleges, role='principal')
    registrars = CustomUser.objects.filter(college__in=all_colleges, role='registrar')
    accountants = CustomUser.objects.filter(college__in=all_colleges, role='accounts_officer')
    
    context = {
        'college': selected_campus,
        'main_college': main_college,
        'selected_campus': selected_campus,
        'selected_campus_id': selected_campus.id,
        'branch_colleges': branch_colleges,
        'all_colleges': all_colleges,
        'principal_analytics': principal_analytics,
        'registrar_analytics': registrar_analytics,
        'accountant_analytics': accountant_analytics,
        'principals': principals,
        'registrars': registrars,
        'accountants': accountants,
        # Accounts dashboard analytics
        'current_academic_year': current_academic_year,
        'current_semester': current_semester,
        'total_expected': total_expected,
        'total_paid_amount': total_paid_amount,
        'total_outstanding': total_outstanding,
        'collection_progress': collection_progress,
        'current_semester_expected': current_semester_expected,
        'current_semester_paid': current_semester_paid,
        'current_semester_progress': current_semester_progress,
        'active_students_in_semester': active_students_in_semester,
        'total_active_students': total_active_students,
        'semester_payments_data': semester_payments_data,
        'semester_labels': semester_labels,
        'semester_amounts': semester_amounts,
        'growth_rate': growth_rate,
        'growth_percentage': growth_percentage,
        'total_academic_year_projected': total_academic_year_projected,
        'monthly_payments': monthly_payments,
        'monthly_labels': monthly_labels,
        'payment_method_data': payment_method_data,
        'payment_method_labels': payment_method_labels,
        'payment_method_amounts': payment_method_amounts,
        'recent_payments': recent_payments,
        # Accounts data for other tabs
        'departments': departments,
        'grouped_fees': grouped_fees.values(),
        'payments_list': payments_list,
        # Check if college is suspended
        'college_is_suspended': getattr(request, 'college_is_suspended', False) or (main_college.registration_status == 'inactive'),
        'college': main_college,
    }
    
    # Get payment config and latest payment if college is suspended
    if main_college.registration_status == 'inactive':
        from superadmin.models import CollegePaymentConfig, CollegePayment
        try:
            payment_config = CollegePaymentConfig.objects.get(college=main_college, status='active')
            context['payment_config'] = payment_config
            latest_payment = CollegePayment.objects.filter(college=main_college).order_by('-created_at').first()
            context['latest_payment'] = latest_payment
        except CollegePaymentConfig.DoesNotExist:
            context['payment_config'] = None
            context['latest_payment'] = None
    
    return render(request, 'education/director/dashboard.html', context)


@login_required
@director_required
def edit_user(request, user_id):
    """Edit user details - Director only"""
    main_college = request.user.college
    
    # Get all colleges (main + branches) that director can manage
    all_colleges = [main_college]
    if main_college.is_main_college():
        all_colleges.extend(main_college.get_all_branches())
    
    # Get the user to edit - must belong to one of director's colleges
    try:
        user = CustomUser.objects.get(id=user_id, college__in=all_colleges)
    except CustomUser.DoesNotExist:
        messages.error(request, 'User not found or you do not have permission to edit this user.')
        return redirect('director_dashboard')
    
    # Ensure user is not a director (directors cannot edit other directors)
    if user.is_director():
        messages.error(request, 'You cannot edit director accounts.')
        return redirect('director_dashboard')
    
    # Ensure user is one of the roles director can manage
    allowed_roles = ['principal', 'registrar', 'accounts_officer']
    if user.role not in allowed_roles:
        messages.error(request, 'You can only edit Principal, Registrar, or Accountant accounts.')
        return redirect('director_dashboard')
    
    # Handle POST request - update user
    if request.method == 'POST':
        try:
            # Update basic fields
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name = request.POST.get('last_name', '').strip()
            user.email = request.POST.get('email', '').strip()
            user.phone = request.POST.get('phone', '').strip()
            
            # Update role (must be one of allowed roles)
            new_role = request.POST.get('role', user.role)
            if new_role in allowed_roles:
                user.role = new_role
            
            # Update college (must be one of director's colleges)
            college_id = request.POST.get('college_id')
            if college_id:
                try:
                    new_college = College.objects.get(id=college_id)
                    if new_college in all_colleges:
                        user.college = new_college
                except College.DoesNotExist:
                    pass
            
            # Update account status
            is_active = request.POST.get('is_active') == 'on'
            user.is_active = is_active
            
            # Check for email uniqueness (if changed)
            if user.email:
                existing_user = CustomUser.objects.filter(email=user.email).exclude(id=user.id).first()
                if existing_user:
                    messages.error(request, 'Email already exists for another user.')
                    return redirect('director_dashboard')
            
            user.save()
            messages.success(request, f'User "{user.get_full_name() or user.username}" updated successfully.')
            
            # Return JSON for AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'User updated successfully.',
                    'user': {
                        'id': user.id,
                        'full_name': user.get_full_name() or user.username,
                        'email': user.email,
                        'role': user.get_role_display(),
                        'college': user.college.name if user.college else '',
                        'is_active': user.is_active
                    }
                })
            
            return redirect('director_dashboard')
        except Exception as e:
            error_msg = f'Error updating user: {str(e)}'
            messages.error(request, error_msg)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            
            return redirect('director_dashboard')
    
    # Handle GET request - return user data as JSON for modal
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'phone': user.phone or '',
                'role': user.role,
                'college_id': user.college.id if user.college else None,
                'is_active': user.is_active,
            },
            'colleges': [
                {'id': c.id, 'name': c.name}
                for c in all_colleges
            ]
        })
    
    # If not AJAX, redirect to dashboard
    return redirect('director_dashboard')


@login_required
@director_required
@csrf_exempt
@require_http_methods(["POST"])
def director_initiate_payment(request):
    """Director - Initiate M-Pesa payment for college subscription"""
    college = request.user.college
    
    # Check if college is suspended
    if college.registration_status != 'inactive':
        return JsonResponse({
            'success': False,
            'error': 'College is not suspended. Payment not required.'
        }, status=400)
    
    try:
        data = json.loads(request.body)
        phone_number = data.get('phone_number', '').strip()
        
        # Get payment config
        try:
            config = CollegePaymentConfig.objects.get(college=college, status='active')
        except CollegePaymentConfig.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Payment configuration not found. Please contact Super Admin.'
            }, status=400)
        
        # Get Daraja settings (use college's Daraja settings)
        try:
            daraja_settings = DarajaSettings.objects.get(college=college, is_active=True)
        except DarajaSettings.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'M-Pesa payments are not configured for this college. Please configure in Accounts Settings.'
            }, status=400)
        
        # Validate phone number
        if not phone_number:
            return JsonResponse({
                'success': False,
                'error': 'Phone number is required'
            }, status=400)
        
        # Create payment record
        payment = CollegePayment.objects.create(
            college=college,
            config=config,
            amount=config.amount,
            status='pending',
            phone_number=phone_number
        )
        
        # Initiate STK Push using DarajaService
        try:
            daraja_service = DarajaService(college)
            
            # Use account reference from config
            account_reference = config.get_account_reference()
            
            # Initiate STK Push (we'll need to modify DarajaService to support college payments)
            # For now, we'll use a workaround by creating a temporary student-like object
            # Actually, we need to extend DarajaService or create a new method
            
            # Use the paybill from config, but credentials from DarajaSettings
            # Note: We use DarajaService but need to ensure it uses the correct paybill
            # The DarajaService uses DarajaSettings which has its own paybill
            # For college payments, we should use the paybill from CollegePaymentConfig
            # But DarajaService is tied to DarajaSettings, so we'll use what's configured
            
            result = daraja_service.initiate_stk_push_for_college(
                amount=config.amount,
                phone_number=phone_number,
                account_reference=account_reference,
                transaction_desc=f"College Payment - {college.name}"
            )
            
            if result.get('success'):
                # Update payment with request IDs
                payment.merchant_request_id = result.get('merchant_request_id')
                payment.checkout_request_id = result.get('checkout_request_id')
                payment.status = 'processing'
                payment.save()
                
                return JsonResponse({
                    'success': True,
                    'message': result.get('response_description', 'Payment request sent successfully'),
                    'payment_id': payment.id,
                    'merchant_request_id': result.get('merchant_request_id'),
                    'checkout_request_id': result.get('checkout_request_id')
                })
            else:
                payment.status = 'failed'
                payment.notes = result.get('error', 'Payment initiation failed')
                payment.save()
                
                return JsonResponse({
                    'success': False,
                    'error': result.get('error', 'Failed to initiate payment')
                }, status=400)
                
        except ValueError as e:
            payment.status = 'failed'
            payment.notes = str(e)
            payment.save()
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
        except Exception as e:
            payment.status = 'failed'
            payment.notes = f'Payment initiation failed: {str(e)}'
            payment.save()
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


@login_required
def logout_view(request):
    """College Admin logout - always redirects to admin login"""
    from django.contrib.auth import logout
    
    # Handle both GET and POST requests
    if request.method == 'POST' or request.method == 'GET':
        logout(request)
        
        # If it's an AJAX request, return JSON
        if request.headers.get('Content-Type') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({'success': True, 'message': 'Logged out successfully'})
        
        # Always redirect to admin login
        return redirect('admin_login')
    
    return redirect('admin_login')




@login_required
@super_admin_required
def college_list(request):
    """List all colleges (Super Admin only)"""
    colleges = College.objects.all().order_by('-created_at')
    
    # Filtering
    status_filter = request.GET.get('status')
    if status_filter:
        colleges = colleges.filter(registration_status=status_filter)
    
    # Search
    search = request.GET.get('search')
    if search:
        colleges = colleges.filter(
            Q(name__icontains=search) |
            Q(email__icontains=search) |
            Q(county__icontains=search)
        )
    
    paginator = Paginator(colleges, 20)
    page = request.GET.get('page')
    colleges = paginator.get_page(page)
    
    return render(request, 'education/colleges/list.html', {'colleges': colleges})


@login_required
@super_admin_required
def college_detail(request, pk):
    """View college details (Super Admin only)"""
    college = get_object_or_404(College, pk=pk)
    
    stats = {
        'students': Student.objects.filter(college=college).count(),
        'courses': CollegeCourse.objects.filter(college=college).count(),
        'units': CollegeUnit.objects.filter(college=college).count(),
        'staff': CustomUser.objects.filter(college=college).count(),
    }
    
    return render(request, 'education/colleges/detail.html', {
        'college': college,
        'stats': stats
    })


@login_required
@super_admin_required
def college_approve(request, pk):
    """Approve or deactivate college (Super Admin only)"""
    college = get_object_or_404(College, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            college.registration_status = 'active'
            messages.success(request, f'{college.name} has been approved.')
        elif action == 'deactivate':
            college.registration_status = 'inactive'
            messages.success(request, f'{college.name} has been deactivated.')
        college.save()
    
    return redirect('college_detail', pk=pk)


def college_register(request):
    """College registration (public)"""
    if request.method == 'POST':
        form = CollegeRegistrationForm(request.POST)
        if form.is_valid():
            college = form.save(commit=False)
            college.registration_status = 'pending'
            college.save()
            messages.success(request, 'College registration submitted. Awaiting approval.')
            return redirect('login')
    else:
        form = CollegeRegistrationForm()
    
    return render(request, 'education/colleges/register.html', {'form': form})


@login_required
@college_admin_required
def user_list(request):
    """List users for college"""
    college = request.user.college
    users = CustomUser.objects.filter(college=college).exclude(role='super_admin')
    
    role_filter = request.GET.get('role')
    if role_filter:
        users = users.filter(role=role_filter)
    
    search = request.GET.get('search')
    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )
    
    paginator = Paginator(users, 20)
    page = request.GET.get('page')
    users = paginator.get_page(page)
    
    return render(request, 'education/users/list.html', {'users': users})


@login_required
@college_admin_required
def user_create(request):
    """Create new user with hierarchical permissions"""
    current_user = request.user
    
    # Determine allowed roles based on user's role
    if current_user.is_director():
        allowed_roles = ['principal', 'registrar', 'accounts_officer']
    elif current_user.is_principal():
        allowed_roles = ['lecturer', 'reception']
    else:
        # For other roles, use default behavior (can create lecturers)
        allowed_roles = ['lecturer']
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            role = form.cleaned_data['role']
            
            # Enforce hierarchical permissions
            if role not in allowed_roles:
                messages.error(request, f'You do not have permission to create users with role "{role}".')
                form = UserRegistrationForm()
                # Filter role choices
                role_choices = [(r, label) for r, label in CustomUser.ROLE_CHOICES if r in allowed_roles]
                form.fields['role'].choices = role_choices
                return render(request, 'education/users/create.html', {'form': form})
            
            user = form.save(commit=False)
            user.college = request.user.college
            user.set_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, f'User {user.username} created successfully.')
            return redirect('user_list')
    else:
        form = UserRegistrationForm()
        # Filter role choices based on user's permissions
        role_choices = [(r, label) for r, label in CustomUser.ROLE_CHOICES if r in allowed_roles]
        form.fields['role'].choices = role_choices
    
    return render(request, 'education/users/create.html', {'form': form})


@login_required
@college_admin_required
def student_list(request):
    """List students"""
    college = request.user.college
    students = Student.objects.filter(college=college)
    
    # Filters
    course_filter = request.GET.get('course')
    if course_filter:
        students = students.filter(course_id=course_filter)
    
    year_filter = request.GET.get('year')
    if year_filter:
        students = students.filter(year_of_study=year_filter)
    
    search = request.GET.get('search')
    if search:
        students = students.filter(
            Q(admission_number__icontains=search) |
            Q(full_name__icontains=search) |
            Q(email__icontains=search)
        )
    
    paginator = Paginator(students, 20)
    page = request.GET.get('page')
    students = paginator.get_page(page)
    
    courses = CollegeCourse.objects.filter(college=college)
    
    return render(request, 'education/students/list.html', {
        'students': students,
        'courses': courses
    })


@login_required
@college_admin_required
def student_create(request):
    """Create new student"""
    college = request.user.college
    if request.method == 'POST':
        form = StudentForm(request.POST, college=college)
        if form.is_valid():
            student = form.save(commit=False)
            student.college = college
            student.save()
            messages.success(request, f'Student {student.admission_number} registered successfully.')
            return redirect('student_list')
    else:
        form = StudentForm(college=college)
    
    return render(request, 'education/students/create.html', {'form': form})


@login_required
@college_admin_required
@ensure_college_access(Student)
def student_detail(request, pk):
    """View student details"""
    student = get_object_or_404(Student, pk=pk)
    
    # STRICT: Verify access - super admin cannot access
    if request.user.is_super_admin():
        from django.contrib import messages
        messages.error(request, 'Super Admin cannot access individual college data.')
        return redirect('superadmin:dashboard')
    
    if student.college != request.user.college:
        raise Http404()
    
    enrollments = Enrollment.objects.filter(student=student).select_related('unit', 'result')
    
    return render(request, 'education/students/detail.html', {
        'student': student,
        'enrollments': enrollments
    })


@login_required
@college_admin_required
def course_list(request):
    """List courses"""
    college = request.user.college
    courses = CollegeCourse.objects.filter(college=college)
    
    search = request.GET.get('search')
    if search:
        courses = courses.filter(name__icontains=search)
    
    paginator = Paginator(courses, 20)
    page = request.GET.get('page')
    courses = paginator.get_page(page)
    
    return render(request, 'education/courses/list.html', {'courses': courses})


@login_required
@college_admin_required
def course_create(request):
    """Create new course"""
    if request.method == 'POST':
        form = CollegeCourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.college = request.user.college
            course.save()
            messages.success(request, f'Course {course.name} created successfully.')
            return redirect('course_list')
    else:
        form = CollegeCourseForm()
    
    return render(request, 'education/courses/create.html', {'form': form})


@login_required
@college_admin_required
def unit_list(request):
    """List units"""
    college = request.user.college
    units = CollegeUnit.objects.filter(college=college)
    
    # Filters
    semester_filter = request.GET.get('semester')
    if semester_filter:
        units = units.filter(semester=semester_filter)
    
    lecturer_filter = request.GET.get('lecturer')
    if lecturer_filter:
        units = units.filter(assigned_lecturer_id=lecturer_filter)
    
    search = request.GET.get('search')
    if search:
        units = units.filter(
            Q(code__icontains=search) |
            Q(name__icontains=search)
        )
    
    paginator = Paginator(units, 20)
    page = request.GET.get('page')
    units = paginator.get_page(page)
    
    lecturers = CustomUser.objects.filter(college=college, role='lecturer')
    
    return render(request, 'education/units/list.html', {
        'units': units,
        'lecturers': lecturers
    })


@login_required
@college_admin_required
def unit_create(request):
    """Create new unit"""
    college = request.user.college
    if request.method == 'POST':
        form = CollegeUnitForm(request.POST, college=college)
        if form.is_valid():
            unit = form.save(commit=False)
            unit.college = college
            unit.save()
            messages.success(request, f'Unit {unit.code} created successfully.')
            return redirect('unit_list')
    else:
        form = CollegeUnitForm(college=college)
        form.fields['assigned_lecturer'].queryset = CustomUser.objects.filter(
            college=college, role='lecturer'
        )
    
    return render(request, 'education/units/create.html', {'form': form})


@login_required
@lecturer_required
def enrollment_list(request):
    """List enrollments"""
    college = request.user.college
    enrollments = Enrollment.objects.filter(unit__college=college)
    
    # Lecturer sees only their assigned units
    if request.user.is_lecturer():
        enrollments = enrollments.filter(unit__assigned_lecturer=request.user)
    
    # Filters
    unit_filter = request.GET.get('unit')
    if unit_filter:
        enrollments = enrollments.filter(unit_id=unit_filter)
    
    year_filter = request.GET.get('year')
    if year_filter:
        enrollments = enrollments.filter(academic_year=year_filter)
    
    paginator = Paginator(enrollments, 20)
    page = request.GET.get('page')
    enrollments = paginator.get_page(page)
    
    units = CollegeUnit.objects.filter(college=college)
    if request.user.is_lecturer():
        units = units.filter(assigned_lecturer=request.user)
    
    return render(request, 'education/enrollments/list.html', {
        'enrollments': enrollments,
        'units': units
    })


@login_required
@college_admin_required
def enrollment_create(request):
    """Create new enrollment"""
    college = request.user.college
    if request.method == 'POST':
        form = EnrollmentForm(request.POST, college=college)
        if form.is_valid():
            enrollment = form.save()
            messages.success(request, 'Student enrolled successfully.')
            return redirect('enrollment_list')
    else:
        form = EnrollmentForm(college=college)
        form.fields['student'].queryset = Student.objects.filter(college=college)
        form.fields['unit'].queryset = CollegeUnit.objects.filter(college=college)
    
    return render(request, 'education/enrollments/create.html', {'form': form})


@login_required
@lecturer_required
def result_list(request):
    """List results"""
    college = request.user.college
    enrollments = Enrollment.objects.filter(unit__college=college)
    
    # Lecturer sees only their assigned units
    if request.user.is_lecturer():
        enrollments = enrollments.filter(unit__assigned_lecturer=request.user)
    
    # Filter by unit
    unit_filter = request.GET.get('unit')
    if unit_filter:
        enrollments = enrollments.filter(unit_id=unit_filter)
    
    # Filter by academic year (default to current academic year if not explicitly set)
    # Check if 'academic_year' is in GET params (even if empty) vs not present at all
    if 'academic_year' in request.GET:
        academic_year_filter = request.GET.get('academic_year') or None
    else:
        # Not in URL at all - use default
        academic_year_filter = college.current_academic_year if college.current_academic_year else None
    
    if academic_year_filter:
        enrollments = enrollments.filter(academic_year=academic_year_filter)
    
    # Filter by semester (default to current semester if not explicitly set)
    if 'semester' in request.GET:
        semester_filter = request.GET.get('semester') or None
    else:
        # Not in URL at all - use default
        semester_filter = str(college.current_semester) if college.current_semester else None
    
    if semester_filter:
        try:
            semester_filter_int = int(semester_filter)
            enrollments = enrollments.filter(semester=semester_filter_int)
        except ValueError:
            pass
    
    # Get results
    results = []
    for enrollment in enrollments:
        result, created = Result.objects.get_or_create(enrollment=enrollment)
        results.append({
            'enrollment': enrollment,
            'result': result,
            'can_edit': request.user.is_lecturer() and enrollment.unit.assigned_lecturer == request.user
        })
    
    units = CollegeUnit.objects.filter(college=college)
    if request.user.is_lecturer():
        units = units.filter(assigned_lecturer=request.user)
    
    # Get academic year choices for dropdown
    academic_year_choices = college.get_academic_year_choices(years_before=2, years_after=3) if college else []
    
    # Get semester choices for dropdown
    semester_choices = college.get_semester_choices() if college else [(1, 'Semester 1'), (2, 'Semester 2'), (3, 'Semester 3')]
    
    return render(request, 'education/results/list.html', {
        'results': results,
        'units': units,
        'academic_year_choices': academic_year_choices,
        'semester_choices': semester_choices,
        'selected_academic_year': academic_year_filter if academic_year_filter else '',
        'selected_semester': semester_filter if semester_filter else '',
        'current_academic_year': college.current_academic_year or '',
        'current_semester': college.current_semester or ''
    })


@login_required
@lecturer_required
def result_edit(request, enrollment_id):
    """Edit result (Lecturer only for assigned units)"""
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    
    # Verify lecturer has access
    if request.user.is_lecturer():
        if enrollment.unit.assigned_lecturer != request.user:
            raise PermissionDenied("You can only edit results for your assigned units.")
    
    # Build redirect URL with filters preserved
    def get_redirect_url():
        params = []
        if request.GET.get('academic_year'):
            params.append(f"academic_year={request.GET.get('academic_year')}")
        if request.GET.get('semester'):
            params.append(f"semester={request.GET.get('semester')}")
        if request.GET.get('unit'):
            params.append(f"unit={request.GET.get('unit')}")
        query_string = '&'.join(params)
        return f"{reverse('result_list')}{'?' + query_string if query_string else ''}"
    
    if request.method == 'POST':
        result, created = Result.objects.get_or_create(enrollment=enrollment)
        form = ResultForm(request.POST, instance=result)
        if form.is_valid():
            result = form.save(commit=False)
            result.enrollment = enrollment
            result.entered_by = request.user
            result.save()
            messages.success(request, 'Results updated successfully.')
            return redirect(get_redirect_url())
    else:
        result, created = Result.objects.get_or_create(enrollment=enrollment)
        form = ResultForm(instance=result)
    
    return render(request, 'education/results/edit.html', {
        'form': form,
        'enrollment': enrollment,
        'return_url': get_redirect_url()
    })


@login_required
@college_admin_required
def announcements_list(request):
    """List announcements (College Admin only)"""
    college = request.user.college
    return render(request, 'admin/announcements.html', {
        'college': college
    })


# ============================================
# Student Portal Views
# ============================================

def student_login_page(request, college_slug):
    """Student login page"""
    college = get_college_from_slug(college_slug)
    if not college:
        raise Http404("College not found")
    
    # If already logged in, redirect to dashboard
    if request.session.get('student_id'):
        try:
            student = Student.objects.get(pk=request.session.get('student_id'), college=college)
            return redirect('student_dashboard', college_slug=college_slug)
        except Student.DoesNotExist:
            request.session.flush()
    
    error = None
    if request.method == 'POST':
        admission_number = request.POST.get('admission_number', '').strip()
        password = request.POST.get('password', '')
        
        if admission_number:
            try:
                student = Student.objects.get(
                    admission_number=admission_number,
                    college=college
                )
                
                # Check student status first
                if student.is_graduated():
                    error = 'Congratulations! You have successfully graduated. Your portal access has been deactivated.'
                elif student.is_suspended():
                    error = 'Your account has been suspended. Please contact your college administration.'
                elif student.is_deferred():
                    error = 'Your studies have been deferred. Please contact your college administration for more information.'
                elif not student.is_active():
                    error = 'Your account is not active. Please contact your college administration.'
                # Check password if set, otherwise allow login without password (initial setup)
                elif student.has_usable_password():
                    if not student.check_password(password):
                        error = 'Invalid admission number or password.'
                    else:
                        # Login successful
                        request.session['student_id'] = student.id
                        request.session['student_college_id'] = college.id
                        return redirect('student_dashboard', college_slug=college_slug)
                else:
                    # No password set, allow login and set password
                    if password:
                        # Set password for first time
                        student.set_password(password)
                        request.session['student_id'] = student.id
                        request.session['student_college_id'] = college.id
                        return redirect('student_dashboard', college_slug=college_slug)
                    else:
                        error = 'Please set a password for your account.'
            except Student.DoesNotExist:
                error = 'Invalid admission number or password.'
        else:
            error = 'Please enter your admission number.'
    
    return render(request, 'education/student/login.html', {
        'college': college,
        'error': error
    })


@student_required
def student_dashboard_page(request, college_slug):
    """Student dashboard page"""
    student = request.student
    college = request.verified_college
    
    # Show congratulations page for graduated students
    if student.is_graduated():
        return render(request, 'education/student/graduated.html', {
            'student': student,
            'college': college
        })
    
    # Compute current semester with fallback
    current_semester = student.current_semester or student.get_current_semester() or None
    
    # Calculate fee information
    total_expected = student.get_total_expected_fees()
    total_paid = student.get_total_payments()
    balance = student.get_balance()
    fee_breakdown = student.get_fee_breakdown()
    semester_number = student.get_course_semester_number()
    
    # Normal dashboard for active students
    return render(request, 'education/student/dashboard.html', {
        'student': student,
        'college': college,
        'current_semester': current_semester,
        'total_expected': total_expected,
        'total_paid': total_paid,
        'balance': balance,
        'fee_breakdown': fee_breakdown,
        'semester_number': semester_number
    })


@student_required
def student_timetable_view(request, college_slug):
    """Student view - can only view their own course timetable"""
    from timetable.views import build_timetable_table
    from timetable.models import TimetableRun
    
    student = request.student
    college = request.verified_college
    
    if not student.course:
        messages.info(request, 'You are not enrolled in any course yet.')
        return redirect('student_dashboard', college_slug=college_slug)
    
    # Get published timetable for student's course
    active_timetable = TimetableRun.objects.filter(
        college=college,
        course=student.course,
        status='published'
    ).order_by('-published_at').first()
    
    timetable_data = None
    if active_timetable:
        timetable_data = build_timetable_table(active_timetable)
    
    context = {
        'college': college,
        'student': student,
        'active_timetable': active_timetable,
        'timetable_data': timetable_data,
    }
    return render(request, 'timetable/student_timetable.html', context)


def student_logout_view(request, college_slug):
    """Student logout handler"""
    college = get_college_from_slug(college_slug)
    if not college:
        raise Http404("College not found")
    
    # Clear student session
    request.session.flush()
    
    # Redirect to login
    return redirect('student_login', college_slug=college_slug)


@student_required
def student_semester_signin_page(request, college_slug):
    """Student semester sign-in page"""
    student = request.student
    college = request.verified_college
    
    return render(request, 'education/student/semester_signin.html', {
        'student': student,
        'college': college
    })


@student_required
def student_signin_history_page(request, college_slug):
    """Student sign-in history page"""
    student = request.student
    college = request.verified_college
    
    # Get sign-in history
    signin_history = StudentSemesterSignIn.objects.filter(student=student).order_by('-signed_in_at')
    
    return render(request, 'education/student/signin_history.html', {
        'student': student,
        'college': college,
        'signin_history': signin_history
    })
