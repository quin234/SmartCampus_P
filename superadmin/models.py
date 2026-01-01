from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from education.models import College


class CollegePaymentConfig(models.Model):
    """Payment configuration per college - set by Super Admin"""
    PAYMENT_PERIOD_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semester', 'Per Semester'),
        ('yearly', 'Yearly'),
        ('custom', 'Custom Days'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    college = models.OneToOneField(College, on_delete=models.CASCADE, related_name='payment_config')
    branch = models.ForeignKey(College, on_delete=models.CASCADE, null=True, blank=True, related_name='branch_payment_configs', help_text="If this is a branch-specific config")
    
    # Payment Amount
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], help_text="Payment amount in KES")
    
    # Payment Period/Validity
    payment_period = models.CharField(max_length=20, choices=PAYMENT_PERIOD_CHOICES, default='monthly', help_text="Payment period type")
    validity_days = models.IntegerField(validators=[MinValueValidator(1)], default=30, help_text="Number of days payment is valid (for custom period)")
    
    # M-Pesa Configuration
    paybill_number = models.CharField(max_length=20, blank=True, default='', help_text="Paybill number / shortcode")
    account_reference_format = models.CharField(max_length=100, default='COLLEGE-{college_id}', help_text="Account reference format (use {college_id}, {college_name}, {branch_id})")
    
    # Callback URLs
    callback_url = models.URLField(blank=True, null=True, help_text="Callback URL for payment confirmations (auto-generated if blank)")
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', help_text="Whether this payment config is active")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('education.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_payment_configs')
    
    class Meta:
        db_table = 'college_payment_configs'
        verbose_name = 'College Payment Configuration'
        verbose_name_plural = 'College Payment Configurations'
        indexes = [
            models.Index(fields=['college', 'status']),
            models.Index(fields=['branch', 'status']),
        ]
    
    def __str__(self):
        college_name = self.branch.name if self.branch else self.college.name
        return f"Payment Config - {college_name} (KES {self.amount})"
    
    def get_account_reference(self):
        """Generate account reference based on format"""
        ref = self.account_reference_format
        ref = ref.replace('{college_id}', str(self.college.id))
        ref = ref.replace('{college_name}', self.college.name[:20])
        if self.branch:
            ref = ref.replace('{branch_id}', str(self.branch.id))
            ref = ref.replace('{branch_name}', self.branch.name[:20])
        return ref
    
    def get_validity_end_date(self, start_date=None):
        """Calculate when payment validity expires"""
        if start_date is None:
            start_date = timezone.now().date()
        
        if self.payment_period == 'monthly':
            return start_date + timedelta(days=30)
        elif self.payment_period == 'quarterly':
            return start_date + timedelta(days=90)
        elif self.payment_period == 'semester':
            # Assume 4 months per semester
            return start_date + timedelta(days=120)
        elif self.payment_period == 'yearly':
            return start_date + timedelta(days=365)
        else:  # custom
            return start_date + timedelta(days=self.validity_days)


class CollegePayment(models.Model):
    """College payment records - tracks M-Pesa payments for college subscriptions"""
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='college_payments')
    branch = models.ForeignKey(College, on_delete=models.CASCADE, null=True, blank=True, related_name='branch_payments', help_text="Branch college if payment is for a branch")
    config = models.ForeignKey(CollegePaymentConfig, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments', help_text="Payment configuration used")
    
    # Payment Amount
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    
    # M-Pesa Transaction Details
    merchant_request_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    checkout_request_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    receipt_number = models.CharField(max_length=100, blank=True, null=True, db_index=True, help_text="M-Pesa receipt number")
    phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="Phone number used for payment")
    
    # Payment Status
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    
    # Dates
    payment_date = models.DateTimeField(null=True, blank=True, help_text="When payment was completed")
    valid_from = models.DateField(null=True, blank=True, help_text="Payment validity start date")
    valid_until = models.DateField(null=True, blank=True, help_text="Payment validity end date")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'college_payments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['college', 'status']),
            models.Index(fields=['branch', 'status']),
            models.Index(fields=['merchant_request_id']),
            models.Index(fields=['checkout_request_id']),
            models.Index(fields=['receipt_number']),
            models.Index(fields=['payment_date']),
        ]
        verbose_name = 'College Payment'
        verbose_name_plural = 'College Payments'
    
    def __str__(self):
        college_name = self.branch.name if self.branch else self.college.name
        return f"Payment - {college_name} - KES {self.amount} ({self.get_status_display()})"
    
    def is_valid(self):
        """Check if payment is still valid (not expired)"""
        if not self.valid_until:
            return False
        return timezone.now().date() <= self.valid_until
    
    def get_payment_status_display(self):
        """Get payment status with expiration check"""
        if self.status == 'completed':
            if self.is_valid():
                return 'Paid'
            else:
                return 'Expired'
        elif self.status == 'pending':
            return 'Unpaid'
        elif self.status == 'processing':
            return 'Processing'
        elif self.status == 'failed':
            return 'Failed'
        else:
            return self.get_status_display()
