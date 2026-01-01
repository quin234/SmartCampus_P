"""
API URL patterns for college-specific endpoints
"""
from django.urls import path
from . import api_views

urlpatterns = [
    # Departments API
    path('departments/', api_views.api_departments_list, name='api_departments_list'),
    path('departments/<int:pk>/', api_views.api_department_detail, name='api_department_detail'),
    
    # Courses API
    path('courses/', api_views.api_courses_list, name='api_courses_list'),
    path('courses/<int:pk>/', api_views.api_course_detail, name='api_course_detail'),
    
    # Global Courses API
    path('global-courses/', api_views.api_global_courses_list, name='api_global_courses_list'),
    
    # Units API
    path('units/', api_views.api_units_list, name='api_units_list'),
    path('units/<int:pk>/', api_views.api_unit_detail, name='api_unit_detail'),
    path('units/my-units/', api_views.api_lecturer_units, name='api_lecturer_units'),
    
    # Global Units API
    path('global-units/', api_views.api_global_units_list, name='api_global_units_list'),
    
    # Students API
    path('students/', api_views.api_students_list, name='api_students_list'),
    path('students/<int:pk>/', api_views.api_student_detail, name='api_student_detail'),
    path('students/<int:pk>/status/', api_views.api_student_status_update, name='api_student_status_update'),
    
    # Lecturers API
    path('lecturers/', api_views.api_lecturers_list, name='api_lecturers_list'),
    path('lecturers/<int:pk>/', api_views.api_lecturer_detail, name='api_lecturer_detail'),
    path('lecturers/<int:pk>/role/', api_views.api_lecturer_role_update, name='api_lecturer_role_update'),
    path('lecturers/<int:pk>/status/', api_views.api_lecturer_status_update, name='api_lecturer_status_update'),
    path('lecturer/announcements/', api_views.api_lecturer_announcements, name='api_lecturer_announcements'),
    path('lecturer/announcements/new-count/', api_views.api_lecturer_new_announcements_count, name='api_lecturer_new_announcements_count'),
    
    # Enrollments API
    path('enrollments/', api_views.api_enrollments_list, name='api_enrollments_list'),
    path('enrollments/<int:pk>/', api_views.api_enrollment_detail, name='api_enrollment_detail'),
    path('enrollments/academic-years/', api_views.api_enrollments_academic_years, name='api_enrollments_academic_years'),
    
    # Results API
    path('results/', api_views.api_results_list, name='api_results_list'),
    path('results/academic-years/', api_views.api_results_academic_years, name='api_results_academic_years'),
    path('results/<int:result_id>/submit/', api_views.api_result_submit, name='api_result_submit'),
    path('results/export-csv/', api_views.api_results_export_csv, name='api_results_export_csv'),
    # Bulk Marks Entry API
    path('lecturer/units/stats/', api_views.api_lecturer_units_with_stats, name='api_lecturer_units_with_stats'),
    path('units/<int:unit_id>/students-marks/', api_views.api_unit_students_marks, name='api_unit_students_marks'),
    path('results/bulk-save/', api_views.api_bulk_save_marks, name='api_bulk_save_marks'),
    path('units/<int:unit_id>/bulk-submit/', api_views.api_bulk_submit_marks, name='api_bulk_submit_marks'),
    
    # Dashboard API
    path('dashboard/overview/', api_views.api_dashboard_overview, name='api_dashboard_overview'),
    
    # Student Portal API
    path('student/dashboard/overview/', api_views.api_student_dashboard_overview, name='api_student_dashboard_overview'),
    path('student/profile/', api_views.api_student_profile, name='api_student_profile'),
    path('student/courses/', api_views.api_student_courses, name='api_student_courses'),
    path('student/units/', api_views.api_student_units, name='api_student_units'),
    path('student/course-units/', api_views.api_student_course_units, name='api_student_course_units'),
    path('student/results/', api_views.api_student_results, name='api_student_results'),
    path('student/results/academic-years/', api_views.api_student_results_academic_years, name='api_student_results_academic_years'),
    path('student/exam-register/', api_views.api_student_exam_register, name='api_student_exam_register'),
    path('student/exam-registrations/', api_views.api_student_exam_registrations, name='api_student_exam_registrations'),
    path('student/timetable/', api_views.api_student_timetable, name='api_student_timetable'),
    path('student/announcements/', api_views.api_student_announcements, name='api_student_announcements'),
    path('student/announcements/new-count/', api_views.api_student_new_announcements_count, name='api_student_new_announcements_count'),
    path('student/fees/', api_views.api_student_fees, name='api_student_fees'),
    path('student/payment/mpesa/initiate/', api_views.api_student_initiate_mpesa_payment, name='api_student_initiate_mpesa_payment'),
    path('student/change-password/', api_views.api_student_change_password, name='api_student_change_password'),
    path('student/signin/', api_views.api_student_semester_signin, name='api_student_semester_signin'),
    path('student/signin/status/', api_views.api_student_signin_status, name='api_student_signin_status'),
    path('student/signin/history/', api_views.api_student_signin_history, name='api_student_signin_history'),
    path('student/academic-settings/', api_views.api_student_academic_settings, name='api_student_academic_settings'),
    
    # Academic Settings API (Admin)
    path('admin/academic-settings/', api_views.api_admin_academic_settings, name='api_admin_academic_settings'),
    path('admin/grading-system/', api_views.api_admin_grading_system, name='api_admin_grading_system'),
    path('admin/profile/', api_views.api_admin_profile, name='api_admin_profile'),
    path('admin/college-info/', api_views.api_college_info, name='api_college_info'),
    
    # Nominal Roll Sign-In API (Admin)
    path('admin/nominal-roll/settings/', api_views.api_admin_nominal_roll_settings, name='api_admin_nominal_roll_settings'),
    path('admin/nominal-roll/list/', api_views.api_admin_nominal_roll_list, name='api_admin_nominal_roll_list'),
    path('admin/nominal-roll/stats/', api_views.api_admin_nominal_roll_stats, name='api_admin_nominal_roll_stats'),
    path('admin/nominal-roll/filters/', api_views.api_admin_nominal_roll_filters, name='api_admin_nominal_roll_filters'),
    
    # Export API (Admin)
    path('admin/export/teachers/', api_views.api_admin_export_teachers, name='api_admin_export_teachers'),
    path('admin/export/units/', api_views.api_admin_export_units, name='api_admin_export_units'),
    path('admin/export/courses/', api_views.api_admin_export_courses, name='api_admin_export_courses'),
    path('admin/export/students/', api_views.api_admin_export_students, name='api_admin_export_students'),
    path('admin/export/students/pdf/', api_views.api_admin_export_students_pdf, name='api_admin_export_students_pdf'),
    
    # Course-Unit Assignment API
    path('courseunits/', api_views.api_courseunits_list, name='api_courseunits_list'),
    
    # Timetable API
    path('timetables/', api_views.api_timetables_list, name='api_timetables_list'),
    path('timetables/<int:pk>/', api_views.api_timetable_detail, name='api_timetable_detail'),
    
    # Announcements API (College Admin)
    path('announcements/', api_views.api_announcements_list, name='api_announcements_list'),
    path('announcements/<int:pk>/', api_views.api_announcement_detail, name='api_announcement_detail'),
    
    # Report Template Mappings API (Admin)
    path('admin/report-template-mapping/', api_views.api_report_template_mapping, name='api_report_template_mapping'),
    
    # Report Templates API
    path('reports/templates/', api_views.api_report_templates_list, name='api_report_templates_list'),
    path('reports/templates/<int:template_id>/', api_views.api_report_template_detail, name='api_report_template_detail'),
    
    # Student PDF Downloads API
    path('student/download/transcript-pdf/', api_views.api_student_download_transcript_pdf, name='api_student_download_transcript_pdf'),
    path('student/download/results-pdf/', api_views.api_student_download_results_pdf, name='api_student_download_results_pdf'),
    path('student/download/registered-units-pdf/', api_views.api_student_download_registered_units_pdf, name='api_student_download_registered_units_pdf'),
    path('student/download/fee-structure-pdf/', api_views.api_student_download_fee_structure_pdf, name='api_student_download_fee_structure_pdf'),
]

