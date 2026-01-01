from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import (
    College, CustomUser, GlobalCourse, GlobalUnit, GlobalCourseUnit,
    CollegeCourse, CollegeUnit, CollegeCourseUnit, Student, Enrollment, Result,
    SchoolRegistration, Announcement, StudentSemesterSignIn
)


@admin.register(College)
class CollegeAdmin(admin.ModelAdmin):
    list_display = ['name', 'county', 'email', 'phone', 'principal_name', 'registration_status', 'created_at']
    list_filter = ['registration_status', 'county', 'created_at']
    search_fields = ['name', 'email', 'county', 'principal_name']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'address', 'county', 'email', 'phone', 'principal_name')
        }),
        ('Status', {
            'fields': ('registration_status',)
        }),
        ('Nominal Roll Sign-In Settings', {
            'fields': ('nominal_roll_signin_enabled', 'current_academic_year', 'current_semester')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'role', 'college', 'phone', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active', 'is_staff', 'college']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Additional Information', {
            'fields': ('role', 'college', 'phone')
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Additional Information', {
            'fields': ('role', 'college', 'phone', 'email', 'first_name', 'last_name')
        }),
    )


@admin.register(GlobalCourse)
class GlobalCourseAdmin(admin.ModelAdmin):
    list_display = ['name', 'level', 'category', 'created_at']
    list_filter = ['level', 'category']
    search_fields = ['name', 'category']


@admin.register(GlobalUnit)
class GlobalUnitAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'created_at']
    search_fields = ['code', 'name']


@admin.register(GlobalCourseUnit)
class GlobalCourseUnitAdmin(admin.ModelAdmin):
    list_display = ['course', 'unit']
    list_filter = ['course']
    search_fields = ['course__name', 'unit__code', 'unit__name']


@admin.register(CollegeCourse)
class CollegeCourseAdmin(admin.ModelAdmin):
    list_display = ['name', 'college', 'global_course', 'duration_years', 'created_at']
    list_filter = ['college', 'duration_years', 'created_at']
    search_fields = ['name', 'college__name']
    raw_id_fields = ['college', 'global_course']


@admin.register(CollegeUnit)
class CollegeUnitAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'college', 'semester', 'assigned_lecturer', 'created_at']
    list_filter = ['college', 'semester', 'created_at']
    search_fields = ['code', 'name', 'college__name']
    raw_id_fields = ['college', 'global_unit', 'assigned_lecturer']


@admin.register(CollegeCourseUnit)
class CollegeCourseUnitAdmin(admin.ModelAdmin):
    list_display = ['course', 'unit', 'semester', 'college']
    list_filter = ['semester', 'college']
    search_fields = ['course__name', 'unit__code', 'college__name']
    raw_id_fields = ['course', 'unit', 'college']


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['admission_number', 'full_name', 'college', 'course', 'year_of_study', 'gender', 'created_at']
    list_filter = ['college', 'gender', 'year_of_study', 'created_at']
    search_fields = ['admission_number', 'full_name', 'email', 'college__name']
    raw_id_fields = ['college', 'course']


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'unit', 'academic_year', 'semester', 'enrolled_at']
    list_filter = ['academic_year', 'semester', 'enrolled_at']
    search_fields = ['student__admission_number', 'student__full_name', 'unit__code']
    raw_id_fields = ['student', 'unit']


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ['enrollment', 'cat_marks', 'exam_marks', 'total', 'entered_by', 'entered_at']
    list_filter = ['entered_at', 'entered_by']
    search_fields = ['enrollment__student__admission_number', 'enrollment__unit__code']
    raw_id_fields = ['enrollment', 'entered_by']
    readonly_fields = ['entered_at', 'updated_at']


@admin.register(SchoolRegistration)
class SchoolRegistrationAdmin(admin.ModelAdmin):
    list_display = ['school_name', 'school_type', 'county_city', 'school_email', 'owner_full_name', 'status', 'created_at']
    list_filter = ['school_type', 'status', 'position', 'created_at']
    search_fields = ['school_name', 'school_email', 'owner_full_name', 'owner_email', 'county_city']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('School Details', {
            'fields': ('school_name', 'school_type', 'school_address', 'county_city', 
                      'school_contact_number', 'school_email', 'school_website', 'school_logo')
        }),
        ('Owner/Principal Details', {
            'fields': ('owner_full_name', 'owner_email', 'owner_phone', 'position')
        }),
        ('Additional Information', {
            'fields': ('number_of_students', 'number_of_teachers')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ['title', 'college', 'target_type', 'priority', 'is_active', 'created_by', 'created_at', 'expires_at']
    list_filter = ['college', 'target_type', 'priority', 'is_active', 'created_at']
    search_fields = ['title', 'content', 'college__name']
    raw_id_fields = ['college', 'created_by']
    readonly_fields = ['created_at', 'updated_at']
    filter_horizontal = ['targeted_students', 'targeted_users']
    fieldsets = (
        ('Basic Information', {
            'fields': ('college', 'title', 'content', 'created_by')
        }),
        ('Targeting', {
            'fields': ('target_type', 'targeted_students', 'targeted_users')
        }),
        ('Settings', {
            'fields': ('priority', 'is_active', 'expires_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(StudentSemesterSignIn)
class StudentSemesterSignInAdmin(admin.ModelAdmin):
    list_display = ['student', 'academic_year', 'semester', 'year_of_study_at_signin', 'next_year_of_study', 'next_semester', 'signed_in_at', 'is_processed']
    list_filter = ['academic_year', 'semester', 'is_processed', 'signed_in_at']
    search_fields = ['student__admission_number', 'student__full_name', 'academic_year']
    raw_id_fields = ['student']
    readonly_fields = ['signed_in_at', 'processed_at']
    date_hierarchy = 'signed_in_at'
    fieldsets = (
        ('Student Information', {
            'fields': ('student',)
        }),
        ('Sign-In Details', {
            'fields': ('academic_year', 'semester', 'signed_in_at')
        }),
        ('Academic Progress', {
            'fields': ('year_of_study_at_signin', 'semester_of_study_at_signin', 
                      'next_year_of_study', 'next_semester')
        }),
        ('Processing Status', {
            'fields': ('is_processed', 'processed_at')
        }),
    )


# TranscriptTemplate admin removed - reports now use ReportTemplate with mappings
