from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password, check_password
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from django.utils import timezone
from django.core.exceptions import ValidationError
import json
import re


class College(models.Model):
    """College/Institution model"""
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    name = models.CharField(max_length=200)
    address = models.TextField()
    county = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    principal_name = models.CharField(max_length=100)
    registration_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    # Academic Settings
    semesters_per_year = models.IntegerField(default=2, validators=[MinValueValidator(1), MaxValueValidator(12)], help_text="Number of semesters per academic year (typically 2, 3, or 4)")
    current_academic_year = models.CharField(max_length=20, blank=True, null=True, help_text="Current academic year (e.g., 2024/2025)")
    current_semester = models.IntegerField(validators=[MinValueValidator(1)], null=True, blank=True, help_text="Current active semester")
    
    # Nominal Roll Sign-In Settings
    nominal_roll_signin_enabled = models.BooleanField(default=False, help_text="Enable/disable semester nominal roll sign-in for students")
    
    # Grading System Settings (stored as JSON for flexibility)
    grading_criteria = models.JSONField(default=dict, blank=True, help_text="Grading system configuration (weights, thresholds, etc.)")
    
    # Branch College Relationship
    parent_college = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='branch_colleges', help_text="Parent college if this is a branch")
    max_branches = models.IntegerField(default=5, validators=[MinValueValidator(0)], help_text="Maximum number of branches this college can create")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'colleges'
        ordering = ['name']
        indexes = [
            models.Index(fields=['registration_status']),  # For status filtering
            models.Index(fields=['email']),  # Already unique, but explicit index helps
        ]
    
    def __str__(self):
        return self.name
    
    def get_slug(self):
        """Generate URL-friendly slug from college name"""
        return slugify(self.name)
    
    def can_students_sign_in(self):
        """Check if students can sign in for nominal roll"""
        return self.nominal_roll_signin_enabled and self.current_academic_year and self.current_semester
    
    def get_max_semester(self):
        """Get maximum semester number based on semesters_per_year"""
        return self.semesters_per_year
    
    def get_semester_choices(self):
        """Get semester choices as list of tuples"""
        return [(i, f'Semester {i}') for i in range(1, self.semesters_per_year + 1)]
    
    def get_academic_year_choices(self, years_before=2, years_after=3):
        """
        Generate academic year choices based on current_academic_year
        Returns list of tuples: [(year_string, year_string), ...]
        """
        if not self.current_academic_year:
            # Fallback: calculate from current date
            current_year = timezone.now().year
            base_year = current_year
        else:
            # Parse current_academic_year (e.g., "2024/2025")
            try:
                base_year = int(self.current_academic_year.split('/')[0])
            except (ValueError, IndexError):
                # Invalid format, use current year
                current_year = timezone.now().year
                base_year = current_year
        
        choices = []
        for i in range(-years_before, years_after + 1):
            year = base_year + i
            year_str = f"{year}/{year + 1}"
            choices.append((year_str, year_str))
        return choices
    
    @staticmethod
    def validate_academic_year_format(value):
        """Validate academic year format (YYYY/YYYY)"""
        if not value:
            return
        pattern = r'^\d{4}/\d{4}$'
        if not re.match(pattern, value):
            raise ValidationError('Academic year must be in format YYYY/YYYY (e.g., 2024/2025)')
        
        # Validate that second year is one more than first
        try:
            year1, year2 = value.split('/')
            year1_int = int(year1)
            year2_int = int(year2)
            if year2_int != year1_int + 1:
                raise ValidationError('Academic year second part must be one year after the first (e.g., 2024/2025)')
        except ValueError:
            raise ValidationError('Academic year must be in format YYYY/YYYY (e.g., 2024/2025)')
    
    def get_grading_criteria(self):
        """Get grading criteria with defaults if not configured"""
        if not self.grading_criteria:
            # Default grading system
            return {
                'cat_weight': 30.0,
                'exam_weight': 70.0,
                'pass_mark': 50.0,
                'grades': {
                    'A': {'min': 70, 'max': 100},
                    'B': {'min': 60, 'max': 69},
                    'C': {'min': 50, 'max': 59},
                    'D': {'min': 40, 'max': 49},
                    'F': {'min': 0, 'max': 39}
                }
            }
        return self.grading_criteria
    
    def calculate_grade(self, total_score):
        """Calculate grade based on configured criteria"""
        criteria = self.get_grading_criteria()
        grades = criteria.get('grades', {})
        
        # Sort grades by min value descending to check from highest first
        sorted_grades = sorted(grades.items(), key=lambda x: x[1]['min'], reverse=True)
        
        for grade, range_data in sorted_grades:
            if range_data['min'] <= total_score <= range_data['max']:
                return grade
        return 'N/A'
    
    def calculate_total_marks(self, cat_marks=None, exam_marks=None):
        """Calculate total marks: CAT (out of max_cat) + Exam (out of max_exam) = Total (out of 100)
        Uses cat_weight and exam_weight from grading criteria as maximum marks.
        Formula: Total = CAT + Exam (direct addition)
        """
        total = 0.0
        if cat_marks is not None:
            total += cat_marks
        if exam_marks is not None:
            total += exam_marks
        
        return round(total, 2)
    
    def is_branch(self):
        """Check if this college is a branch of another college"""
        return self.parent_college is not None
    
    def is_main_college(self):
        """Check if this is a main college (has branches)"""
        return self.branch_colleges.exists()
    
    def get_all_branches(self):
        """Get all branch colleges including nested branches"""
        branches = list(self.branch_colleges.all())
        # Recursively get nested branches
        for branch in branches:
            branches.extend(branch.get_all_branches())
        return branches
    
    def can_create_branch(self):
        """Check if this college can create more branches"""
        if self.is_branch():
            return False  # Branches cannot create branches
        current_branches = self.branch_colleges.count()
        return current_branches < self.max_branches
    
    def get_remaining_branches(self):
        """Get the number of branches this college can still create"""
        if self.is_branch():
            return 0
        current_branches = self.branch_colleges.count()
        return max(0, self.max_branches - current_branches)


class CustomUser(AbstractUser):
    """Custom user model with college association and roles"""
    ROLE_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('director', 'Director/Owner'),
        ('principal', 'Principal'),
        ('registrar', 'Registrar'),
        ('accounts_officer', 'Accounts Officer'),
        ('reception', 'Reception'),
        ('lecturer', 'Lecturer'),
        # Legacy role - map to principal for backward compatibility
        ('college_admin', 'College Admin'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='lecturer')
    college = models.ForeignKey(College, on_delete=models.CASCADE, null=True, blank=True, related_name='staff')
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
        ordering = ['username']
        indexes = [
            models.Index(fields=['college', 'role']),  # For role-based queries
            models.Index(fields=['college', 'username']),  # For username searches
            models.Index(fields=['email']),  # For email lookups
        ]
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    def is_super_admin(self):
        """Check if user is super admin - either through role or Django superuser flag"""
        return self.role == 'super_admin' or self.is_superuser
    
    def is_director(self):
        return self.role == 'director'
    
    def is_principal(self):
        return self.role == 'principal'
    
    def is_registrar(self):
        return self.role == 'registrar'
    
    def is_accounts_officer(self):
        return self.role == 'accounts_officer'
    
    def is_reception(self):
        return self.role == 'reception'
    
    def is_lecturer(self):
        return self.role == 'lecturer'
    
    # Legacy method for backward compatibility
    def is_college_admin(self):
        return self.role == 'college_admin' or self.role == 'principal' or self.role == 'registrar'
    
    # Permission helper methods
    def can_view_all(self):
        """Director, Principal, Registrar, Accounts, and Reception can view everything"""
        return self.is_director() or self.is_principal() or self.is_registrar() or self.is_accounts_officer() or self.is_reception()
    
    def can_edit_academic(self):
        """Principal and Registrar can edit academic content"""
        return self.is_principal() or self.is_registrar()
    
    def can_manage_students(self):
        """Principal, Registrar, and Reception can manage students"""
        return self.is_principal() or self.is_registrar() or self.is_reception()
    
    def can_manage_courses(self):
        """Principal and Registrar can manage courses"""
        return self.is_principal() or self.is_registrar()
    
    def can_enter_all_marks(self):
        """Principal and Registrar can enter marks for all units"""
        return self.is_principal() or self.is_registrar()
    
    def can_manage_finance(self):
        """Accounts Officer can manage finance"""
        return self.is_accounts_officer()
    
    def can_manage_fee_structure(self):
        """Director and College Admin can create and edit fee structure"""
        return self.role == 'director' or self.role == 'college_admin'
    
    def can_record_payments(self):
        """Only Accounts Officer can record payments"""
        return self.is_accounts_officer()
    
    def can_manage_payment_settings(self):
        """Only Director can manage payment settings (MPESA, Bank integration)"""
        return self.role == 'director'
    
    def can_manage_lecturers(self):
        """Only Principal can manage lecturers"""
        return self.is_principal()
    
    def can_export_data(self):
        """Director, Principal, Registrar, and Accounts can export"""
        return self.is_director() or self.is_principal() or self.is_registrar() or self.is_accounts_officer()
    
    def is_read_only(self):
        """Director is read-only (except accounts section)"""
        return self.is_director()


class GlobalCourse(models.Model):
    """Global course templates"""
    LEVEL_CHOICES = [
        ('certificate', 'Certificate'),
        ('diploma', 'Diploma'),
        ('higher_diploma', 'Higher Diploma'),
    ]
    
    name = models.CharField(max_length=200)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    category = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'global_courses'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_level_display()})"


class GlobalUnit(models.Model):
    """Global unit templates"""
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'global_units'
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class GlobalCourseUnit(models.Model):
    """Mapping of global courses to global units (templates - semester is defined at college level)"""
    course = models.ForeignKey(GlobalCourse, on_delete=models.CASCADE, related_name='units')
    unit = models.ForeignKey(GlobalUnit, on_delete=models.CASCADE, related_name='courses')
    
    class Meta:
        db_table = 'global_course_units'
        unique_together = ['course', 'unit']
    
    def __str__(self):
        return f"{self.course.name} - {self.unit.code}"


class CollegeCourse(models.Model):
    """College-specific courses"""
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='courses')
    global_course = models.ForeignKey(GlobalCourse, on_delete=models.SET_NULL, null=True, blank=True, related_name='college_instances')
    code = models.CharField(max_length=50, help_text="Course code (e.g., CS101)")
    name = models.CharField(max_length=200)
    duration_years = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    admission_requirements = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'college_courses'
        ordering = ['name']
        indexes = [
            models.Index(fields=['college', 'name']),  # For search queries
            models.Index(fields=['college', 'code']),  # For code lookups
            models.Index(fields=['college', 'global_course']),  # For global course filtering
        ]
    
    def save(self, *args, **kwargs):
        # Ensure code is uppercase
        if self.code:
            self.code = self.code.upper()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.college.name} - {self.name}"
    
    def get_total_semesters(self, college=None):
        """Calculate total semesters for this course"""
        college = college or self.college
        if not college:
            return None
        return self.duration_years * college.semesters_per_year


class CollegeUnit(models.Model):
    """College-specific units"""
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='units')
    global_unit = models.ForeignKey(GlobalUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name='college_instances')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50)
    semester = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)], help_text="Semester (validated against college's semesters_per_year)")
    assigned_lecturer = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_units', limit_choices_to={'role': 'lecturer'})
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'college_units'
        ordering = ['code']
        unique_together = ['college', 'code']
        indexes = [
            models.Index(fields=['college', 'assigned_lecturer']),  # For lecturer unit queries
            models.Index(fields=['college', 'semester']),  # For semester filtering
            models.Index(fields=['college', 'code']),  # For code searches
        ]
    
    def __str__(self):
        return f"{self.college.name} - {self.code} ({self.name})"


class CollegeCourseUnit(models.Model):
    """Mapping of college courses to college units with year and semester"""
    course = models.ForeignKey(CollegeCourse, on_delete=models.CASCADE, related_name='course_units')
    unit = models.ForeignKey(CollegeUnit, on_delete=models.CASCADE, related_name='course_assignments')
    year_of_study = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], help_text="Year of study (1-5)")
    semester = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)], help_text="Semester (validated against college's semesters_per_year)")
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='course_unit_mappings')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'college_course_units'
        unique_together = ['course', 'unit', 'year_of_study', 'semester']
        ordering = ['course', 'year_of_study', 'semester', 'unit__code']
        indexes = [
            models.Index(fields=['college', 'course', 'year_of_study', 'semester']),  # Common filter
            models.Index(fields=['unit', 'college']),  # For unit-based lookups
            models.Index(fields=['course', 'semester']),  # For course-semester queries
        ]
    
    def __str__(self):
        return f"{self.course.name} - Year {self.year_of_study}, Sem {self.semester} - {self.unit.code}"
    
    def clean(self):
        """Validate that year_of_study doesn't exceed course duration"""
        from django.core.exceptions import ValidationError
        if self.course and self.year_of_study > self.course.duration_years:
            raise ValidationError(f'Year of study ({self.year_of_study}) cannot exceed course duration ({self.course.duration_years} years)')


class Student(models.Model):
    """Student model"""
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('graduated', 'Graduated'),
        ('deferred', 'Deferred'),
    ]
    
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='students')
    admission_number = models.CharField(max_length=50)
    full_name = models.CharField(max_length=200)
    course = models.ForeignKey(CollegeCourse, on_delete=models.SET_NULL, null=True, related_name='students')
    year_of_study = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    date_of_birth = models.DateField()
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    password = models.CharField(max_length=128, blank=True, help_text="Hashed password for student login")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', help_text="Student status")
    graduation_date = models.DateField(null=True, blank=True, help_text="Date of graduation (if graduated)")
    # Semester Sign-In Tracking
    current_semester = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)], null=True, blank=True, help_text="Current semester (validated against college's semesters_per_year)")
    last_signin_date = models.DateTimeField(null=True, blank=True, help_text="Last semester sign-in timestamp")
    last_signin_academic_year = models.CharField(max_length=20, blank=True, null=True, help_text="Last sign-in academic year")
    
    # School Sponsorship Fields
    is_sponsored = models.BooleanField(default=False, help_text="Whether student is school-sponsored")
    sponsorship_discount_type = models.CharField(
        max_length=20,
        choices=[('percentage', 'Percentage'), ('fixed_amount', 'Fixed Amount')],
        null=True, blank=True,
        help_text="Discount type for this student"
    )
    sponsorship_discount_value = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text="Discount value (percentage 0-100 or fixed amount in KES)"
    )
    sponsorship_approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='sponsorship_approvals', help_text="User who approved sponsorship")
    sponsorship_approved_at = models.DateTimeField(null=True, blank=True, help_text="When sponsorship was approved")
    
    # Ream Paper Field
    has_ream_paper = models.BooleanField(default=False, help_text="Whether student has submitted ream paper")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'students'
        unique_together = ['college', 'admission_number']
        ordering = ['admission_number']
        indexes = [
            models.Index(fields=['college', 'status']),  # For filtering by status
            models.Index(fields=['college', 'course', 'status']),  # Composite for common queries
            models.Index(fields=['college', 'full_name']),  # For name searches
            models.Index(fields=['college', 'year_of_study']),  # For year filtering
            models.Index(fields=['college', 'admission_number']),  # For admission number searches
        ]
    
    def __str__(self):
        return f"{self.admission_number} - {self.full_name}"
    
    def save(self, *args, **kwargs):
        """Override save to automatically generate invoice for new students or when course is added"""
        is_new = self.pk is None
        
        # Track if course was just added (for existing students)
        course_was_added = False
        if not is_new:
            try:
                old_student = Student.objects.get(pk=self.pk)
                # Check if course was None before and is now set
                if not old_student.course and self.course:
                    course_was_added = True
            except Student.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # Generate invoice for new students with course (Semester 1)
        if is_new and self.course:
            try:
                from accounts.models import generate_student_invoice
                # Generate invoice for semester 1
                invoice = generate_student_invoice(
                    student=self,
                    semester_number=1,
                    academic_year=self.college.current_academic_year
                )
                if not invoice:
                    # Log warning if invoice generation returned None
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Invoice generation returned None for new student {self.admission_number} - Semester 1. Check if fee structure exists.")
            except Exception as e:
                # Log error but don't fail student creation
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to generate invoice for new student {self.admission_number}: {str(e)}", exc_info=True)
        
        # Generate invoice when course is added to existing student
        elif course_was_added and self.course:
            try:
                from accounts.models import generate_student_invoice
                # Generate invoice for semester 1 (first semester of the course)
                invoice = generate_student_invoice(
                    student=self,
                    semester_number=1,
                    academic_year=self.college.current_academic_year
                )
                if not invoice:
                    # Log warning if invoice generation returned None
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Invoice generation returned None when course was added to student {self.admission_number} - Semester 1. Check if fee structure exists.")
            except Exception as e:
                # Log error but don't fail student update
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to generate invoice when course was added to student {self.admission_number}: {str(e)}", exc_info=True)
    
    def set_password(self, raw_password):
        """Set password for student"""
        self.password = make_password(raw_password)
        self.save(update_fields=['password'])
    
    def check_password(self, raw_password):
        """Check if provided password matches student's password"""
        if not self.password:
            return False
        return check_password(raw_password, self.password)
    
    def has_usable_password(self):
        """Check if student has a password set"""
        return bool(self.password)
    
    def is_active(self):
        """Check if student is active"""
        return self.status == 'active'
    
    def is_suspended(self):
        """Check if student is suspended"""
        return self.status == 'suspended'
    
    def is_graduated(self):
        """Check if student is graduated"""
        return self.status == 'graduated'
    
    def is_deferred(self):
        """Check if student is deferred"""
        return self.status == 'deferred'
    
    def can_access_portal(self):
        """Check if student can access the portal"""
        return self.status == 'active'
    
    def get_current_semester(self):
        """Get current semester from most recent enrollment for current academic year"""
        from django.utils import timezone
        current_year = timezone.now().year
        # Try to match current academic year format (e.g., "2024/2025")
        current_academic_year = f"{current_year}/{current_year + 1}"
        
        # Get most recent enrollment for current academic year
        enrollment = self.enrollments.filter(academic_year=current_academic_year).order_by('-semester').first()
        if enrollment:
            return enrollment.semester
        
        # Fallback: get most recent enrollment overall
        enrollment = self.enrollments.order_by('-academic_year', '-semester').first()
        if enrollment:
            return enrollment.semester
        
        # Default to semester 1 if no enrollments
        return 1
    
    def has_signed_in_for_semester(self, academic_year, semester):
        """Check if student has already signed in for a specific semester"""
        return self.semester_signins.filter(academic_year=academic_year, semester=semester).exists()
    
    def sign_in_to_semester(self, academic_year, semester):
        """
        Process semester sign-in: update student's year and semester
        Returns tuple: (success: bool, message: str, signin_record: StudentSemesterSignIn or None)
        """
        from django.core.exceptions import ValidationError
        
        # Check if already signed in
        if self.has_signed_in_for_semester(academic_year, semester):
            return False, "You have already signed in for this semester.", None
        
        # Check if feature is enabled
        if not self.college.can_students_sign_in():
            return False, "Semester sign-in is currently disabled.", None
        
        # Check if student is active
        if not self.is_active():
            return False, "Your account is not active. Please contact administration.", None
        
        # Determine next semester and year
        current_year = self.year_of_study
        current_sem = self.current_semester or self.get_current_semester()
        
        # Calculate next semester/year
        # Get max semesters from college settings
        max_semesters = self.college.get_max_semester()
        
        if current_sem < max_semesters:
            next_semester = current_sem + 1
            next_year = current_year
        else:
            next_semester = 1
            next_year = current_year + 1
        
        # Check if next year exceeds course duration
        if self.course and next_year > self.course.duration_years:
            return False, f"Cannot advance to year {next_year}. Course duration is {self.course.duration_years} years.", None
        
        # Create sign-in record
        signin_record = StudentSemesterSignIn.objects.create(
            student=self,
            academic_year=academic_year,
            semester=semester,
            year_of_study_at_signin=current_year,
            semester_of_study_at_signin=current_sem,
            next_year_of_study=next_year,
            next_semester=next_semester
        )
        
        # Update student's year and semester
        self.year_of_study = next_year
        self.current_semester = next_semester
        self.last_signin_date = timezone.now()
        self.last_signin_academic_year = academic_year
        self.save(update_fields=['year_of_study', 'current_semester', 'last_signin_date', 'last_signin_academic_year'])
        
        # Mark sign-in as processed
        signin_record.is_processed = True
        signin_record.processed_at = timezone.now()
        signin_record.save(update_fields=['is_processed', 'processed_at'])
        
        # Generate invoice for the new semester
        if self.course:
            try:
                from accounts.models import generate_student_invoice
                # Calculate course semester number for the new semester
                semesters_per_year = self.college.semesters_per_year
                course_semester_number = (next_year - 1) * semesters_per_year + next_semester
                
                # Generate invoice for the new semester
                generate_student_invoice(
                    student=self,
                    semester_number=course_semester_number,
                    academic_year=academic_year
                )
            except Exception as e:
                # Log error but don't fail sign-in
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to generate invoice for student {self.admission_number} semester {course_semester_number}: {str(e)}")
        
        return True, f"Successfully signed in! You are now in Year {next_year}, Semester {next_semester}.", signin_record
    
    def get_course_semester_number(self):
        """Calculate current semester number in course (1 to total semesters)"""
        if not self.course or not self.college:
            return None
        
        # Get current semester (use current_semester or default to 1)
        current_sem = self.current_semester or 1
        
        # Calculate semester number: (year_of_study - 1) × semesters_per_year + current_semester
        semesters_per_year = self.college.semesters_per_year
        semester_number = (self.year_of_study - 1) * semesters_per_year + current_sem
        
        # Validate it doesn't exceed total semesters
        total_semesters = self.get_total_course_semesters()
        if total_semesters and semester_number > total_semesters:
            return None  # Invalid semester
        
        return semester_number
    
    def get_total_course_semesters(self):
        """Get total semesters for student's course"""
        if not self.course or not self.college:
            return None
        return self.course.duration_years * self.college.semesters_per_year
    
    def _get_fee_structure_for_semester_on_date(self, semester_number, reference_date=None):
        """Get fee structures for a specific semester
        Now uses CourseFeeStructure (semester-specific)"""
        from accounts.models import CourseFeeStructure
        
        # Get course fee structures for this specific semester
        fee_structures = CourseFeeStructure.objects.filter(
            course=self.course,
            semester_number=semester_number
        )
        
        return fee_structures
    
    def _get_reference_date_for_semester(self, semester_number):
        """Get reference date for when student should have been charged for a semester
        Uses student's sign-in history or calculates based on when they should have been in that semester"""
        from django.utils import timezone
        from datetime import timedelta
        
        if not self.course or not self.college:
            return timezone.now().date()
        
        current_semester = self.get_course_semester_number()
        
        # For students in their current semester, use current date
        # This ensures newly created fees are found
        if current_semester and semester_number == current_semester:
            return timezone.now().date()
        
        # For past semesters, we need to find when the student was actually in that semester
        # Try to use student's semester sign-in history first
        if hasattr(self, 'semester_signins'):
            # Find the sign-in record for when student entered this semester
            # The sign-in record shows when they signed in for the semester AFTER this one
            # So we need to find when they signed in for semester_number + 1, or
            # find the last sign-in before reaching this semester
            semesters_per_year = self.college.semesters_per_year
            
            # Calculate which term semester this corresponds to
            term_semester = ((semester_number - 1) % semesters_per_year) + 1
            
            # Find sign-in records and work backwards
            signins = self.semester_signins.all().order_by('signed_in_at')
            
            # Find the sign-in where student reached this semester
            # When student signs in, they move to the NEXT semester
            # So if we find a sign-in where next_semester_of_study_at_signin == semester_number,
            # that's when they entered this semester
            for signin in signins:
                # Calculate the course semester number at sign-in
                signin_course_sem = (signin.year_of_study_at_signin - 1) * semesters_per_year + signin.semester_of_study_at_signin
                if signin_course_sem == semester_number:
                    # This is when they were in this semester
                    return signin.signed_in_at.date()
                elif signin_course_sem > semester_number:
                    # We've passed this semester, use the previous sign-in date
                    # Or estimate based on when they should have been in this semester
                    break
        
        # If no sign-in history, estimate based on semester progression
        
        # Last resort: use a date in the past to ensure we get fees that were active
        # when the student should have been charged, not current updated fees
        # Use a date that's approximately when they should have been in this semester
        if current_semester and semester_number < current_semester:
            # Estimate: assume each semester is about 4-6 months
            semesters_ago = current_semester - semester_number
            estimated_date = timezone.now().date() - timedelta(days=120 * semesters_ago)
            return estimated_date
        
        # Final fallback: use a date far enough in the past to avoid recent updates
        # This ensures we get the fee version that was active when student was in that semester
        return timezone.now().date() - timedelta(days=180)
    
    def get_total_expected_fees(self):
        """Calculate total expected fees up to current semester
        Uses invoices if available, otherwise falls back to fee structure calculation"""
        from accounts.models import StudentInvoice
        from django.db.models import Sum
        from decimal import Decimal
        
        if not self.course:
            return Decimal('0.00')
        
        semester_number = self.get_course_semester_number()
        if not semester_number:
            return Decimal('0.00')
        
        # Try to use invoices first (preferred method)
        invoices = StudentInvoice.objects.filter(
            student=self,
            semester_number__lte=semester_number
        )
        
        if invoices.exists():
            # Sum up all invoice amounts
            total = invoices.aggregate(total=Sum('fee_amount'))['total'] or Decimal('0.00')
            return total
        
        # Fallback to course fee structures if no invoices exist (semester-specific)
        from accounts.models import CourseFeeStructure
        
        # Calculate total from course fee structures for each semester
        total = Decimal('0.00')
        for sem_num in range(1, semester_number + 1):
            course_fee_structures = CourseFeeStructure.objects.filter(
                course=self.course,
                semester_number=sem_num
            )
            sem_total = course_fee_structures.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            total += sem_total
        
        # Apply sponsorship discount if applicable
        if hasattr(self, 'is_sponsored') and self.is_sponsored:
            if hasattr(self, 'sponsorship_discount_type') and hasattr(self, 'sponsorship_discount_value'):
                if self.sponsorship_discount_type and self.sponsorship_discount_value:
                    if self.sponsorship_discount_type == 'percentage':
                        discount = total * (self.sponsorship_discount_value / Decimal('100.00'))
                    else:  # fixed_amount
                        discount = self.sponsorship_discount_value
                    total = max(Decimal('0.00'), total - discount)
        
        return total
    
    def get_total_payments(self):
        """Calculate total payments made by student"""
        from accounts.models import Payment
        from django.db.models import Sum
        from decimal import Decimal
        
        return Payment.objects.filter(student=self).aggregate(
            total=Sum('amount_paid')
        )['total'] or Decimal('0.00')
    
    def get_balance(self):
        """Calculate outstanding balance"""
        return self.get_total_expected_fees() - self.get_total_payments()
    
    def get_fee_breakdown(self):
        """Get fee breakdown by semester
        Uses invoices if available, otherwise falls back to course fee structure calculation"""
        from accounts.models import StudentInvoice, CourseFeeStructure
        from django.db.models import Sum
        from decimal import Decimal
        
        if not self.course:
            return {}
        
        semester_number = self.get_course_semester_number()
        if not semester_number:
            return {}
        
        breakdown = {}
        
        # Try to use invoices first (preferred method)
        invoices = StudentInvoice.objects.filter(
            student=self,
            semester_number__lte=semester_number
        ).order_by('semester_number')
        
        if invoices.exists():
            # Use invoice data
            for invoice in invoices:
                breakdown[invoice.semester_number] = {
                    'amount': invoice.fee_amount,
                    'invoice_number': invoice.invoice_number,
                    'invoice_id': invoice.id,
                    'status': invoice.status,
                    'fee_structures': []  # Invoice already has the total, no breakdown needed
                }
            
            # Fill in missing semesters with zero
            for sem_num in range(1, semester_number + 1):
                if sem_num not in breakdown:
                    breakdown[sem_num] = {
                        'amount': Decimal('0.00'),
                        'fee_structures': []
                    }
        else:
            # Use course fee structures (semester-specific)
            for sem_num in range(1, semester_number + 1):
                # Get fee structures for this specific semester
                course_fee_structures = CourseFeeStructure.objects.filter(
                    course=self.course,
                    semester_number=sem_num
                )
                
                # Calculate total from course fee structures for this semester
                sem_total = course_fee_structures.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                
                # Apply sponsorship if applicable
                if hasattr(self, 'is_sponsored') and self.is_sponsored:
                    if hasattr(self, 'sponsorship_discount_type') and hasattr(self, 'sponsorship_discount_value'):
                        if self.sponsorship_discount_type and self.sponsorship_discount_value:
                            if self.sponsorship_discount_type == 'percentage':
                                discount = sem_total * (self.sponsorship_discount_value / Decimal('100.00'))
                            else:  # fixed_amount
                                discount = self.sponsorship_discount_value
                            sem_total = max(Decimal('0.00'), sem_total - discount)
                
                # Get fee structure details for breakdown
                fee_structure_details = []
                for cfs in course_fee_structures:
                    fee_structure_details.append({
                        'fee_type': cfs.fee_item.name,
                        'amount': cfs.amount
                    })
                
                breakdown[sem_num] = {
                    'amount': sem_total,
                    'fee_structures': fee_structure_details
                }
        
        return breakdown
    
    def has_invoice_for_semester(self, semester_number, term=None):
        """Check if invoice exists for this semester number"""
        from accounts.models import StudentInvoice
        
        invoices = StudentInvoice.objects.filter(
            student=self,
            semester_number=semester_number
        )
        
        if term:
            invoices = invoices.filter(term=term)
        
        return invoices.first()  # Return invoice if exists, None otherwise


class Enrollment(models.Model):
    """Student enrollment in units"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    unit = models.ForeignKey(CollegeUnit, on_delete=models.CASCADE, related_name='enrollments')
    academic_year = models.CharField(
        max_length=20,
        help_text="Academic year in format YYYY/YYYY (e.g., 2024/2025)"
    )
    semester = models.IntegerField()
    enrolled_at = models.DateTimeField(auto_now_add=True)
    exam_registered = models.BooleanField(default=False, help_text="Whether student has registered for examination")
    exam_registered_at = models.DateTimeField(null=True, blank=True, help_text="Date and time when student registered for examination")
    
    class Meta:
        db_table = 'enrollments'
        unique_together = ['student', 'unit', 'academic_year', 'semester']
        ordering = ['-academic_year', 'semester']
        indexes = [
            models.Index(fields=['student', 'academic_year', 'semester']),  # Common filter combo
            models.Index(fields=['unit', 'academic_year']),  # For unit-based queries
            models.Index(fields=['academic_year', 'semester']),  # For academic year/semester filtering
            models.Index(fields=['exam_registered']),  # For exam status filtering
            models.Index(fields=['student', 'exam_registered']),  # For student exam status
        ]
    
    def clean(self):
        """Validate academic year format"""
        if self.academic_year:
            College.validate_academic_year_format(self.academic_year)
    
    def save(self, *args, **kwargs):
        """Override save to validate academic year"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.student.admission_number} - {self.unit.code} ({self.academic_year})"


class Result(models.Model):
    """Student results/marks"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
    ]
    
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='result')
    cat_marks = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)], null=True, blank=True)
    exam_marks = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)], null=True, blank=True)
    total = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)], null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', help_text="Result status: draft or submitted")
    submitted_at = models.DateTimeField(null=True, blank=True, help_text="Date and time when result was submitted")
    entered_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='entered_results')
    entered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'results'
        ordering = ['-entered_at']
        indexes = [
            models.Index(fields=['entered_by', 'status']),  # For user result queries
            models.Index(fields=['status']),  # For status filtering
            models.Index(fields=['entered_at']),  # For date-based queries
        ]
    
    def __str__(self):
        return f"{self.enrollment.student.admission_number} - {self.enrollment.unit.code} - {self.total or 'N/A'}"
    
    def is_submitted(self):
        """Check if result is submitted"""
        return self.status == 'submitted'
    
    def can_edit(self, user):
        """Check if user can edit this result"""
        # Registrar and Principal can edit both draft and submitted results
        if user.is_registrar() or user.is_principal():
            return True
        
        # Lecturers can only edit draft results for their assigned units
        if user.is_lecturer():
            return self.status == 'draft' and self.enrollment.unit.assigned_lecturer == user
        
        # Other roles cannot edit results
        return False
    
    def save(self, *args, **kwargs):
        # Auto-calculate total using college's grading system
        college = self.enrollment.unit.college
        self.total = college.calculate_total_marks(
            cat_marks=float(self.cat_marks) if self.cat_marks is not None else None,
            exam_marks=float(self.exam_marks) if self.exam_marks is not None else None
        )
        
        # Maintain status='draft' unless explicitly set
        if not self.status:
            self.status = 'draft'
        
        super().save(*args, **kwargs)


def timetable_upload_path(instance, filename):
    """Generate upload path for timetable images"""
    if instance.course:
        return f'timetables/{instance.college.id}/{instance.course.id}/{filename}'
    else:
        return f'timetables/{instance.college.id}/general/{filename}'


class CollegeTimetable(models.Model):
    """College timetable files - can be general or course-specific. Supports images and PDFs."""
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='timetables')
    course = models.ForeignKey(CollegeCourse, on_delete=models.CASCADE, null=True, blank=True, related_name='timetables', help_text="Leave empty for general timetable applicable to all courses")
    image = models.ImageField(upload_to=timetable_upload_path, null=True, blank=True, help_text="Upload timetable image (JPG, PNG, GIF, WebP)")
    file = models.FileField(upload_to=timetable_upload_path, null=True, blank=True, help_text="Upload timetable file (PDF, JPG, PNG, GIF, WebP)")
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='uploaded_timetables')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, help_text="Inactive timetables are hidden from students")
    academic_year = models.CharField(max_length=20, blank=True, null=True, help_text="e.g., 2024/2025")
    semester = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)], null=True, blank=True, help_text="Semester (validated against college's semesters_per_year)")
    description = models.TextField(blank=True, help_text="Optional description or notes")
    
    def clean(self):
        """Ensure at least one file is uploaded"""
        from django.core.exceptions import ValidationError
        if not self.image and not self.file:
            raise ValidationError("Either an image or file must be uploaded.")
        if self.image and self.file:
            raise ValidationError("Please upload either an image or a file, not both.")
    
    def get_file_url(self):
        """Get the URL of the uploaded file (image or PDF)"""
        if self.file:
            return self.file.url
        elif self.image:
            return self.image.url
        return None
    
    def is_pdf(self):
        """Check if the uploaded file is a PDF"""
        if self.file:
            return self.file.name.lower().endswith('.pdf')
        return False
    
    def get_file_type(self):
        """Get the file type (image or pdf)"""
        if self.is_pdf():
            return 'pdf'
        return 'image'
    
    class Meta:
        db_table = 'college_timetables'
        ordering = ['-uploaded_at']
        unique_together = [['college', 'course', 'academic_year', 'semester']]
        indexes = [
            models.Index(fields=['college', 'is_active']),
            models.Index(fields=['college', 'course']),
            models.Index(fields=['academic_year', 'semester']),
        ]
    
    def __str__(self):
        if self.course:
            return f"{self.college.name} - {self.course.name} Timetable"
        else:
            return f"{self.college.name} - General Timetable"
    
    def get_timetable_type(self):
        """Return 'general' or 'course_specific'"""
        return 'general' if self.course is None else 'course_specific'


class SchoolRegistration(models.Model):
    """School registration form data"""
    SCHOOL_TYPE_CHOICES = [
        ('primary', 'Primary'),
        ('secondary', 'Secondary'),
        ('college', 'College'),
        ('university', 'University'),
    ]
    
    POSITION_CHOICES = [
        ('director', 'Director'),
        ('owner', 'Owner'),
        ('principal', 'Principal'),
        ('administrator', 'Administrator'),
    ]
    
    # School Details
    school_name = models.CharField(max_length=200)
    school_type = models.CharField(max_length=20, choices=SCHOOL_TYPE_CHOICES)
    school_address = models.TextField()
    county_city = models.CharField(max_length=100)
    school_contact_number = models.CharField(max_length=20)
    school_email = models.EmailField()
    
    # School Owner/Principal Details
    owner_full_name = models.CharField(max_length=200)
    owner_email = models.EmailField()
    owner_phone = models.CharField(max_length=20)
    position = models.CharField(max_length=20, choices=POSITION_CHOICES)
    
    # Additional Information
    number_of_students = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    number_of_teachers = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    school_website = models.URLField(blank=True, null=True)
    school_logo = models.ImageField(upload_to='school_logos/', blank=True, null=True)
    
    # Status
    status = models.CharField(max_length=20, choices=College.STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'school_registrations'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.school_name} - {self.get_status_display()}"


# TranscriptTemplate model has been removed - reports now use ReportTemplate with mappings


class Announcement(models.Model):
    """Announcement model for college announcements with targeting capabilities"""
    TARGET_TYPE_CHOICES = [
        ('all_students', 'All Students'),
        ('all_lecturers', 'All Lecturers'),
        ('individual', 'Individual Users'),
    ]
    
    PRIORITY_CHOICES = [
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='announcements')
    title = models.CharField(max_length=200)
    content = models.TextField()
    target_type = models.CharField(max_length=20, choices=TARGET_TYPE_CHOICES)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='created_announcements')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Many-to-Many relationships for individual targeting
    targeted_students = models.ManyToManyField(Student, blank=True, related_name='announcements')
    targeted_users = models.ManyToManyField(CustomUser, blank=True, related_name='targeted_announcements')
    
    class Meta:
        db_table = 'announcements'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['college', 'target_type']),
            models.Index(fields=['college', 'is_active']),
            models.Index(fields=['college', 'created_at']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.college.name}"
    
    def is_expired(self):
        """Check if announcement has expired"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def is_visible_to_student(self, student):
        """Check if announcement should be visible to a student"""
        # Must be active and not expired
        if not self.is_active or self.is_expired():
            return False
        
        # Must belong to same college
        if self.college != student.college:
            return False
        
        # Check targeting
        if self.target_type == 'all_students':
            return True
        elif self.target_type == 'individual':
            return self.targeted_students.filter(pk=student.pk).exists()
        
        return False
    
    def is_visible_to_user(self, user):
        """Check if announcement should be visible to a user (lecturer/admin)"""
        # Must be active and not expired
        if not self.is_active or self.is_expired():
            return False
        
        # Must belong to same college
        if not hasattr(user, 'college') or not user.college or self.college != user.college:
            return False
        
        # Check targeting
        if self.target_type == 'all_lecturers':
            # Show to all lecturers (and college admins)
            return user.is_lecturer() or user.is_college_admin()
        elif self.target_type == 'individual':
            return self.targeted_users.filter(pk=user.pk).exists()
        
        return False


class StudentSemesterSignIn(models.Model):
    """Track student semester sign-ins for nominal roll"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='semester_signins')
    academic_year = models.CharField(max_length=20, help_text="Academic year (e.g., 2024/2025)")
    semester = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)], help_text="Semester (validated against college's semesters_per_year)")
    signed_in_at = models.DateTimeField(auto_now_add=True, help_text="Date and time when student signed in")
    year_of_study_at_signin = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], help_text="Year of study when signed in")
    semester_of_study_at_signin = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)], help_text="Semester when signed in (validated against college's semesters_per_year)")
    next_year_of_study = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], help_text="Year of study after sign-in")
    next_semester = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)], help_text="Semester after sign-in (validated against college's semesters_per_year)")
    is_processed = models.BooleanField(default=False, help_text="Whether student's year/semester was updated")
    processed_at = models.DateTimeField(null=True, blank=True, help_text="Date and time when sign-in was processed")
    
    class Meta:
        db_table = 'student_semester_signins'
        unique_together = ['student', 'academic_year', 'semester']
        ordering = ['-signed_in_at']
        indexes = [
            models.Index(fields=['student', 'academic_year', 'semester']),
            models.Index(fields=['academic_year', 'semester']),
            models.Index(fields=['signed_in_at']),
        ]
    
    def __str__(self):
        return f"{self.student.admission_number} - {self.academic_year} Sem {self.semester}"


class PasswordResetCode(models.Model):
    """Model to store password reset codes"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='password_reset_codes')
    code = models.CharField(max_length=6)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    class Meta:
        db_table = 'password_reset_codes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'code']),
            models.Index(fields=['code', 'is_verified']),
        ]
    
    def __str__(self):
        return f"Reset code for {self.user.username} - {self.code}"
    
    def is_expired(self):
        """Check if the reset code has expired"""
        from django.utils import timezone
        return timezone.now() > self.expires_at


class ReportTemplate(models.Model):
    """Model to store report templates with editable elements, positions, fonts, and alignment"""
    REPORT_TYPE_CHOICES = [
        ('transcript', 'Transcript'),
        ('certificate', 'Certificate'),
        ('result_slip', 'Result Slip'),
        ('custom', 'Custom Report'),
    ]
    
    PAGE_SIZE_CHOICES = [
        ('A4', 'A4 (794 × 1123 px)'),
        ('A3', 'A3 (1123 × 1587 px)'),
        ('A5', 'A5 (559 × 794 px)'),
        ('Letter', 'Letter (816 × 1056 px)'),
    ]
    
    # Page size dimensions in pixels (width × height at 96 DPI)
    PAGE_DIMENSIONS = {
        'A4': (794, 1123),
        'A3': (1123, 1587),
        'A5': (559, 794),
        'Letter': (816, 1056),
    }
    
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='report_templates')
    name = models.CharField(max_length=200, help_text="Template name")
    report_type = models.CharField(max_length=50, choices=REPORT_TYPE_CHOICES, default='custom')
    description = models.TextField(blank=True, help_text="Template description")
    
    # Page size and canvas settings
    page_size = models.CharField(max_length=20, choices=PAGE_SIZE_CHOICES, default='A4', help_text="Page size for the template")
    canvas_width = models.IntegerField(default=794, help_text="Canvas width in pixels")
    canvas_height = models.IntegerField(default=1123, help_text="Canvas height in pixels")
    
    # Elements stored as JSON: list of elements with type, content, position, style, etc.
    elements = models.JSONField(default=list, help_text="Array of report elements (text boxes, images, etc.)")
    
    # Metadata
    is_active = models.BooleanField(default=True, help_text="Whether this template is currently active")
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='created_report_templates')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'report_templates'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['college', 'is_active']),
            models.Index(fields=['college', 'report_type']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.college.name}"
    
    def get_page_dimensions(self):
        """Get width and height for the selected page size"""
        return self.PAGE_DIMENSIONS.get(self.page_size, self.PAGE_DIMENSIONS['A4'])
    
    def update_canvas_to_page_size(self):
        """Update canvas dimensions to match the selected page size"""
        width, height = self.get_page_dimensions()
        self.canvas_width = width
        self.canvas_height = height
        self.save(update_fields=['canvas_width', 'canvas_height'])


class ReportTemplateMapping(models.Model):
    """Model to store which template is used for each report type per college"""
    REPORT_TYPE_CHOICES = [
        ('transcript', 'Transcript'),
        ('fee_structure', 'Fee Structure'),
        ('exam_card', 'Exam Card'),
    ]
    
    college = models.OneToOneField(College, on_delete=models.CASCADE, related_name='report_template_mapping')
    transcript_template = models.ForeignKey(
        ReportTemplate, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='transcript_mappings',
        help_text="Template to use for Transcript reports"
    )
    fee_structure_template = models.ForeignKey(
        ReportTemplate, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='fee_structure_mappings',
        help_text="Template to use for Fee Structure reports"
    )
    exam_card_template = models.ForeignKey(
        ReportTemplate, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='exam_card_mappings',
        help_text="Template to use for Exam Card reports"
    )
    updated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='updated_report_mappings')
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'report_template_mappings'
        verbose_name = 'Report Template Mapping'
        verbose_name_plural = 'Report Template Mappings'
    
    def __str__(self):
        return f"Report Template Mapping - {self.college.name}"
    
    def get_template_for_report_type(self, report_type):
        """Get the template for a specific report type"""
        if report_type == 'transcript':
            return self.transcript_template
        elif report_type == 'fee_structure':
            return self.fee_structure_template
        elif report_type == 'exam_card':
            return self.exam_card_template
        return None