from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, Count
from django.db import models
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.exceptions import PermissionDenied
import json
from django.utils import timezone
from decimal import Decimal
from education.decorators import (
    college_required, accounts_officer_required, director_required,
    can_edit_academic, can_manage_students, college_admin_required_for_fee_structure
)
from .models import Department, FeeStructure, Payment, AccountsSettings, StudentInvoice, DarajaSettings, DailyExpenditure, FeeItem, CourseFeeStructure
from .forms import DepartmentForm, FeeStructureForm, PaymentForm, DarajaSettingsForm, DailyExpenditureForm
from education.models import Student, CollegeCourse, Enrollment
from decimal import InvalidOperation
from .utils import resolve_active_branch, validate_branch_selection, get_colleges_to_query


def calculate_expected_fees(student):
    """
    Calculate expected fees for a student up to their current semester.
    Uses invoices if available, otherwise falls back to fee structure calculation.
    Returns: {
        'expected_total': Decimal,
        'current_semester': int or None,
        'fee_breakdown': dict (semester_number: total_amount)
    }
    """
    if not student.course:
        return {
            'expected_total': Decimal('0.00'),
            'current_semester': None,
            'fee_breakdown': {}
        }
    
    # Get student's current semester number in course
    current_semester_number = student.get_course_semester_number()
    if not current_semester_number:
        return {
            'expected_total': Decimal('0.00'),
            'current_semester': None,
            'fee_breakdown': {}
        }
    
    # Use student's get_fee_breakdown which now uses invoices if available
    fee_breakdown_dict = student.get_fee_breakdown()
    
    # Convert to expected format and calculate total
    fee_breakdown = {}
    expected_total = Decimal('0.00')
    
    for semester_num in range(1, current_semester_number + 1):
        if semester_num in fee_breakdown_dict:
            sem_data = fee_breakdown_dict[semester_num]
            semester_total = sem_data['amount']
            
            # Get fee type display names
            fee_type_choices = {
                'tuition': 'Tuition Fee',
                'registration': 'Registration Fee',
                'library': 'Library Fee',
                'examination': 'Examination Fee',
                'activity': 'Activity Fee',
                'medical': 'Medical Fee',
                'other': 'Other'
            }
            
            # If invoice exists, use invoice info
            if 'invoice_number' in sem_data:
                fee_breakdown[semester_num] = {
                    'total': semester_total,
                    'invoice_number': sem_data.get('invoice_number'),
                    'invoice_status': sem_data.get('status', 'pending'),
                    'fees': sem_data.get('fee_structures', [])
                }
            else:
                # Use fee structures from course fee structure (new system)
                fee_breakdown[semester_num] = {
                    'total': semester_total,
                    'fees': [
                        {
                            'type': fs_data.get('fee_type', ''),  # fee_item name from CourseFeeStructure
                            'amount': fs_data.get('amount', Decimal('0.00'))
                        }
                        for fs_data in sem_data.get('fee_structures', [])
                    ]
                }
            expected_total += semester_total
        else:
            fee_breakdown[semester_num] = {
                'total': Decimal('0.00'),
                'fees': []
            }
    
    return {
        'expected_total': expected_total,
        'current_semester': current_semester_number,
        'fee_breakdown': fee_breakdown
    }


@login_required
@college_required
def accounts_dashboard(request):
    """Accounts dashboard with key metrics, analytics, and projections"""
    # Resolve active branch for directors
    if request.user.is_director():
        is_valid, active_branch, error_msg = validate_branch_selection(request, require_branch=True)
        if not is_valid:
            messages.warning(request, error_msg or "Please select a branch to view data.")
            # Redirect to director dashboard if branch selection is required
            if error_msg and "select a branch" in error_msg.lower():
                return redirect('director_dashboard')
        college = active_branch
    else:
        college = request.user.college
    
    # Get current academic year
    current_academic_year = college.current_academic_year or f"{timezone.now().year}/{timezone.now().year + 1}"
    current_semester = college.current_semester or 1
    
    # Get active students in current semester
    # Students are considered active if they have enrollments in the current academic year and semester
    active_students_in_semester = Student.objects.filter(
        college=college,
        status='active',
        enrollments__academic_year=current_academic_year,
        enrollments__semester=current_semester
    ).distinct().count()
    
    # Get all active students (for overall stats)
    total_active_students = Student.objects.filter(college=college, status='active').count()
    
    # Calculate total expected fees and outstanding using automatic calculation
    students = Student.objects.filter(college=college, status='active').select_related('course')
    total_expected = Decimal('0.00')
    total_paid_amount = Payment.objects.filter(
        student__college=college
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
        student__college=college,
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
    max_semesters = college.semesters_per_year or 2
    for sem in range(1, max_semesters + 1):
        sem_payments = Payment.objects.filter(
            student__college=college,
            semester_number=sem,
            academic_year=current_academic_year
        ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
        
        semester_labels.append(f'Semester {sem}')
        semester_amounts.append(float(sem_payments))
        semester_payments_data.append({
            'semester': sem,
            'amount': float(sem_payments),
            'count': Payment.objects.filter(
                student__college=college,
                semester_number=sem,
                academic_year=current_academic_year
            ).count()
        })
    
    # Calculate growth rate (comparing current semester with previous semester)
    growth_rate = 0
    growth_percentage = 0
    if current_semester > 1:
        previous_semester_paid = Payment.objects.filter(
            student__college=college,
            semester_number=current_semester - 1,
            academic_year=current_academic_year
        ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
        
        if previous_semester_paid > 0:
            growth_rate = float(current_semester_paid - previous_semester_paid)
            growth_percentage = (growth_rate / float(previous_semester_paid)) * 100
        elif current_semester_paid > 0:
            growth_percentage = 100  # 100% growth if previous was 0
    
    # Calculate projection for end of academic year
    # Projection based on current semester progress and average growth
    total_academic_year_projected = Decimal('0.00')
    if current_semester_progress > 0 and current_semester <= max_semesters:
        # Estimate remaining semesters based on current performance
        remaining_semesters = max_semesters - current_semester
        if remaining_semesters > 0:
            # Project based on current semester average
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
            student__college=college,
            date_paid__gte=month_start,
            date_paid__lt=month_end
        ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
        monthly_payments.append(float(month_payments))
        monthly_labels.append(month_start.strftime('%b %Y'))
    
    # Payment method breakdown
    payment_methods = Payment.objects.filter(
        student__college=college
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
        student__college=college
    ).order_by('-date_paid')[:10]
    
    context = {
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
    }
    
    return render(request, 'accounts/dashboard.html', context)


# Department Views
@login_required
@college_required
def department_list(request):
    """List all departments"""
    college = request.user.college
    departments = Department.objects.filter(college=college).order_by('department_name')
    
    context = {
        'departments': departments
    }
    return render(request, 'accounts/departments/list.html', context)


@login_required
@can_edit_academic
def department_create(request):
    """Create a new department"""
    college = request.user.college
    
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department = form.save(commit=False)
            department.college = college
            department.save()
            messages.success(request, 'Department created successfully!')
            return redirect('accounts:department_list')
    else:
        form = DepartmentForm()
    
    context = {
        'form': form,
        'title': 'Create Department'
    }
    return render(request, 'accounts/departments/form.html', context)


# Fee Structure Views
@login_required
@college_required
def fee_structure_list(request):
    """List all fee structures (grouped by course and semester)"""
    college = request.user.college
    fee_structures = FeeStructure.objects.filter(
        college=college,
        is_current_version=True
    ).select_related('course').order_by('course', 'semester_number', 'fee_type')
    
    # Group by course and semester_number
    grouped = {}
    for fee in fee_structures:
        if fee.semester_number:  # Only process if semester_number is set
            key = f"{fee.course.id}_{fee.semester_number}"
            if key not in grouped:
                grouped[key] = {
                    'course': fee.course,
                    'semester_number': fee.semester_number,
                    'fees': [],
                    'total': Decimal('0.00'),
                    'version': fee.version_number
                }
            grouped[key]['fees'].append(fee)
            grouped[key]['total'] += fee.amount
    
    # Calculate total course fees
    course_totals = {}
    for key, group in grouped.items():
        course_id = group['course'].id
        if course_id not in course_totals:
            course_totals[course_id] = Decimal('0.00')
        course_totals[course_id] += group['total']
    
    context = {
        'grouped_fees': grouped.values(),
        'course_totals': course_totals
    }
    return render(request, 'accounts/fee_structure/list.html', context)


@login_required
@college_admin_required_for_fee_structure
def fee_structure_create(request):
    """Create a new fee structure"""
    college = request.user.college
    
    if request.method == 'POST':
        form = FeeStructureForm(request.POST, college=college)
        if form.is_valid():
            fee_structure = form.save(commit=False)
            fee_structure.college = college
            fee_structure.save()
            messages.success(request, 'Fee structure created successfully!')
            return redirect('accounts:fee_structure_list')
    else:
        form = FeeStructureForm(college=college)
    
    context = {
        'form': form,
        'title': 'Create Fee Structure'
    }
    return render(request, 'accounts/fee_structure/form.html', context)


@login_required
@college_admin_required_for_fee_structure
def fee_structure_edit(request, pk):
    """Edit a fee structure - creates new version if amount or key fields change"""
    college = request.user.college
    fee_structure = get_object_or_404(FeeStructure, pk=pk, college=college)
    
    if request.method == 'POST':
        form = FeeStructureForm(request.POST, instance=fee_structure, college=college)
        if form.is_valid():
            # Store original values to detect changes
            original_amount = fee_structure.amount
            original_course = fee_structure.course
            original_semester = fee_structure.semester_number
            original_fee_type = fee_structure.fee_type
            
            # Get new values from form
            new_fee_structure = form.save(commit=False)
            new_amount = new_fee_structure.amount
            new_effective_from = new_fee_structure.effective_from
            
            # Check if amount or key fields changed
            amount_changed = original_amount != new_amount
            key_fields_changed = (
                original_course != new_fee_structure.course or
                original_semester != new_fee_structure.semester_number or
                original_fee_type != new_fee_structure.fee_type
            )
            
            # If amount changed, create new version to preserve history
            if amount_changed:
                # Create new version with updated amount
                new_version = fee_structure.create_new_version(
                    new_amount=new_amount,
                    effective_from=new_effective_from if new_effective_from else None
                )
                # Update other fields on new version
                new_version.course = new_fee_structure.course
                new_version.semester_number = new_fee_structure.semester_number
                new_version.fee_type = new_fee_structure.fee_type
                new_version.description = new_fee_structure.description
                new_version.is_active = new_fee_structure.is_active
                new_version.save()
                messages.success(request, f'Fee structure updated! New version {new_version.version_number} created to preserve history.')
            elif key_fields_changed:
                # If key fields changed (course, semester, fee_type), we need to handle differently
                # For now, just update the existing version but warn user
                new_fee_structure.college = college
                new_fee_structure.save()
                messages.warning(request, 'Fee structure updated. Note: Changing course/semester/fee_type may affect existing records.')
            else:
                # Only non-critical fields changed (description, is_active), update in place
                fee_structure.description = new_fee_structure.description
                fee_structure.is_active = new_fee_structure.is_active
                fee_structure.save()
                messages.success(request, 'Fee structure updated successfully!')
            
            return redirect('accounts:fee_structure_list')
    else:
        form = FeeStructureForm(instance=fee_structure, college=college)
    
    context = {
        'form': form,
        'title': 'Edit Fee Structure',
        'fee_structure': fee_structure
    }
    return render(request, 'accounts/fee_structure/form.html', context)


@login_required
@college_required
def fee_structure_courses_list(request):
    """List all courses with fee structure status - new redesigned UI"""
    # Resolve active branch for directors
    if request.user.is_director():
        is_valid, active_branch, error_msg = validate_branch_selection(request, require_branch=True)
        if not is_valid:
            messages.warning(request, error_msg or "Please select a branch to view data.")
            return redirect('director_dashboard')
        college = active_branch
    else:
        college = request.user.college
    courses = CollegeCourse.objects.filter(college=college).order_by('name')
    
    # Get all fee items
    fee_items = FeeItem.objects.all().order_by('name')
    
    # For each course, check if it has any fee structure records
    courses_with_status = []
    for course in courses:
        has_fee_structure = CourseFeeStructure.objects.filter(course=course).exists()
        courses_with_status.append({
            'course': course,
            'has_fee_structure': has_fee_structure
        })
    
    context = {
        'courses': courses_with_status,
        'fee_items': fee_items,
        'college': college
    }
    return render(request, 'accounts/fee_structure/courses_list.html', context)


@login_required
@college_admin_required_for_fee_structure
@require_http_methods(["GET", "POST"])
def fee_structure_course_detail(request, course_id):
    """Get or save fee structure for a specific course and semester"""
    college = request.user.college
    course = get_object_or_404(CollegeCourse, pk=course_id, college=college)
    
    if request.method == 'GET':
        # Get semester_number from query parameter
        semester_number = request.GET.get('semester_number')
        if not semester_number:
            return JsonResponse({
                'error': 'semester_number is required'
            }, status=400)
        
        try:
            semester_number = int(semester_number)
            if semester_number < 1:
                return JsonResponse({
                    'error': 'semester_number must be at least 1'
                }, status=400)
        except (ValueError, TypeError):
            return JsonResponse({
                'error': 'Invalid semester_number'
            }, status=400)
        
        # Get all fee items
        fee_items = FeeItem.objects.all().order_by('name')
        
        # Get existing course fee structures for this semester
        existing_structures = CourseFeeStructure.objects.filter(
            course=course,
            semester_number=semester_number
        )
        structure_dict = {struct.fee_item_id: struct.amount for struct in existing_structures}
        
        # Build response with all fee items
        fee_items_data = []
        for fee_item in fee_items:
            amount = structure_dict.get(fee_item.id, Decimal('0.00'))
            fee_items_data.append({
                'id': fee_item.id,
                'name': fee_item.name,
                'description': fee_item.description or '',
                'amount': str(amount)
            })
        
        return JsonResponse({
            'course_id': course.id,
            'course_name': course.name,
            'semester_number': semester_number,
            'fee_items': fee_items_data
        })
    
    elif request.method == 'POST':
        # Save fee structure
        try:
            data = json.loads(request.body)
            semester_number = data.get('semester_number')
            fee_items_data = data.get('fee_items', [])
            
            if not semester_number:
                return JsonResponse({
                    'success': False,
                    'message': 'semester_number is required'
                }, status=400)
            
            try:
                semester_number = int(semester_number)
                if semester_number < 1:
                    return JsonResponse({
                        'success': False,
                        'message': 'semester_number must be at least 1'
                    }, status=400)
            except (ValueError, TypeError):
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid semester_number'
                }, status=400)
            
            # Loop through all fee items and create/update records
            for item_data in fee_items_data:
                fee_item_id = item_data.get('fee_item_id')
                amount_str = item_data.get('amount', '0.00')
                
                try:
                    amount = Decimal(amount_str)
                    if amount < 0:
                        amount = Decimal('0.00')
                except (ValueError, InvalidOperation):
                    amount = Decimal('0.00')
                
                fee_item = get_object_or_404(FeeItem, pk=fee_item_id)
                
                # Create or update the course fee structure for this semester
                course_fee_structure, created = CourseFeeStructure.objects.update_or_create(
                    course=course,
                    fee_item=fee_item,
                    semester_number=semester_number,
                    defaults={'amount': amount}
                )
            
            return JsonResponse({
                'success': True,
                'message': f'Fee structure for {course.name} Semester {semester_number} saved successfully!'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error saving fee structure: {str(e)}'
            }, status=400)


@login_required
@college_required
@require_http_methods(["GET"])
def fee_item_list(request):
    """List all fee items - read-only for Principal/Accounts, editable for Director"""
    # Check permissions: Director can edit, Principal/Accounts can view, others denied
    if not (request.user.is_director() or request.user.is_principal() or request.user.is_accounts_officer()):
        raise PermissionDenied("Access denied. Director, Principal, or Accounts Officer required.")
    
    fee_items = FeeItem.objects.all().order_by('name')
    
    fee_items_data = []
    for item in fee_items:
        fee_items_data.append({
            'id': item.id,
            'name': item.name,
            'description': item.description or '',
            'created_at': item.created_at.isoformat() if item.created_at else None,
            'updated_at': item.updated_at.isoformat() if item.updated_at else None
        })
    
    return JsonResponse({
        'fee_items': fee_items_data,
        'can_edit': request.user.is_director()  # Only Director can edit
    })


@login_required
@director_required
@require_http_methods(["POST"])
def fee_item_create(request):
    """Create a new fee item - Director only"""
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        
        if not name:
            return JsonResponse({
                'success': False,
                'message': 'Name is required'
            }, status=400)
        
        # Check if fee item with same name already exists
        if FeeItem.objects.filter(name=name).exists():
            return JsonResponse({
                'success': False,
                'message': f'A fee item with the name "{name}" already exists'
            }, status=400)
        
        fee_item = FeeItem.objects.create(
            name=name,
            description=description if description else None
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Fee item "{fee_item.name}" created successfully!',
            'fee_item': {
                'id': fee_item.id,
                'name': fee_item.name,
                'description': fee_item.description or '',
                'created_at': fee_item.created_at.isoformat() if fee_item.created_at else None,
                'updated_at': fee_item.updated_at.isoformat() if fee_item.updated_at else None
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error creating fee item: {str(e)}'
        }, status=400)


@login_required
@director_required
@require_http_methods(["POST"])
def fee_item_edit(request, fee_item_id):
    """Edit an existing fee item - Director only"""
    fee_item = get_object_or_404(FeeItem, pk=fee_item_id)
    
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        
        if not name:
            return JsonResponse({
                'success': False,
                'message': 'Name is required'
            }, status=400)
        
        # Check if another fee item with same name already exists
        if FeeItem.objects.filter(name=name).exclude(pk=fee_item_id).exists():
            return JsonResponse({
                'success': False,
                'message': f'A fee item with the name "{name}" already exists'
            }, status=400)
        
        fee_item.name = name
        fee_item.description = description if description else None
        fee_item.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Fee item "{fee_item.name}" updated successfully!',
            'fee_item': {
                'id': fee_item.id,
                'name': fee_item.name,
                'description': fee_item.description or '',
                'created_at': fee_item.created_at.isoformat() if fee_item.created_at else None,
                'updated_at': fee_item.updated_at.isoformat() if fee_item.updated_at else None
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error updating fee item: {str(e)}'
        }, status=400)


# Payment Views
@login_required
@college_required
def payment_list(request):
    """List all payments"""
    # Resolve active branch for directors
    if request.user.is_director():
        is_valid, active_branch, error_msg = validate_branch_selection(request, require_branch=True)
        if not is_valid:
            messages.warning(request, error_msg or "Please select a branch to view data.")
            return redirect('director_dashboard')
        college = active_branch
    else:
        college = request.user.college
    payments = Payment.objects.filter(
        student__college=college
    ).select_related('student').order_by('-date_paid')
    
    # Filtering
    method_filter = request.GET.get('method', '')
    student_filter = request.GET.get('student', '')
    
    if method_filter:
        payments = payments.filter(payment_method=method_filter)
    
    if student_filter:
        payments = payments.filter(student_id=student_filter)
    
    # Pagination
    paginator = Paginator(payments, 25)
    page = request.GET.get('page')
    payments = paginator.get_page(page)
    
    context = {
        'payments': payments,
        'method_filter': method_filter,
        'student_filter': student_filter
    }
    return render(request, 'accounts/payments/list.html', context)


@login_required
@college_required
def payment_detail(request, pk):
    """View payment details"""
    college = request.user.college
    payment = get_object_or_404(Payment, pk=pk, student__college=college)
    
    context = {
        'payment': payment
    }
    return render(request, 'accounts/payments/detail.html', context)


@login_required
@accounts_officer_required
def payment_create(request):
    """Create a new payment"""
    college = request.user.college
    
    if request.method == 'POST':
        form = PaymentForm(request.POST, college=college)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.recorded_by = request.user
            payment.save()
            messages.success(request, f'Payment {payment.receipt_number} recorded successfully!')
            return redirect('accounts:payment_detail', pk=payment.pk)
    else:
        form = PaymentForm(college=college)
        # Pre-fill student if provided in URL
        student_id = request.GET.get('student')
        if student_id:
            try:
                student = Student.objects.get(pk=student_id, college=college)
                form.fields['student'].initial = student
            except Student.DoesNotExist:
                pass
    
    context = {
        'form': form,
        'title': 'Record Payment'
    }
    return render(request, 'accounts/payments/form.html', context)


# Report Views
@login_required
@college_required
def balance_report(request):
    """Student balance report - shows all students with their balances based on expected fees up to current semester"""
    # Resolve active branch for directors
    if request.user.is_director():
        is_valid, active_branch, error_msg = validate_branch_selection(request, require_branch=True)
        if not is_valid:
            messages.warning(request, error_msg or "Please select a branch to view data.")
            return redirect('director_dashboard')
        college = active_branch
    else:
        college = request.user.college
    
    # Get filter option
    filter_with_course = request.GET.get('with_course', '')
    
    # Get all students for the college
    students = Student.objects.filter(college=college).select_related('course').order_by('admission_number')
    
    # Filter to show only students with courses if requested
    if filter_with_course == 'true':
        students = students.exclude(course__isnull=True)
    
    # Calculate balance for each student
    student_data = []
    for student in students:
        # Calculate expected fees up to current semester (automatic calculation)
        fee_info = calculate_expected_fees(student)
        expected_total = fee_info['expected_total']
        current_semester = fee_info['current_semester']
        
        # Get all payments for this student
        payments = Payment.objects.filter(student=student)
        
        # Calculate total payments
        total_payments = payments.aggregate(
            total=Sum('amount_paid')
        )['total'] or Decimal('0.00')
        
        # Calculate outstanding balance (expected - paid)
        outstanding = expected_total - total_payments
        
        # Check if student has a course
        has_course = student.course is not None
        
        student_data.append({
            'student': student,
            'expected_total': expected_total,
            'total_payments': total_payments,
            'outstanding': outstanding,
            'current_semester': current_semester,
            'has_course': has_course,
        })
    
    # Sort by outstanding balance descending (students with highest balance first)
    student_data.sort(key=lambda x: x['outstanding'], reverse=True)
    
    # Total outstanding across all students
    total_outstanding = sum(item['outstanding'] for item in student_data if item['outstanding'] > 0)
    
    context = {
        'student_data': student_data,
        'total_outstanding': total_outstanding,
        'filter_with_course': filter_with_course
    }
    return render(request, 'accounts/reports/balances.html', context)


@login_required
@college_required
def debtors_report(request):
    """Debtors report - students with outstanding balances"""
    # Resolve active branch for directors
    if request.user.is_director():
        is_valid, active_branch, error_msg = validate_branch_selection(request, require_branch=True)
        if not is_valid:
            messages.warning(request, error_msg or "Please select a branch to view data.")
            return redirect('director_dashboard')
        college = active_branch
    else:
        college = request.user.college
    students = Student.objects.filter(college=college).select_related('course').order_by('admission_number')
    
    # Calculate balance for each student
    debtor_data = []
    for student in students:
        fee_info = calculate_expected_fees(student)
        expected_total = fee_info['expected_total']
        
        payments = Payment.objects.filter(student=student)
        total_payments = payments.aggregate(
            total=Sum('amount_paid')
        )['total'] or Decimal('0.00')
        
        outstanding = expected_total - total_payments
        
        # Only include students with outstanding balance
        if outstanding > 0:
            debtor_data.append({
                'student': student,
                'expected_total': expected_total,
                'total_payments': total_payments,
                'outstanding': outstanding,
                'current_semester': fee_info['current_semester']
            })
    
    # Sort by outstanding balance descending
    debtor_data.sort(key=lambda x: x['outstanding'], reverse=True)
    
    # Total overdue
    total_overdue = sum(item['outstanding'] for item in debtor_data)
    
    context = {
        'debtor_data': debtor_data,
        'total_overdue': total_overdue
    }
    return render(request, 'accounts/reports/debtors.html', context)


@login_required
@college_required
def payments_by_term_report(request):
    """Payments summary by semester and academic year"""
    # Resolve active branch for directors
    if request.user.is_director():
        is_valid, active_branch, error_msg = validate_branch_selection(request, require_branch=True)
        if not is_valid:
            messages.warning(request, error_msg or "Please select a branch to view data.")
            return redirect('director_dashboard')
        college = active_branch
    else:
        college = request.user.college
    
    # Get all unique semester_number and academic_year combinations from payments
    payments = Payment.objects.filter(student__college=college).values('semester_number', 'academic_year').distinct()
    
    semester_data = []
    for payment_info in payments:
        semester_number = payment_info.get('semester_number')
        academic_year = payment_info.get('academic_year')
        
        if semester_number and academic_year:
            # Get all payments for this semester and academic year
            semester_payments = Payment.objects.filter(
                student__college=college,
                semester_number=semester_number,
                academic_year=academic_year
            )
            total_paid = semester_payments.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
            
            semester_data.append({
                'semester_number': semester_number,
                'academic_year': academic_year,
                'total_paid': total_paid,
                'payment_count': semester_payments.count()
            })
    
    # Sort by academic year (descending) and semester number
    semester_data.sort(key=lambda x: (x['academic_year'], x['semester_number']), reverse=True)
    
    context = {
        'semester_data': semester_data
    }
    return render(request, 'accounts/reports/payments_by_term.html', context)


# Settings Views
@login_required
@college_required
def accounts_settings(request):
    """Accounts settings page with tabs"""
    from .forms import SponsorshipSettingsForm
    from education.decorators import director_required
    
    # Resolve active branch for directors
    if request.user.is_director():
        is_valid, active_branch, error_msg = validate_branch_selection(request, require_branch=True)
        if not is_valid:
            messages.warning(request, error_msg or "Please select a branch to view data.")
            return redirect('director_dashboard')
        college = active_branch
    else:
        college = request.user.college
    
    # Get or create accounts settings
    settings, created = AccountsSettings.objects.get_or_create(college=college)
    
    active_tab = request.GET.get('tab', 'fee_structure')
    form = None
    daraja_form = None
    
    # Prevent non-directors from accessing daraja tab directly via URL
    if active_tab == 'daraja' and not request.user.can_manage_payment_settings():
        messages.error(request, 'Only Directors can access M-Pesa and Bank payment settings.')
        return redirect(reverse('accounts:accounts_settings') + '?tab=fee_structure')
    
    # Handle sponsorship settings form submission
    if request.method == 'POST' and active_tab == 'sponsorship':
        form = SponsorshipSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Sponsorship settings updated successfully!')
            return redirect(reverse('accounts:accounts_settings') + '?tab=sponsorship')
        else:
            messages.error(request, 'Please correct the errors below.')
    elif request.method == 'POST' and active_tab == 'daraja':
        # Only director can edit Daraja settings (MPESA and Bank integration)
        if not request.user.can_manage_payment_settings():
            messages.error(request, 'Only Directors can configure M-Pesa and Bank payment settings.')
            return redirect(reverse('accounts:accounts_settings') + '?tab=daraja')
        
        daraja_settings, created = DarajaSettings.objects.get_or_create(college=college)
        daraja_form = DarajaSettingsForm(request.POST, instance=daraja_settings)
        if daraja_form.is_valid():
            daraja_form.save()
            
            # Auto-generate callback URL if not provided
            if not daraja_settings.callback_url:
                from django.conf import settings as django_settings
                base_url = getattr(django_settings, 'BASE_URL', request.build_absolute_uri('/').rstrip('/'))
                daraja_settings.callback_url = f"{base_url}/accounts/payment/daraja/callback/"
                daraja_settings.save()
            
            messages.success(request, 'M-Pesa payment settings updated successfully!')
            return redirect(reverse('accounts:accounts_settings') + '?tab=daraja')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = SponsorshipSettingsForm(instance=settings)
        # Only show Daraja form to directors (for MPESA and Bank integration)
        can_manage_daraja = request.user.can_manage_payment_settings()
        if can_manage_daraja:
            daraja_settings, created = DarajaSettings.objects.get_or_create(college=college)
            daraja_form = DarajaSettingsForm(instance=daraja_settings)
    
    context = {
        'settings': settings,
        'form': form,
        'daraja_form': daraja_form,
        'active_tab': active_tab,
        'can_manage_daraja': request.user.can_manage_payment_settings()
    }
    return render(request, 'accounts/settings.html', context)


# Balance Views
@login_required
@college_required
def student_balances(request):
    """View all student balances"""
    # Resolve active branch for directors
    if request.user.is_director():
        is_valid, active_branch, error_msg = validate_branch_selection(request, require_branch=True)
        if not is_valid:
            messages.warning(request, error_msg or "Please select a branch to view data.")
            return redirect('director_dashboard')
        college = active_branch
    else:
        college = request.user.college
    students = Student.objects.filter(college=college, status='active').select_related('course')
    
    # Calculate balances for each student
    student_data = []
    for student in students:
        total_expected = student.get_total_expected_fees()
        total_paid = student.get_total_payments()
        balance = student.get_balance()
        
        student_data.append({
            'student': student,
            'total_expected': total_expected,
            'total_paid': total_paid,
            'balance': balance
        })
    
    # Sort by balance descending (highest debt first)
    student_data.sort(key=lambda x: x['balance'], reverse=True)
    
    # Calculate totals
    total_expected_all = sum(item['total_expected'] for item in student_data)
    total_paid_all = sum(item['total_paid'] for item in student_data)
    total_balance_all = sum(item['balance'] for item in student_data)
    
    # Filtering
    search_query = request.GET.get('search', '')
    if search_query:
        student_data = [s for s in student_data if 
                       search_query.lower() in s['student'].admission_number.lower() or
                       search_query.lower() in s['student'].full_name.lower()]
    
    # Pagination
    paginator = Paginator(student_data, 25)
    page = request.GET.get('page')
    student_data = paginator.get_page(page)
    
    context = {
        'student_data': student_data,
        'total_expected_all': total_expected_all,
        'total_paid_all': total_paid_all,
        'total_balance_all': total_balance_all,
        'search_query': search_query
    }
    return render(request, 'accounts/balances/list.html', context)


@login_required
@college_required
def invoice_list(request):
    """Invoice view with student search and invoice details"""
    # Resolve active branch for directors
    if request.user.is_director():
        is_valid, active_branch, error_msg = validate_branch_selection(request, require_branch=True)
        if not is_valid:
            messages.warning(request, error_msg or "Please select a branch to view data.")
            return redirect('director_dashboard')
        college = active_branch
    else:
        college = request.user.college
    
    # Get search query
    search_query = request.GET.get('search', '')
    student_id = request.GET.get('student_id', '')
    
    student = None
    invoices = []
    selected_invoice = None
    
    # If student_id is provided, get the student and their invoices
    if student_id:
        try:
            student = Student.objects.get(id=student_id, college=college)
            invoices = StudentInvoice.objects.filter(student=student).order_by('semester_number', '-date_created')
            
            # Get current semester number
            current_semester_number = student.get_course_semester_number() if student.course else None
            
            # Get invoice for selected semester
            selected_semester = request.GET.get('semester', '')
            if selected_semester:
                try:
                    selected_semester_num = int(selected_semester)
                    selected_invoice = StudentInvoice.objects.filter(
                        student=student,
                        semester_number=selected_semester_num
                    ).first()
                except (ValueError, TypeError):
                    selected_invoice = None
            elif invoices.exists():
                # Default to most recent invoice
                selected_invoice = invoices.first()
            else:
                selected_invoice = None
        except Student.DoesNotExist:
            messages.error(request, 'Student not found.')
    
    # Search for students if search query is provided
    students = []
    if search_query:
        students = Student.objects.filter(
            college=college
        ).filter(
            Q(admission_number__icontains=search_query) |
            Q(full_name__icontains=search_query)
        )[:10]  # Limit to 10 results
    
    # Get current semester number for dropdown
    current_semester_number = None
    semester_range = []
    if student and student.course:
        current_semester_number = student.get_course_semester_number()
        if current_semester_number:
            semester_range = list(range(1, current_semester_number + 1))
    
    context = {
        'search_query': search_query,
        'student': student,
        'students': students,
        'invoices': invoices,
        'selected_invoice': selected_invoice,
        'current_semester_number': current_semester_number,
        'semester_range': semester_range,
        'selected_semester': request.GET.get('semester', ''),
    }
    return render(request, 'accounts/invoice/list.html', context)


@login_required
@college_required
def generate_student_invoices(request, student_id):
    """Generate invoices for a student for all semesters up to current semester"""
    college = request.user.college
    
    try:
        student = Student.objects.get(id=student_id, college=college)
    except Student.DoesNotExist:
        messages.error(request, 'Student not found.')
        return redirect('accounts:invoice_list')
    
    if not student.course:
        messages.error(request, 'Student must have a course assigned to generate invoices.')
        return redirect(f"{reverse('accounts:invoice_list')}?student_id={student_id}")
    
    # Get student's current semester number in course
    current_semester_number = student.get_course_semester_number()
    
    if not current_semester_number:
        messages.error(request, 'Unable to determine current semester for this student.')
        return redirect(f"{reverse('accounts:invoice_list')}?student_id={student_id}")
    
    # Get total course semesters
    total_semesters = student.get_total_course_semesters()
    is_final_semester = current_semester_number >= total_semesters if total_semesters else False
    
    # Generate invoices for all semesters from 1 to current semester
    from .models import generate_student_invoice
    
    generated_count = 0
    skipped_count = 0
    errors = []
    
    for sem_num in range(1, current_semester_number + 1):
        try:
            invoice = generate_student_invoice(
                student=student,
                semester_number=sem_num,
                academic_year=student.college.current_academic_year,
                created_by=request.user
            )
            if invoice:
                generated_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            errors.append(f"Semester {sem_num}: {str(e)}")
    
    # Note: Graduation invoice to be implemented later
    # if is_final_semester:
    #     # Generate graduation invoice (to be implemented)
    #     pass
    
    if generated_count > 0:
        messages.success(request, f'Successfully generated {generated_count} invoice(s) for {student.full_name}.')
    elif skipped_count > 0:
        messages.warning(request, f'No new invoices generated. {skipped_count} semester(s) already have invoices.')
    else:
        messages.info(request, 'No invoices were generated. Please check if fee structures exist for this course.')
    
    if errors:
        messages.error(request, f'Some errors occurred: {"; ".join(errors[:3])}')
    
    return redirect(f"{reverse('accounts:invoice_list')}?student_id={student_id}")


# Daraja M-Pesa Payment Views
@csrf_exempt
@require_http_methods(["POST"])
def daraja_payment_callback(request):
    """Handle payment callback from Daraja M-Pesa"""
    try:
        callback_data = json.loads(request.body)
        
        # Process callback using DarajaService
        from .daraja_service import DarajaService
        result = DarajaService.process_callback(callback_data)
        
        if result.get('success'):
            return JsonResponse({
                'ResultCode': 0,
                'ResultDesc': 'Payment processed successfully'
            })
        else:
            return JsonResponse({
                'ResultCode': 1,
                'ResultDesc': result.get('error', 'Payment processing failed')
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


# Daily Expenditure Views
@login_required
@college_required
def daily_expenditure_draft(request, pk=None):
    """
    Create or edit daily expenditure drafts.
    Access: Principal and Accounts Officer only.
    """
    college = request.user.college
    user = request.user
    
    # Check permissions: Only Principal and Accounts Officer can create/edit drafts
    if not (user.is_principal() or user.is_accounts_officer()):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('accounts:dashboard')
    
    # Handle delete request
    if request.method == 'POST' and 'delete_id' in request.POST:
        delete_id = request.POST.get('delete_id')
        try:
            expenditure = DailyExpenditure.objects.get(
                pk=delete_id,
                college=college,
                submitted=False
            )
            # Check if user can delete (must be creator or same role)
            if expenditure.entered_by == user or user.is_principal() or user.is_accounts_officer():
                expenditure.delete()
                messages.success(request, 'Expenditure entry deleted successfully.')
            else:
                messages.error(request, 'You do not have permission to delete this entry.')
        except DailyExpenditure.DoesNotExist:
            messages.error(request, 'Entry not found.')
        return redirect('accounts:daily_expenditure_draft')
    
    # Get today's date for filtering drafts
    today = timezone.now().date()
    
    # Get all draft entries for today (not submitted)
    today_drafts = DailyExpenditure.objects.filter(
        college=college,
        created_at__date=today,
        submitted=False
    ).order_by('-created_at')
    
    # Calculate total for today's drafts
    draft_total = today_drafts.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # If editing an existing entry
    expenditure = None
    if pk:
        expenditure = get_object_or_404(
            DailyExpenditure,
            pk=pk,
            college=college,
            submitted=False  # Can only edit drafts
        )
        
        # Check if user can edit this entry (must be creator or same role)
        if expenditure.entered_by != user and not (user.is_principal() or user.is_accounts_officer()):
            messages.error(request, 'You do not have permission to edit this entry.')
            return redirect('accounts:daily_expenditure_draft')
    
    if request.method == 'POST':
        form = DailyExpenditureForm(
            request.POST,
            instance=expenditure,
            user=user,
            college=college,
            is_submitted=False
        )
        
        if form.is_valid():
            expenditure = form.save()
            messages.success(request, 'Expenditure entry saved successfully.')
            return redirect('accounts:daily_expenditure_draft')
    else:
        form = DailyExpenditureForm(
            instance=expenditure,
            user=user,
            college=college,
            is_submitted=False
        )
    
    context = {
        'form': form,
        'today_drafts': today_drafts,
        'draft_total': draft_total,
        'today': today,
        'expenditure': expenditure,
    }
    
    return render(request, 'accounts/daily_expenditure/draft.html', context)


@login_required
@college_required
@require_http_methods(["POST"])
def submit_daily_expenditure(request):
    """
    Submit all draft entries for today.
    Access: Principal and Accounts Officer only.
    """
    college = request.user.college
    user = request.user
    
    # Check permissions
    if not (user.is_principal() or user.is_accounts_officer()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    today = timezone.now().date()
    
    # Get all draft entries for today
    drafts = DailyExpenditure.objects.filter(
        college=college,
        created_at__date=today,
        submitted=False
    )
    
    if not drafts.exists():
        return JsonResponse({'success': False, 'error': 'No draft entries to submit'}, status=400)
    
    # Submit all drafts
    submitted_count = 0
    for draft in drafts:
        draft.submitted = True
        draft.submitted_at = timezone.now()
        draft.save()
        submitted_count += 1
    
    messages.success(request, f'Successfully submitted {submitted_count} expenditure entr{"y" if submitted_count == 1 else "ies"}.')
    
    return JsonResponse({
        'success': True,
        'message': f'Successfully submitted {submitted_count} entr{"y" if submitted_count == 1 else "ies"}.',
        'submitted_count': submitted_count
    })


@login_required
@director_required
def daily_expenditure_report(request):
    """
    Read-only report view for Director.
    Shows submitted expenditures for a selected date with line graph.
    """
    # Resolve active branch for directors
    if request.user.is_director():
        is_valid, active_branch, error_msg = validate_branch_selection(request, require_branch=True)
        if not is_valid:
            messages.warning(request, error_msg or "Please select a branch to view data.")
            return redirect('director_dashboard')
        college = active_branch
    else:
        college = request.user.college
    
    # Get selected date from query parameter (default to today)
    selected_date_str = request.GET.get('date', None)
    if selected_date_str:
        try:
            from datetime import datetime
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()
    
    # Get all submitted expenditures for the selected date
    expenditures = DailyExpenditure.objects.filter(
        college=college,
        created_at__date=selected_date,
        submitted=True
    ).order_by('-created_at')
    
    # Calculate total for selected date
    daily_total = expenditures.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Get all available dates with submitted expenditures (for date picker)
    available_dates = DailyExpenditure.objects.filter(
        college=college,
        submitted=True
    ).values_list('created_at__date', flat=True).distinct().order_by('-created_at__date')
    
    # Get cumulative data for line graph (up to selected date in current semester)
    # Calculate semester start date (approximate: 3 months ago or start of academic year)
    from datetime import timedelta
    import json
    semester_start = selected_date - timedelta(days=90)  # Approximate semester start
    
    cumulative_data = DailyExpenditure.get_cumulative_by_date(
        college=college,
        start_date=semester_start,
        end_date=selected_date
    )
    
    context = {
        'expenditures': expenditures,
        'daily_total': daily_total,
        'selected_date': selected_date,
        'available_dates': available_dates,
        'cumulative_data': json.dumps(cumulative_data),  # Convert to JSON string for template
    }
    
    return render(request, 'accounts/daily_expenditure/report.html', context)


@login_required
@director_required
def daily_expenditure_graph_data(request):
    """
    API endpoint to get cumulative expenditure data for line graph.
    Returns JSON data for Chart.js or similar.
    """
    college = request.user.college
    
    # Get date range from query parameters
    start_date_str = request.GET.get('start_date', None)
    end_date_str = request.GET.get('end_date', None)
    
    start_date = None
    end_date = None
    
    if start_date_str:
        try:
            from datetime import datetime
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    if end_date_str:
        try:
            from datetime import datetime
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    # Get cumulative data
    cumulative_data = DailyExpenditure.get_cumulative_by_date(
        college=college,
        start_date=start_date,
        end_date=end_date
    )
    
    return JsonResponse({
        'success': True,
        'data': cumulative_data
    })

