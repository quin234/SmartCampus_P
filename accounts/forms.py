from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Department, FeeStructure, Payment, AccountsSettings, DarajaSettings, DailyExpenditure
from education.models import Student, CollegeCourse, College


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['department_name']
        widgets = {
            'department_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter department name'
            })
        }


    def clean_academic_year(self):
        academic_year = self.cleaned_data.get('academic_year')
        if academic_year:
            import re
            pattern = r'^\d{4}/\d{4}$'
            if not re.match(pattern, academic_year):
                raise ValidationError('Academic year must be in format YYYY/YYYY (e.g., 2024/2025)')
            
            try:
                year1, year2 = academic_year.split('/')
                year1_int = int(year1)
                year2_int = int(year2)
                if year2_int != year1_int + 1:
                    raise ValidationError('Academic year second part must be one year after the first')
            except ValueError:
                raise ValidationError('Invalid academic year format')
        
        return academic_year


class FeeStructureForm(forms.ModelForm):
    class Meta:
        model = FeeStructure
        fields = ['course', 'semester_number', 'amount', 'fee_type', 'description', 
                 'effective_from', 'is_active']
        widgets = {
            'course': forms.Select(attrs={
                'class': 'form-control',
                'id': 'id_course'
            }),
            'semester_number': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'id': 'id_semester_number'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'fee_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'effective_from': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    
    def __init__(self, *args, **kwargs):
        college = kwargs.pop('college', None)
        super().__init__(*args, **kwargs)
        
        if college:
            self.fields['course'].queryset = CollegeCourse.objects.filter(college=college)
            
            # Set max semester_number based on selected course
            if self.instance and self.instance.pk:
                # Editing existing
                if self.instance.course:
                    max_semesters = self.instance.get_total_semesters()
                    if max_semesters:
                        self.fields['semester_number'].widget.attrs['max'] = max_semesters
                        self.fields['semester_number'].help_text = f'Must be between 1 and {max_semesters}'
        
        # Set default effective_from to today
        if not self.instance.pk:
            from django.utils import timezone
            self.fields['effective_from'].initial = timezone.now().date()
        
        # Make version fields read-only for non-admins (handled in template)
        if self.instance and self.instance.pk:
            self.fields['effective_from'].widget.attrs['readonly'] = True
    
    def clean_semester_number(self):
        semester_number = self.cleaned_data.get('semester_number')
        course = self.cleaned_data.get('course')
        
        if semester_number and course:
            # Get college from form instance or course
            college = course.college if hasattr(course, 'college') else None
            if not college and self.instance and self.instance.college:
                college = self.instance.college
            
            if college:
                total_semesters = course.get_total_semesters(college)
                if total_semesters and semester_number > total_semesters:
                    raise ValidationError(
                        f'Semester number ({semester_number}) cannot exceed total semesters ({total_semesters})'
                    )
                if semester_number < 1:
                    raise ValidationError('Semester number must be at least 1')
        
        return semester_number


class SponsorshipSettingsForm(forms.ModelForm):
    class Meta:
        model = AccountsSettings
        fields = ['sponsorship_enabled', 'sponsorship_default_discount_type', 'sponsorship_default_discount_value']
        widgets = {
            'sponsorship_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'sponsorship_default_discount_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'sponsorship_default_discount_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            })
        }
    
    def clean_sponsorship_default_discount_value(self):
        discount_value = self.cleaned_data.get('sponsorship_default_discount_value')
        discount_type = self.cleaned_data.get('sponsorship_default_discount_type')
        
        if discount_value is not None:
            if discount_type == 'percentage':
                if discount_value < 0 or discount_value > 100:
                    raise ValidationError('Percentage discount must be between 0 and 100')
            else:  # fixed_amount
                if discount_value < 0:
                    raise ValidationError('Fixed amount discount must be positive')
        
        return discount_value


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['student', 'amount_paid', 'payment_method', 'transaction_code', 
                 'semester_number', 'academic_year', 'date_paid', 'notes']
        widgets = {
            'student': forms.Select(attrs={
                'class': 'form-control',
                'id': 'id_student_select'
            }),
            'amount_paid': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01'
            }),
            'payment_method': forms.Select(attrs={
                'class': 'form-control'
            }),
            'transaction_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'MPesa code, cheque number, etc.'
            }),
            'semester_number': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'placeholder': 'Optional: Semester number'
            }),
            'academic_year': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'YYYY/YYYY (e.g., 2024/2025)'
            }),
            'date_paid': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            })
        }
    
    def __init__(self, *args, **kwargs):
        college = kwargs.pop('college', None)
        super().__init__(*args, **kwargs)
        
        if college:
            students = Student.objects.filter(college=college).order_by('admission_number', 'full_name')
            self.fields['student'].queryset = students
            
            # Format choices to show admission number and name for better searchability
            self.fields['student'].label_from_instance = lambda obj: f"{obj.admission_number} - {obj.full_name}"
            
            # Make semester and academic_year optional
            self.fields['semester_number'].required = False
            self.fields['academic_year'].required = False


class DarajaSettingsForm(forms.ModelForm):
    class Meta:
        model = DarajaSettings
        fields = [
            'paybill_number',
            'consumer_key', 'consumer_secret', 'passkey', 'shortcode',
            'is_active', 'is_test_mode', 'callback_url',
            'account_reference', 'transaction_description',
            'bank_name', 'bank_account_name', 'bank_account_number',
            'bank_branch', 'bank_swift_code', 'bank_transfer_instructions',
            'bank_transfers_enabled'
        ]
        widgets = {
            'paybill_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 123456',
                'id': 'id_paybill_number'
            }),
            'consumer_key': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'password',
                'placeholder': 'Enter Consumer Key',
                'autocomplete': 'new-password'
            }),
            'consumer_secret': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'password',
                'placeholder': 'Enter Consumer Secret',
                'autocomplete': 'new-password'
            }),
            'passkey': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'password',
                'placeholder': 'Enter Passkey',
                'autocomplete': 'new-password'
            }),
            'shortcode': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Auto-filled from Paybill/Till number'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_test_mode': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'callback_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'Auto-generated if left blank'
            }),
            'account_reference': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., FEE (optional)'
            }),
            'transaction_description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Fee Payment'
            }),
            'bank_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Equity Bank, KCB, Co-operative Bank'
            }),
            'bank_account_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Cambridge College'
            }),
            'bank_account_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 1234567890'
            }),
            'bank_branch': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Nairobi Branch'
            }),
            'bank_swift_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., EQBLKENA (optional)'
            }),
            'bank_transfer_instructions': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'e.g., Use your admission number as the payment reference'
            }),
            'bank_transfers_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make password fields show/hide toggle
        if self.instance and self.instance.pk:
            # If editing, show placeholder that values are set
            if self.instance.consumer_key:
                self.fields['consumer_key'].widget.attrs['placeholder'] = '•••••••• (click to change)'
            if self.instance.consumer_secret:
                self.fields['consumer_secret'].widget.attrs['placeholder'] = '•••••••• (click to change)'
            if self.instance.passkey:
                self.fields['passkey'].widget.attrs['placeholder'] = '•••••••• (click to change)'
    
    def clean(self):
        cleaned_data = super().clean()
        paybill_number = cleaned_data.get('paybill_number')
        
        # Validate PayBill number (always required, no Till option)
        if paybill_number:
            if not paybill_number.isdigit():
                raise ValidationError({'paybill_number': 'Paybill number must contain only digits.'})
        
        # Validate ALL required fields when is_active is True (mandatory for PayBill → Bank settlement)
        # NOTE: Bank details (bank_name, bank_account_number, etc.) are NOT validated here
        # because they are display-only and NOT used in STK Push payment flow
        if cleaned_data.get('is_active'):
            # PayBill number is mandatory
            if not paybill_number:
                raise ValidationError({'paybill_number': 'Paybill number is required when M-Pesa payments are enabled.'})
            
            # Core credentials (mandatory)
            if not cleaned_data.get('consumer_key'):
                # Check if existing instance has consumer_key (encrypted values start with 'gAAAAAB')
                if not (self.instance and self.instance.pk and self.instance.consumer_key):
                    raise ValidationError({'consumer_key': 'Consumer Key is required when M-Pesa payments are enabled.'})
            if not cleaned_data.get('consumer_secret'):
                if not (self.instance and self.instance.pk and self.instance.consumer_secret):
                    raise ValidationError({'consumer_secret': 'Consumer Secret is required when M-Pesa payments are enabled.'})
            if not cleaned_data.get('passkey'):
                if not (self.instance and self.instance.pk and self.instance.passkey):
                    raise ValidationError({'passkey': 'Passkey is required when M-Pesa payments are enabled.'})
            
            # PayBill Shortcode (mandatory - used as BusinessShortCode/PartyB in STK Push)
            # This must match the PayBill number configured for bank settlement
            # TransactionType is always CustomerPayBillOnline (enforced in DarajaService)
            if not cleaned_data.get('shortcode'):
                # Auto-set from paybill_number
                if paybill_number:
                    cleaned_data['shortcode'] = paybill_number
                else:
                    raise ValidationError({
                        'shortcode': 'PayBill Shortcode is required when M-Pesa payments are enabled. '
                                   'This must match your PayBill number configured for bank settlement.'
                    })
            
            # Callback URL (can be auto-generated, but validate environment)
            callback_url = cleaned_data.get('callback_url')
            if not callback_url:
                # Will be auto-generated in view if BASE_URL is configured
                pass
            
            # Account Reference Template (has default 'FEE', but validate if provided)
            # Transaction Description (has default 'Fee Payment', but validate if provided)
            # These are optional and have defaults in the model/service
        
        # Validate bank account fields when bank_transfers_enabled is True
        if cleaned_data.get('bank_transfers_enabled'):
            if not cleaned_data.get('bank_name'):
                raise ValidationError({'bank_name': 'Bank name is required when bank transfers are enabled.'})
            if not cleaned_data.get('bank_account_name'):
                raise ValidationError({'bank_account_name': 'Bank account name is required when bank transfers are enabled.'})
            if not cleaned_data.get('bank_account_number'):
                raise ValidationError({'bank_account_number': 'Bank account number is required when bank transfers are enabled.'})
        
        return cleaned_data


class DailyExpenditureForm(forms.ModelForm):
    """Form for creating/editing daily expenditure drafts (Principal/Accounts only)"""
    class Meta:
        model = DailyExpenditure
        fields = ['description', 'amount']
        widgets = {
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter expense description',
                'required': True
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '0.00',
                'required': True
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.college = kwargs.pop('college', None)
        self.is_submitted = kwargs.pop('is_submitted', False)
        super().__init__(*args, **kwargs)
        
        # If submitted, make all fields read-only
        if self.is_submitted:
            for field in self.fields.values():
                field.widget.attrs['readonly'] = True
                field.widget.attrs['disabled'] = True
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount and amount <= 0:
            raise ValidationError('Amount must be greater than zero.')
        return amount
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        if self.user:
            instance.entered_by = self.user
            # Auto-set role based on user
            if self.user.is_principal():
                instance.role = 'principal'
            elif self.user.is_accounts_officer():
                instance.role = 'accounts_officer'
        
        if self.college:
            instance.college = self.college
        
        # Ensure created_at is set (auto-set by model, but ensure it's not editable)
        if not instance.pk:
            instance.created_at = timezone.now()
        
        if commit:
            instance.save()
        
        return instance
