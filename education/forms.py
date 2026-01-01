from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import (
    College, CustomUser, Student, CollegeCourse, CollegeUnit,
    Enrollment, Result, GlobalCourse, GlobalUnit, PasswordResetCode
)


class CollegeRegistrationForm(forms.ModelForm):
    """Form for college registration"""
    class Meta:
        model = College
        fields = ['name', 'address', 'county', 'email', 'phone', 'principal_name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'county': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'principal_name': forms.TextInput(attrs={'class': 'form-control'}),
        }


class UserRegistrationForm(forms.ModelForm):
    """Form for creating users"""
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    password_confirm = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input'}), label='Confirm Password')
    
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'role', 'password']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'phone': forms.TextInput(attrs={'class': 'form-input'}),
            'role': forms.Select(attrs={'class': 'form-input'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Passwords do not match.")
        
        return cleaned_data


class StudentForm(forms.ModelForm):
    """Form for student registration"""
    class Meta:
        model = Student
        fields = ['admission_number', 'full_name', 'course', 'year_of_study', 'gender', 
                  'date_of_birth', 'email', 'phone', 'current_semester', 'status',
                  'has_ream_paper', 'is_sponsored', 'sponsorship_discount_type', 'sponsorship_discount_value']
        widgets = {
            'admission_number': forms.TextInput(attrs={'class': 'form-input'}),
            'full_name': forms.TextInput(attrs={'class': 'form-input'}),
            'course': forms.Select(attrs={'class': 'form-input'}),
            'year_of_study': forms.NumberInput(attrs={'class': 'form-input', 'min': 1, 'max': 5}),
            'gender': forms.Select(attrs={'class': 'form-input'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'phone': forms.TextInput(attrs={'class': 'form-input'}),
            'current_semester': forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
            'status': forms.Select(attrs={'class': 'form-input'}),
            'has_ream_paper': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_sponsored': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sponsorship_discount_type': forms.Select(attrs={'class': 'form-input'}),
            'sponsorship_discount_value': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': 0}),
        }
    
    def __init__(self, *args, **kwargs):
        college = kwargs.pop('college', None)
        super().__init__(*args, **kwargs)
        
        # Store college for validation in clean method
        self.college = college
        
        # Set course queryset if college provided
        if college:
            self.fields['course'].queryset = CollegeCourse.objects.filter(college=college)
            self.fields['course'].required = False
            self.fields['course'].empty_label = '-- Select Course (Optional) --'
        
        # Set current_semester max based on college settings
        if college:
            max_semesters = college.semesters_per_year
            self.fields['current_semester'].widget.attrs['max'] = max_semesters
            self.fields['current_semester'].help_text = f'Must be between 1 and {max_semesters} (based on college settings)'
            self.fields['current_semester'].required = False
        else:
            # Default to 12 if college not provided
            self.fields['current_semester'].widget.attrs['max'] = 12
        
        # Set default current_semester to 1 for new students
        if not self.instance.pk:
            self.fields['current_semester'].initial = 1
        
        # Set status default and make optional
        self.fields['status'].required = False
        if not self.instance.pk:
            self.fields['status'].initial = 'active'
        
        # Make ream paper and sponsorship fields optional
        self.fields['has_ream_paper'].required = False
        self.fields['is_sponsored'].required = False
        self.fields['sponsorship_discount_type'].required = False
        self.fields['sponsorship_discount_value'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        course = cleaned_data.get('course')
        year_of_study = cleaned_data.get('year_of_study')
        current_semester = cleaned_data.get('current_semester')
        is_sponsored = cleaned_data.get('is_sponsored')
        sponsorship_discount_type = cleaned_data.get('sponsorship_discount_type')
        sponsorship_discount_value = cleaned_data.get('sponsorship_discount_value')
        
        # Validate year_of_study against course duration
        if course and year_of_study:
            if year_of_study > course.duration_years:
                raise forms.ValidationError({
                    'year_of_study': f'Year of study ({year_of_study}) cannot exceed course duration ({course.duration_years} years)'
                })
        
        # Validate current_semester against college semesters_per_year
        if current_semester:
            # Get college from form instance or instance
            college = self.college
            if not college and self.instance and self.instance.college:
                college = self.instance.college
            
            if college and current_semester > college.semesters_per_year:
                raise forms.ValidationError({
                    'current_semester': f'Semester ({current_semester}) cannot exceed college semesters per year ({college.semesters_per_year})'
                })
            elif current_semester < 1:
                raise forms.ValidationError({
                    'current_semester': 'Semester must be at least 1'
                })
        
        # Validate sponsorship fields
        if is_sponsored:
            if not sponsorship_discount_type:
                raise forms.ValidationError({
                    'sponsorship_discount_type': 'Discount type is required when student is sponsored'
                })
            if not sponsorship_discount_value:
                raise forms.ValidationError({
                    'sponsorship_discount_value': 'Discount value is required when student is sponsored'
                })
            if sponsorship_discount_type == 'percentage' and (sponsorship_discount_value < 0 or sponsorship_discount_value > 100):
                raise forms.ValidationError({
                    'sponsorship_discount_value': 'Percentage discount must be between 0 and 100'
                })
        
        return cleaned_data


class CollegeCourseForm(forms.ModelForm):
    """Form for college course"""
    class Meta:
        model = CollegeCourse
        fields = ['global_course', 'code', 'name', 'duration_years', 'admission_requirements']
        widgets = {
            'global_course': forms.Select(attrs={'class': 'form-input'}),
            'code': forms.TextInput(attrs={'class': 'form-input', 'style': 'text-transform: uppercase;'}),
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'duration_years': forms.NumberInput(attrs={'class': 'form-input', 'min': 1, 'max': 5}),
            'admission_requirements': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['global_course'].required = False
        self.fields['global_course'].queryset = GlobalCourse.objects.all()
        self.fields['global_course'].empty_label = '-- Select Global Course (Optional) --'
        self.fields['code'].required = True
    
    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip().upper()
        return code


class CollegeUnitForm(forms.ModelForm):
    """Form for college unit"""
    class Meta:
        model = CollegeUnit
        fields = ['global_unit', 'name', 'code', 'semester', 'assigned_lecturer']
        widgets = {
            'global_unit': forms.Select(attrs={'class': 'form-input'}),
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'code': forms.TextInput(attrs={'class': 'form-input'}),
            'semester': forms.Select(attrs={'class': 'form-input'}),
            'assigned_lecturer': forms.Select(attrs={'class': 'form-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        college = kwargs.pop('college', None)
        super().__init__(*args, **kwargs)
        self.fields['global_unit'].required = False
        self.fields['global_unit'].queryset = GlobalUnit.objects.all()
        self.fields['global_unit'].empty_label = '-- Select Global Unit (Optional) --'
        self.fields['assigned_lecturer'].required = False
        self.fields['assigned_lecturer'].empty_label = '-- No Lecturer Assigned --'
        
        # Dynamically set semester choices based on college's semesters_per_year
        if college:
            max_semesters = college.semesters_per_year
            self.fields['semester'].choices = [(i, f'Semester {i}') for i in range(1, max_semesters + 1)]
        else:
            # Default to 2 semesters if college not provided
            self.fields['semester'].choices = [(1, 'Semester 1'), (2, 'Semester 2')]


class EnrollmentForm(forms.ModelForm):
    """Form for student enrollment"""
    class Meta:
        model = Enrollment
        fields = ['student', 'unit', 'academic_year', 'semester']
        widgets = {
            'student': forms.Select(attrs={'class': 'form-control'}),
            'unit': forms.Select(attrs={'class': 'form-control'}),
            'academic_year': forms.Select(attrs={'class': 'form-control'}),
            'semester': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 12}),
        }
    
    def __init__(self, *args, **kwargs):
        college = kwargs.pop('college', None)
        super().__init__(*args, **kwargs)
        # Update max semester based on college's semesters_per_year
        if college:
            max_semesters = college.semesters_per_year
            self.fields['semester'].widget.attrs['max'] = max_semesters
            # Set academic year choices dynamically based on college's current_academic_year
            self.fields['academic_year'].choices = college.get_academic_year_choices(years_before=2, years_after=3)
            # Default to current academic year if creating new enrollment
            if not self.instance.pk and college.current_academic_year:
                self.fields['academic_year'].initial = college.current_academic_year
            # Default to current semester if creating new enrollment
            if not self.instance.pk and college.current_semester:
                self.fields['semester'].initial = college.current_semester


class ResultForm(forms.ModelForm):
    """Form for entering results"""
    class Meta:
        model = Result
        fields = ['cat_marks', 'exam_marks']
        widgets = {
            'cat_marks': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0, 'max': 100}),
            'exam_marks': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0, 'max': 100}),
        }


class PasswordResetRequestForm(forms.Form):
    """Form for requesting password reset"""
    identifier = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your email or phone number',
            'autofocus': True
        }),
        label='Email or Phone Number',
        help_text='Enter the email or phone number used during registration'
    )
    
    def clean_identifier(self):
        identifier = self.cleaned_data.get('identifier', '').strip()
        if not identifier:
            raise forms.ValidationError('Please enter your email or phone number.')
        return identifier


class PasswordResetVerifyForm(forms.Form):
    """Form for verifying reset code"""
    code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter 6-digit code',
            'maxlength': '6',
            'pattern': '[0-9]{6}',
            'autofocus': True
        }),
        label='Verification Code',
        help_text='Enter the 6-digit code sent to your email or phone'
    )
    
    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip()
        if not code.isdigit():
            raise forms.ValidationError('Code must contain only numbers.')
        if len(code) != 6:
            raise forms.ValidationError('Code must be 6 digits.')
        return code


class PasswordResetForm(forms.Form):
    """Form for resetting password"""
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter new password',
            'autofocus': True
        }),
        label='New Password',
        min_length=8,
        help_text='Password must be at least 8 characters long'
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Confirm new password'
        }),
        label='Confirm Password'
    )
    
    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if new_password and confirm_password:
            if new_password != confirm_password:
                raise forms.ValidationError('Passwords do not match.')
        
        return cleaned_data

