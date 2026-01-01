from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from datetime import timedelta
from education.models import College, Student, CollegeCourse, CustomUser
from decimal import Decimal
import json
from cryptography.fernet import Fernet
from django.conf import settings
import base64
import hashlib


def generate_student_invoice(student, semester_number, academic_year=None, created_by=None):
    """
    Automatically generate an invoice for a student for a specific semester.
    This function calculates fees based on the active fee structure at the time of generation.
    
    Args:
        student: Student instance
        semester_number: Course semester number (1, 2, 3...)
        academic_year: Academic year string (e.g., "2024/2025"). If None, uses college's current_academic_year
        created_by: User who triggered the invoice generation (optional)
    
    Returns:
        StudentInvoice instance or None if invoice already exists or student has no course
    """
    # Check if student has a course
    if not student.course:
        return None
    
    # Check if invoice already exists for this semester
    if StudentInvoice.objects.filter(student=student, semester_number=semester_number).exists():
        return None
    
    # Refresh student from database to ensure we have latest data
    try:
        student.refresh_from_db()
    except Student.DoesNotExist:
        return None
    
    # Get academic year if not provided
    if not academic_year:
        academic_year = student.college.current_academic_year
        if not academic_year:
            # Fallback: calculate from current date
            current_year = timezone.now().year
            academic_year = f"{current_year}/{current_year + 1}"
    
    # Get course fee structures for this semester (semester-specific)
    course_fee_structures = CourseFeeStructure.objects.filter(
        course=student.course,
        semester_number=semester_number
    )
    
    # Calculate total fee amount from course fee structures
    total_amount = course_fee_structures.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    
    # Apply sponsorship discount if applicable
    if student.is_sponsored and student.sponsorship_discount_type and student.sponsorship_discount_value:
        if student.sponsorship_discount_type == 'percentage':
            discount = total_amount * (student.sponsorship_discount_value / Decimal('100.00'))
        else:  # fixed_amount
            discount = student.sponsorship_discount_value
        total_amount = max(Decimal('0.00'), total_amount - discount)
    
    # Only create invoice if there are fees to charge
    if total_amount <= Decimal('0.00'):
        return None
    
    # Calculate due date (30 days from creation by default)
    due_date = timezone.now().date() + timedelta(days=30)
    
    # Create invoice
    invoice = StudentInvoice.objects.create(
        student=student,
        semester_number=semester_number,
        academic_year=academic_year,
        fee_amount=total_amount,
        due_date=due_date,
        created_by=created_by,
        notes=f"Auto-generated invoice for Semester {semester_number}"
    )
    
    return invoice


class Department(models.Model):
    """Department model - linked to college"""
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='departments')
    department_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'departments'
        unique_together = ['college', 'department_name']
        ordering = ['department_name']
    
    def __str__(self):
        return f"{self.college.name} - {self.department_name}"


class AccountsSettings(models.Model):
    """Global accounts settings for college"""
    college = models.OneToOneField(College, on_delete=models.CASCADE, related_name='accounts_settings')
    
    # Sponsorship Settings
    sponsorship_enabled = models.BooleanField(default=False, help_text="Enable school sponsorship system")
    sponsorship_default_discount_type = models.CharField(
        max_length=20,
        choices=[('percentage', 'Percentage'), ('fixed_amount', 'Fixed Amount')],
        default='percentage',
        help_text="Default discount type for sponsored students"
    )
    sponsorship_default_discount_value = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text="Default discount value (percentage 0-100 or fixed amount in KES)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'accounts_settings'
        verbose_name = 'Accounts Settings'
        verbose_name_plural = 'Accounts Settings'
    
    def __str__(self):
        return f"Accounts Settings - {self.college.name}"


class FeeStructure(models.Model):
    """Fee structure per course per semester (versioned)"""
    FEE_TYPE_CHOICES = [
        ('tuition', 'Tuition Fee'),
        ('registration', 'Registration Fee'),
        ('library', 'Library Fee'),
        ('examination', 'Examination Fee'),
        ('activity', 'Activity Fee'),
        ('medical', 'Medical Fee'),
        ('other', 'Other'),
    ]
    
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='fee_structures')
    course = models.ForeignKey(CollegeCourse, on_delete=models.CASCADE, related_name='fee_structures')
    semester_number = models.IntegerField(validators=[MinValueValidator(1)], null=True, blank=True, help_text="Semester position in course (1, 2, 3... up to total semesters)")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    fee_type = models.CharField(max_length=50, choices=FEE_TYPE_CHOICES, default='tuition')
    description = models.TextField(blank=True, null=True)
    
    # Versioning fields
    version_number = models.IntegerField(default=1, help_text="Version number of this fee structure")
    effective_from = models.DateField(default=timezone.now, help_text="Date when this version becomes active")
    effective_to = models.DateField(null=True, blank=True, help_text="Date when this version expires (null = current version)")
    is_current_version = models.BooleanField(default=True, help_text="Whether this is the current active version")
    replaced_by_version = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replaces', help_text="New version that replaced this one")
    
    is_active = models.BooleanField(default=True, help_text="Whether this fee structure is active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'fee_structures'
        unique_together = ['course', 'semester_number', 'fee_type', 'version_number']
        ordering = ['course', 'semester_number', 'fee_type', 'version_number']
        indexes = [
            models.Index(fields=['college', 'course']),
            models.Index(fields=['course', 'semester_number']),
            models.Index(fields=['is_current_version', 'effective_from']),
        ]
    
    def __str__(self):
        version_text = f"v{self.version_number}" if self.version_number > 1 else ""
        return f"{self.course.name} - Semester {self.semester_number} - {self.get_fee_type_display()}: KES {self.amount} {version_text}"
    
    def get_total_semesters(self):
        """Calculate total semesters for this course"""
        if not self.course or not self.college:
            return None
        return self.course.duration_years * self.college.semesters_per_year
    
    @classmethod
    def get_active_version(cls, course, semester_number, date=None):
        """Get active fee structure version for course and semester on given date"""
        if date is None:
            date = timezone.now().date()
        
        return cls.objects.filter(
            course=course,
            semester_number=semester_number,
            is_current_version=True,
            is_active=True,
            effective_from__lte=date
        ).filter(
            models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=date)
        ).first()
    
    def create_new_version(self, new_amount=None, effective_from=None):
        """Create a new version of this fee structure"""
        if effective_from is None:
            effective_from = timezone.now().date()
        
        # Deactivate current version
        self.effective_to = effective_from - timedelta(days=1) if effective_from > timezone.now().date() else timezone.now().date()
        self.is_current_version = False
        self.save()
        
        # Create new version
        new_version = FeeStructure.objects.create(
            college=self.college,
            course=self.course,
            semester_number=self.semester_number,
            amount=new_amount if new_amount is not None else self.amount,
            fee_type=self.fee_type,
            description=self.description,
            version_number=self.version_number + 1,
            effective_from=effective_from,
            is_current_version=True,
            is_active=True,
            replaced_by_version=None
        )
        
        # Link versions
        self.replaced_by_version = new_version
        self.save()
        
        return new_version
    
    def is_active_on_date(self, date=None):
        """Check if this version is active on given date"""
        if date is None:
            date = timezone.now().date()
        return (self.effective_from <= date and 
                (self.effective_to is None or self.effective_to >= date))
    
    def get_version_history(self):
        """Get all versions of this fee structure"""
        return FeeStructure.objects.filter(
            course=self.course,
            semester_number=self.semester_number,
            fee_type=self.fee_type
        ).order_by('version_number')


class StudentInvoice(models.Model):
    """Student invoice - automatically generated for each semester"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partially Paid'),
        ('paid', 'Fully Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='invoices')
    invoice_number = models.CharField(max_length=50, unique=True, db_index=True)
    semester_number = models.IntegerField(validators=[MinValueValidator(1)], help_text="Course semester number (1, 2, 3...)")
    academic_year = models.CharField(max_length=20, help_text="Academic year (e.g., 2024/2025)")
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    date_created = models.DateTimeField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'student_invoices'
        ordering = ['-date_created']
        unique_together = ['student', 'semester_number']
        indexes = [
            models.Index(fields=['student', 'semester_number']),
            models.Index(fields=['status']),
            models.Index(fields=['invoice_number']),
            models.Index(fields=['academic_year']),
        ]
    
    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.student.admission_number} - Semester {self.semester_number}"
    
    def save(self, *args, **kwargs):
        # Auto-generate invoice number if not provided
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        
        # For new invoices, set default status
        is_new = self.pk is None
        if is_new and not self.status:
            # Set initial status based on due date
            if self.due_date and timezone.now().date() > self.due_date:
                self.status = 'overdue'
            else:
                self.status = 'pending'
        
        # Save first to get primary key
        super().save(*args, **kwargs)
        
        # Update status based on payments (only after saving, so we can access payments)
        if not is_new:  # Only update status for existing invoices
            old_status = self.status
            self.update_status()
            # Save again if status changed
            if old_status != self.status:
                super().save(update_fields=['status'])
    
    def generate_invoice_number(self):
        """Generate unique invoice number"""
        from datetime import datetime
        college_prefix = self.student.college.name[:3].upper().replace(' ', '')
        date_str = datetime.now().strftime('%Y%m%d')
        prefix = f"INV-{college_prefix}-{date_str}"
        
        last_invoice = StudentInvoice.objects.filter(
            invoice_number__startswith=prefix
        ).order_by('-invoice_number').first()
        
        if last_invoice:
            try:
                last_num = int(last_invoice.invoice_number.split('-')[-1])
                new_num = last_num + 1
            except (ValueError, IndexError):
                new_num = 1
        else:
            new_num = 1
        
        return f"{prefix}-{new_num:04d}"
    
    def get_total_paid(self):
        """Calculate total payments made against this invoice"""
        # Only calculate if invoice has been saved (has primary key)
        if not self.pk:
            return Decimal('0.00')
        
        from django.db.models import Sum
        total = self.payments.aggregate(total=Sum('amount_paid'))['total']
        return total or Decimal('0.00')
    
    def get_balance(self):
        """Calculate outstanding balance for this invoice"""
        return self.fee_amount - self.get_total_paid()
    
    def update_status(self):
        """Update invoice status based on payments"""
        # Only update if invoice has been saved (has primary key)
        if not self.pk:
            return
        
        total_paid = self.get_total_paid()
        
        if total_paid >= self.fee_amount:
            self.status = 'paid'
        elif total_paid > Decimal('0.00'):
            self.status = 'partial'
        elif self.status != 'cancelled':
            # Check if overdue
            if self.due_date and timezone.now().date() > self.due_date:
                self.status = 'overdue'
            else:
                self.status = 'pending'


class Payment(models.Model):
    """Payment records - includes scholarship payments"""
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('mpesa', 'MPesa'),
        ('bank_transfer', 'Bank Transfer'),
        ('bank_deposit', 'Bank Deposit'),
        ('cheque', 'Cheque'),
        ('scholarship', 'Scholarship'),
        ('other', 'Other'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='payments')
    invoice = models.ForeignKey(StudentInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments', help_text="Invoice this payment is for (optional)")
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHOD_CHOICES)
    transaction_code = models.CharField(max_length=100, blank=True, null=True, 
                                       help_text="MPesa code, cheque number, bank reference, etc.")
    semester_number = models.IntegerField(null=True, blank=True, help_text="Semester number this payment is for (optional)")
    academic_year = models.CharField(max_length=20, blank=True, null=True, help_text="Academic year (e.g., 2024/2025)")
    date_paid = models.DateTimeField(default=timezone.now)
    receipt_number = models.CharField(max_length=50, unique=True, null=True, blank=True, db_index=True)
    notes = models.TextField(blank=True, null=True)
    recorded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='recorded_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payments'
        ordering = ['-date_paid']
        indexes = [
            models.Index(fields=['student', 'date_paid']),
            models.Index(fields=['payment_method']),
            models.Index(fields=['receipt_number']),
            models.Index(fields=['invoice']),
        ]
    
    def __str__(self):
        return f"Payment {self.receipt_number or self.id} - {self.student.admission_number} - KES {self.amount_paid}"
    
    def save(self, *args, **kwargs):
        # Auto-generate receipt number if not provided
        if not self.receipt_number:
            self.receipt_number = self.generate_receipt_number()
        
        super().save(*args, **kwargs)
        
        # Update invoice status after payment is saved
        if self.invoice:
            self.invoice.update_status()
            self.invoice.save()
    
    def generate_receipt_number(self):
        """Generate unique receipt number"""
        from datetime import datetime
        prefix = f"RCP-{self.student.college.name[:3].upper()}-{datetime.now().strftime('%Y%m%d')}"
        last_payment = Payment.objects.filter(
            receipt_number__startswith=prefix
        ).order_by('-receipt_number').first()
        
        if last_payment:
            try:
                last_num = int(last_payment.receipt_number.split('-')[-1])
                new_num = last_num + 1
            except (ValueError, IndexError):
                new_num = 1
        else:
            new_num = 1
        
        return f"{prefix}-{new_num:04d}"


# Encryption helper for sensitive data
def get_encryption_key():
    """Get or generate encryption key from settings"""
    key = getattr(settings, 'ENCRYPTION_KEY', None)
    if not key:
        # Generate a key from SECRET_KEY if no encryption key is set
        key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(key[:32])
    else:
        if isinstance(key, str):
            key = key.encode()
    return key


def encrypt_value(value):
    """Encrypt a string value"""
    if not value:
        return value
    try:
        f = Fernet(get_encryption_key())
        encrypted = f.encrypt(value.encode())
        return encrypted.decode()
    except Exception as e:
        # If encryption fails, return as is (for development)
        # In production, you should handle this properly
        import logging
        logging.warning(f"Encryption failed: {str(e)}")
        return value


def decrypt_value(encrypted_value):
    """Decrypt an encrypted string value"""
    if not encrypted_value:
        return encrypted_value
    try:
        f = Fernet(get_encryption_key())
        decrypted = f.decrypt(encrypted_value.encode())
        return decrypted.decode()
    except Exception as e:
        # If decryption fails, return as is (might be unencrypted from old data)
        import logging
        logging.warning(f"Decryption failed: {str(e)}")
        return encrypted_value


class DarajaSettings(models.Model):
    """Daraja M-Pesa API settings for college - Only Director can edit"""
    ACCOUNT_TYPE_CHOICES = [
        ('paybill', 'Paybill Number'),
        ('till', 'Till Number'),
    ]
    
    college = models.OneToOneField(College, on_delete=models.CASCADE, related_name='daraja_settings')
    
    # Account Type
    account_type = models.CharField(
        max_length=10,
        choices=ACCOUNT_TYPE_CHOICES,
        default='paybill',
        help_text="Select Paybill or Till Number"
    )
    
    # Account Details
    paybill_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Paybill Number (e.g., 123456)"
    )
    till_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Till Number (e.g., 123456)"
    )
    
    # Daraja API Credentials (encrypted)
    consumer_key = models.TextField(
        blank=True,
        null=True,
        help_text="Daraja API Consumer Key from Safaricom Developer Portal"
    )
    consumer_secret = models.TextField(
        blank=True,
        null=True,
        help_text="Daraja API Consumer Secret from Safaricom Developer Portal"
    )
    passkey = models.TextField(
        blank=True,
        null=True,
        help_text="Daraja API Passkey (Lipa na M-Pesa Online Passkey)"
    )
    shortcode = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Business Shortcode (same as Paybill/Till number)"
    )
    
    # Configuration
    is_active = models.BooleanField(
        default=False,
        help_text="Enable M-Pesa payments for this college"
    )
    is_test_mode = models.BooleanField(
        default=True,
        help_text="Use Daraja Sandbox for testing (disable for production)"
    )
    
    # Callback URLs
    callback_url = models.URLField(
        blank=True,
        null=True,
        help_text="Callback URL for payment confirmations (auto-generated if blank)"
    )
    
    # Additional settings
    account_reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Account Reference prefix (e.g., 'FEE' - will be appended with student admission number)"
    )
    transaction_description = models.CharField(
        max_length=100,
        default='Fee Payment',
        help_text="Transaction description shown in M-Pesa prompt"
    )
    
    # Bank Account Details for Display Only (NOT used in STK Push payment flow)
    # IMPORTANT: These fields are for displaying payment instructions to students only.
    # They are NOT sent to Daraja API and do NOT affect PayBill → Bank settlement.
    # Settlement is handled automatically by Safaricom based on PayBill configuration.
    bank_name = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Bank Name (e.g., Equity Bank, KCB, Co-operative Bank) - Display only, not used in payment flow"
    )
    bank_account_name = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Account Name (e.g., Cambridge College)"
    )
    bank_account_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Bank Account Number"
    )
    bank_branch = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Bank Branch Name"
    )
    bank_swift_code = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="SWIFT/BIC Code (for international transfers)"
    )
    bank_transfer_instructions = models.TextField(
        blank=True,
        null=True,
        help_text="Additional instructions for bank transfers (e.g., 'Use admission number as reference')"
    )
    bank_transfers_enabled = models.BooleanField(
        default=False,
        help_text="Enable direct bank transfer payments"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'daraja_settings'
        verbose_name = 'Daraja M-Pesa Settings'
        verbose_name_plural = 'Daraja M-Pesa Settings'
    
    def __str__(self):
        return f"Daraja Settings - {self.college.name}"
    
    def save(self, *args, **kwargs):
        # Always enforce PayBill (TransactionType: CustomerPayBillOnline)
        self.account_type = 'paybill'
        
        # Encrypt sensitive fields before saving
        if self.consumer_key and not self.consumer_key.startswith('gAAAAAB'):
            self.consumer_key = encrypt_value(self.consumer_key)
        if self.consumer_secret and not self.consumer_secret.startswith('gAAAAAB'):
            self.consumer_secret = encrypt_value(self.consumer_secret)
        if self.passkey and not self.passkey.startswith('gAAAAAB'):
            self.passkey = encrypt_value(self.passkey)
        
        # Set shortcode from PayBill number if not provided
        if not self.shortcode and self.paybill_number:
            self.shortcode = self.paybill_number
        
        super().save(*args, **kwargs)
    
    def get_consumer_key(self):
        """Get decrypted consumer key"""
        if self.consumer_key:
            return decrypt_value(self.consumer_key)
        return None
    
    def get_consumer_secret(self):
        """Get decrypted consumer secret"""
        if self.consumer_secret:
            return decrypt_value(self.consumer_secret)
        return None
    
    def get_passkey(self):
        """Get decrypted passkey"""
        if self.passkey:
            return decrypt_value(self.passkey)
        return None
    
    def get_account_number(self):
        """Get the PayBill number (always PayBill, no Till option)"""
        return self.paybill_number


class DailyExpenditure(models.Model):
    """Daily expenditure entries with draft and submission workflow"""
    ROLE_CHOICES = [
        ('principal', 'Principal'),
        ('accounts_officer', 'Accounts Officer'),
    ]
    
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='daily_expenditures')
    entered_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='daily_expenditures')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, blank=True, null=True, help_text="Role of person entering the expenditure (auto-set)")
    description = models.TextField(help_text="Description of the expenditure")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], help_text="Expenditure amount")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Date and time when entry was created (auto-set, not editable)")
    submitted = models.BooleanField(default=False, help_text="Whether this entry has been submitted (draft if False)")
    submitted_at = models.DateTimeField(null=True, blank=True, help_text="Date and time when entry was submitted")
    
    class Meta:
        db_table = 'daily_expenditures'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['college', 'created_at']),
            models.Index(fields=['college', 'submitted', 'created_at']),
            models.Index(fields=['entered_by', 'submitted']),
        ]
    
    def __str__(self):
        status = "Submitted" if self.submitted else "Draft"
        return f"{self.description[:50]} - KES {self.amount} ({status}) - {self.created_at.strftime('%Y-%m-%d')}"
    
    def save(self, *args, **kwargs):
        # Auto-set role based on user if not provided
        if not self.role and self.entered_by:
            if self.entered_by.is_principal():
                self.role = 'principal'
            elif self.entered_by.is_accounts_officer():
                self.role = 'accounts_officer'
        
        # Set submitted_at when submitted
        if self.submitted and not self.submitted_at:
            self.submitted_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    @classmethod
    def get_daily_total(cls, college, date=None):
        """Get total expenditure for a specific date (submitted entries only)"""
        if date is None:
            date = timezone.now().date()
        
        total = cls.objects.filter(
            college=college,
            created_at__date=date,
            submitted=True
        ).aggregate(total=models.Sum('amount'))['total']
        
        return total or Decimal('0.00')
    
    @classmethod
    def get_cumulative_by_date(cls, college, start_date=None, end_date=None):
        """
        Get cumulative expenditure totals by date for line graph.
        Returns a list of dicts with 'date' and 'cumulative_total' keys.
        """
        if start_date is None:
            # Default to start of current semester
            from education.models import College
            try:
                college_obj = College.objects.get(pk=college.pk if hasattr(college, 'pk') else college)
                # Use current academic year start or 3 months ago as fallback
                start_date = timezone.now().date() - timedelta(days=90)
            except:
                start_date = timezone.now().date() - timedelta(days=90)
        
        if end_date is None:
            end_date = timezone.now().date()
        
        # Get all submitted expenditures in date range
        expenditures = cls.objects.filter(
            college=college,
            submitted=True,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).order_by('created_at__date')
        
        # Group by date and calculate cumulative
        daily_totals = {}
        for exp in expenditures:
            date = exp.created_at.date()
            if date not in daily_totals:
                daily_totals[date] = Decimal('0.00')
            daily_totals[date] += exp.amount
        
        # Build cumulative data
        cumulative_data = []
        cumulative_total = Decimal('0.00')
        
        # Generate all dates in range
        current_date = start_date
        while current_date <= end_date:
            if current_date in daily_totals:
                cumulative_total += daily_totals[current_date]
            
            cumulative_data.append({
                'date': current_date.isoformat(),
                'cumulative_total': float(cumulative_total)
            })
            
            current_date += timedelta(days=1)
        
        return cumulative_data


class FeeItem(models.Model):
    """Master list of all possible fee items (no amounts stored here)"""
    name = models.CharField(max_length=200, unique=True, help_text="Name of the fee item (e.g., Tuition Fee, Registration Fee)")
    description = models.TextField(blank=True, null=True, help_text="Description of what this fee item covers")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'fee_items'
        ordering = ['name']
        verbose_name = 'Fee Item'
        verbose_name_plural = 'Fee Items'
    
    def __str__(self):
        return self.name


class CourseFeeStructure(models.Model):
    """Fee structure linking courses to fee items with amounts per semester"""
    course = models.ForeignKey(CollegeCourse, on_delete=models.CASCADE, related_name='course_fee_structures')
    fee_item = models.ForeignKey(FeeItem, on_delete=models.CASCADE, related_name='course_fee_structures')
    semester_number = models.IntegerField(validators=[MinValueValidator(1)], help_text="Semester position in course (1, 2, 3... up to total semesters)")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'course_fee_structures'
        unique_together = ['course', 'fee_item', 'semester_number']
        ordering = ['course', 'semester_number', 'fee_item']
        indexes = [
            models.Index(fields=['course']),
            models.Index(fields=['fee_item']),
            models.Index(fields=['course', 'semester_number']),
        ]
        verbose_name = 'Course Fee Structure'
        verbose_name_plural = 'Course Fee Structures'
    
    def __str__(self):
        return f"{self.course.name} - Semester {self.semester_number} - {self.fee_item.name}: KES {self.amount}"