"""
Super Admin Views
Handles all Super Admin functionality - completely separate from College Admin
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.utils.text import slugify
from functools import wraps
import json

from education.models import College, CustomUser, Student, CollegeCourse, CollegeUnit, SchoolRegistration, GlobalCourse, GlobalUnit
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import CollegePaymentConfig, CollegePayment
from accounts.models import DarajaSettings
from accounts.daraja_service import DarajaService
import json


def superadmin_login_required(view_func):
    """Custom login_required decorator that redirects to superadmin login instead of admin login"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Redirect to superadmin login with next parameter
            from django.urls import reverse
            login_url = reverse('superadmin:login')
            path = request.get_full_path()
            # Avoid redirect loop - don't add next if already going to login
            if '/superadmin/login' not in path:
                return redirect(f'{login_url}?next={path}')
            else:
                return redirect(login_url)
        # If authenticated but not super admin, redirect to appropriate page
        if not request.user.is_super_admin():
            if hasattr(request.user, 'college') and request.user.college:
                return redirect('college_landing', college_slug=request.user.college.get_slug())
            else:
                return redirect('admin_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def superadmin_login(request):
    """Super Admin login page - uses same template as college admin"""
    # Redirect if already authenticated
    if request.user.is_authenticated:
        if request.user.is_super_admin():
            # Check for next parameter to redirect to intended page
            next_url = request.GET.get('next', None)
            # Avoid redirect loop - don't redirect to login page itself
            if next_url and next_url.startswith('/superadmin/') and '/superadmin/login' not in next_url:
                return redirect(next_url)
            return redirect('superadmin:dashboard')
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
            if user.is_super_admin():
                login(request, user)
                messages.success(request, f'Welcome, {user.username}!')
                # Check for next parameter to redirect to intended page
                next_url = request.POST.get('next') or request.GET.get('next', None)
                # Avoid redirect loop - don't redirect to login page itself
                if next_url and next_url.startswith('/superadmin/') and '/superadmin/login' not in next_url:
                    return redirect(next_url)
                return redirect('superadmin:dashboard')
            else:
                messages.error(request, 'Access denied. Super Admin access required.')
                return render(request, 'admin/login.html', {'error': 'Access denied. Super Admin access required.'})
        else:
            return render(request, 'admin/login.html', {'error': 'Invalid username or password.'})

    return render(request, 'admin/login.html')


@superadmin_login_required
def superadmin_dashboard(request):
    """Super Admin Dashboard - system-wide overview"""
    user = request.user
    
    # Calculate total departments (unique course names across all colleges)
    total_departments = CollegeCourse.objects.values('name').distinct().count()
    
    # Get colleges statistics
    total_colleges = College.objects.count()
    active_colleges = College.objects.filter(registration_status='active').count()
    pending_colleges = College.objects.filter(registration_status='pending').count()
    suspended_colleges = College.objects.filter(registration_status='inactive').count()
    
    # Calculate colleges added this month
    now = timezone.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    colleges_this_month = College.objects.filter(created_at__gte=start_of_month).count()
    
    # Get recent colleges (last 10)
    recent_colleges = College.objects.select_related().order_by('-created_at')[:10]
    
    # Get recent school registrations (pending approvals)
    recent_registrations = SchoolRegistration.objects.filter(status='pending').order_by('-created_at')[:10]
    
    # Calculate student distribution by college
    student_distribution = Student.objects.values('college__name').annotate(
        student_count=Count('id')
    ).order_by('-student_count')[:10]
    
    # Calculate colleges growth by month (last 12 months)
    colleges_growth_data = []
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
        colleges_growth_data.append({
            'month': month_start.strftime('%b %Y'),
            'count': count
        })
    
    # Convert to JSON for JavaScript
    colleges_growth_json = json.dumps(colleges_growth_data)
    student_distribution_json = json.dumps(list(student_distribution))
    
    context = {
        'user': user,
        'total_colleges': total_colleges,
        'active_colleges': active_colleges,
        'pending_colleges': pending_colleges,
        'suspended_colleges': suspended_colleges,
        'total_students': Student.objects.count(),
        'total_lecturers': CustomUser.objects.filter(role='lecturer').count(),
        'total_departments': total_departments,
        'colleges_this_month': colleges_this_month,
        'recent_colleges': recent_colleges,
        'recent_registrations': recent_registrations,
        'colleges_growth': colleges_growth_json,
        'student_distribution': student_distribution_json,
    }
    
    return render(request, 'superadmin/dashboard.html', context)


@superadmin_login_required
def superadmin_colleges(request):
    """Super Admin - Colleges Management Page"""
    user = request.user
    
    context = {
        'user': user,
    }
    
    return render(request, 'superadmin/colleges.html', context)


@superadmin_login_required
def superadmin_academic(request):
    """Super Admin - Academic Management Page (Global Units and Courses)"""
    user = request.user
    
    # Handle POST requests for creating global units and courses
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_global_unit':
            code = request.POST.get('code', '').strip().upper()
            name = request.POST.get('name', '').strip()
            
            if not code or not name:
                messages.error(request, 'Unit code and name are required.')
            else:
                # Check if unit code already exists
                if GlobalUnit.objects.filter(code=code).exists():
                    messages.error(request, f'A unit with code {code} already exists.')
                else:
                    GlobalUnit.objects.create(code=code, name=name)
                    messages.success(request, f'Global unit {code} - {name} created successfully.')
        
        elif action == 'create_global_course':
            name = request.POST.get('name', '').strip()
            level = request.POST.get('level', '').strip()
            category = request.POST.get('category', '').strip()
            
            if not name or not level or not category:
                messages.error(request, 'Course name, level, and category are required.')
            else:
                GlobalCourse.objects.create(name=name, level=level, category=category)
                messages.success(request, f'Global course {name} created successfully.')
        
        return redirect('superadmin:academic')
    
    # Get all global units and courses for display
    global_units = GlobalUnit.objects.all().order_by('code')
    global_courses = GlobalCourse.objects.all().order_by('name')
    
    context = {
        'user': user,
        'global_units': global_units,
        'global_courses': global_courses,
        'level_choices': GlobalCourse.LEVEL_CHOICES,
    }
    
    return render(request, 'superadmin/academic.html', context)


@superadmin_login_required
def superadmin_analytics(request):
    """Super Admin - Analytics Page"""
    user = request.user
    
    context = {
        'user': user,
    }
    
    return render(request, 'superadmin/analytics.html', context)


@superadmin_login_required
def superadmin_settings(request):
    """Super Admin - System Settings Page"""
    user = request.user
    
    context = {
        'user': user,
    }
    
    return render(request, 'superadmin/settings.html', context)


@superadmin_login_required
def superadmin_profile(request):
    """Super Admin - Profile Page"""
    user = request.user
    
    context = {
        'user': user,
    }
    
    return render(request, 'superadmin/profile.html', context)


@superadmin_login_required
def superadmin_logout(request):
    """Super Admin logout - redirects to admin login"""
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


# Super Admin Payments Views
@superadmin_login_required
def superadmin_payments(request):
    """Super Admin - Payments Management Page"""
    user = request.user
    
    try:
        # Get all colleges with their payment status
        colleges = College.objects.all().order_by('name')
        
        # Get payment configs
        payment_configs = CollegePaymentConfig.objects.select_related('college', 'branch').all()
        config_dict = {}
        for config in payment_configs:
            key = config.branch.id if config.branch else config.college.id
            config_dict[key] = config
        
        # Get latest payments for each college
        latest_payments = {}
        for college in colleges:
            latest_payment = CollegePayment.objects.filter(
                college=college
            ).order_by('-created_at').first()
            if latest_payment:
                latest_payments[college.id] = latest_payment
        
        # Build college list with payment info
        college_list = []
        for college in colleges:
            # Check if this is a main college or branch
            is_branch = college.is_branch()
            
            # Get payment config
            config = config_dict.get(college.id)
            
            # Get latest payment
            latest_payment = latest_payments.get(college.id)
            
            # Determine payment status
            if latest_payment and latest_payment.status == 'completed' and latest_payment.is_valid():
                payment_status = 'Paid'
            elif latest_payment and latest_payment.status == 'completed' and not latest_payment.is_valid():
                payment_status = 'Expired'
            else:
                payment_status = 'Unpaid'
            
            # Only add main colleges to list (branches will be nested)
            if not is_branch:
                # Get branches
                branches = college.branch_colleges.all()
                branch_list = []
                for branch in branches:
                    branch_config = config_dict.get(branch.id)
                    branch_payment = latest_payments.get(branch.id)
                    
                    if branch_payment and branch_payment.status == 'completed' and branch_payment.is_valid():
                        branch_status = 'Paid'
                    elif branch_payment and branch_payment.status == 'completed' and not branch_payment.is_valid():
                        branch_status = 'Expired'
                    else:
                        branch_status = 'Unpaid'
                    
                    branch_list.append({
                        'college': branch,
                        'config': branch_config,
                        'latest_payment': branch_payment,
                        'payment_status': branch_status,
                    })
                
                college_list.append({
                    'college': college,
                    'config': config,
                    'latest_payment': latest_payment,
                    'payment_status': payment_status,
                    'branches': branch_list,
                })
        
        context = {
            'user': user,
            'college_list': college_list,
        }
        
        return render(request, 'superadmin/payments.html', context)
    except Exception as e:
        # Log error and show user-friendly message
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in superadmin_payments view: {str(e)}", exc_info=True)
        
        from django.contrib import messages
        messages.error(request, f'An error occurred while loading payments: {str(e)}')
        
        context = {
            'user': user,
            'college_list': [],
            'error': str(e),
        }
        return render(request, 'superadmin/payments.html', context)


@superadmin_login_required
def superadmin_payment_config(request, college_id):
    """Super Admin - Configure payment settings for a college"""
    user = request.user
    college = get_object_or_404(College, id=college_id)
    
    # Get or create payment config with default values
    try:
        config = CollegePaymentConfig.objects.get(college=college)
    except CollegePaymentConfig.DoesNotExist:
        # Create new config with defaults
        config = CollegePaymentConfig.objects.create(
            college=college,
            created_by=user,
            amount=Decimal('1000.00'),  # Default amount
            payment_period='monthly',
            validity_days=30,
            paybill_number='',  # Will be set by user
            account_reference_format=f'COLLEGE-{college.id}',
            status='active'
        )
    
    if request.method == 'POST':
        # Validate required fields
        amount = request.POST.get('amount', '').strip()
        paybill_number = request.POST.get('paybill_number', '').strip()
        
        if not amount or Decimal(amount) <= 0:
            messages.error(request, 'Please enter a valid payment amount.')
        elif not paybill_number:
            messages.error(request, 'Paybill number is required.')
        else:
            # Update config
            config.amount = Decimal(amount)
            config.payment_period = request.POST.get('payment_period', 'monthly')
            config.validity_days = int(request.POST.get('validity_days', 30))
            config.paybill_number = paybill_number
            config.account_reference_format = request.POST.get('account_reference_format', f'COLLEGE-{college.id}')
            config.callback_url = request.POST.get('callback_url', '').strip()
            config.status = request.POST.get('status', 'active')
            
            # Auto-generate callback URL if not provided
            if not config.callback_url:
                from django.conf import settings
                base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
                config.callback_url = f"{base_url}/superadmin/payments/callback/"
            
            config.save()
            messages.success(request, f'Payment configuration updated for {college.name}')
            return redirect('superadmin:payments')
    
    context = {
        'user': user,
        'college': college,
        'config': config,
    }
    
    return render(request, 'superadmin/payment_config.html', context)


@superadmin_login_required
def superadmin_payment_detail(request, payment_id):
    """Super Admin - View payment details"""
    user = request.user
    payment = get_object_or_404(CollegePayment, id=payment_id)
    
    context = {
        'user': user,
        'payment': payment,
    }
    
    return render(request, 'superadmin/payment_detail.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def superadmin_payment_callback(request):
    """Handle payment callback from Daraja M-Pesa for college payments"""
    
    try:
        callback_data = json.loads(request.body)
        
        # Process callback - similar to accounts callback but for college payments
        body = callback_data.get('Body', {})
        stk_callback = body.get('stkCallback', {})
        
        merchant_request_id = stk_callback.get('MerchantRequestID')
        checkout_request_id = stk_callback.get('CheckoutRequestID')
        result_code = stk_callback.get('ResultCode')
        result_desc = stk_callback.get('ResultDesc')
        
        # Get callback metadata
        callback_metadata = stk_callback.get('CallbackMetadata', {})
        items = callback_metadata.get('Item', [])
        
        # Extract payment details
        payment_data = {}
        for item in items:
            name = item.get('Name')
            value = item.get('Value')
            payment_data[name] = value
        
        if result_code == 0:
            # Payment successful
            amount = Decimal(str(payment_data.get('Amount', 0)))
            mpesa_receipt_number = payment_data.get('MpesaReceiptNumber', '')
            transaction_date = payment_data.get('TransactionDate', '')
            phone_number = payment_data.get('PhoneNumber', '')
            account_reference = payment_data.get('AccountReference', '')
            
            # Find payment by checkout_request_id
            try:
                payment = CollegePayment.objects.get(checkout_request_id=checkout_request_id)
                
                # Update payment
                payment.status = 'completed'
                payment.receipt_number = mpesa_receipt_number
                payment.phone_number = phone_number
                payment.payment_date = timezone.now()
                payment.notes = f"M-Pesa payment via Daraja STK Push. Phone: {phone_number}, Transaction Date: {transaction_date}"
                
                # Set validity dates
                if payment.config:
                    payment.valid_from = timezone.now().date()
                    payment.valid_until = payment.config.get_validity_end_date()
                
                payment.save()
                
                # Activate college if suspended
                college = payment.branch if payment.branch else payment.college
                if college.registration_status == 'inactive':
                    college.registration_status = 'active'
                    college.save()
                
                return JsonResponse({
                    'ResultCode': 0,
                    'ResultDesc': 'Payment processed successfully'
                })
            except CollegePayment.DoesNotExist:
                return JsonResponse({
                    'ResultCode': 1,
                    'ResultDesc': 'Payment record not found'
                }, status=404)
        else:
            # Payment failed - update payment status
            try:
                payment = CollegePayment.objects.get(checkout_request_id=checkout_request_id)
                payment.status = 'failed'
                payment.notes = f"Payment failed: {result_desc}"
                payment.save()
            except CollegePayment.DoesNotExist:
                pass
            
            return JsonResponse({
                'ResultCode': 1,
                'ResultDesc': result_desc or 'Payment failed'
            })
            
    except json.JSONDecodeError:
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': f'Error: {str(e)}'
        }, status=500)
