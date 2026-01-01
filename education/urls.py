from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Authentication
    path('logout/', views.logout_view, name='logout'),
    
    # Admin Portal
    path('admin/login/', views.admin_login_page, name='admin_login'),
    path('admin/register/', views.register_page, name='admin_register'),
    
    # Password Reset
    path('admin/password-reset/', views.password_reset_request, name='password_reset_request'),
    path('admin/password-reset/verify/<int:user_id>/', views.password_reset_verify, name='password_reset_verify'),
    path('admin/password-reset/confirm/', views.password_reset_confirm, name='password_reset_confirm'),
    path('admin/password-reset/user/<int:user_id>/', views.admin_password_reset, name='admin_password_reset'),
    
    # Colleges (Super Admin)
    path('colleges/', views.college_list, name='college_list'),
    path('colleges/<int:pk>/', views.college_detail, name='college_detail'),
    path('colleges/<int:pk>/approve/', views.college_approve, name='college_approve'),
    path('colleges/register/', views.college_register, name='college_register'),
    
    # Users (College Admin)
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    
    # Students (College Admin)
    path('students/', views.student_list, name='student_list'),
    path('students/create/', views.student_create, name='student_create'),
    path('students/<int:pk>/', views.student_detail, name='student_detail'),
    
    # Courses (College Admin)
    path('courses/', views.course_list, name='course_list'),
    path('courses/create/', views.course_create, name='course_create'),
    
    # Units (College Admin)
    path('units/', views.unit_list, name='unit_list'),
    path('units/create/', views.unit_create, name='unit_create'),
    
    # Enrollments (College Admin, Lecturer)
    path('enrollments/', views.enrollment_list, name='enrollment_list'),
    path('enrollments/create/', views.enrollment_create, name='enrollment_create'),
    
    # Results (Lecturer, College Admin)
    path('results/', views.result_list, name='result_list'),
    path('results/<int:enrollment_id>/edit/', views.result_edit, name='result_edit'),
    
    # Announcements (College Admin)
    path('announcements/', views.announcements_list, name='announcements_list'),
    
    # Director Dashboard
    path('director/dashboard/', views.director_dashboard, name='director_dashboard'),
    path('director/users/<int:user_id>/edit/', views.edit_user, name='edit_user'),
    path('director/payment/initiate/', views.director_initiate_payment, name='director_initiate_payment'),
    
    # Student Portal (must come before college_landing to avoid conflicts)
    path('<str:college_slug>/login/', views.student_login_page, name='student_login'),
    path('<str:college_slug>/dashboard/', views.student_dashboard_page, name='student_dashboard'),
    path('<str:college_slug>/logout/', views.student_logout_view, name='student_logout'),
    path('<str:college_slug>/signin/', views.student_semester_signin_page, name='student_semester_signin'),
    path('<str:college_slug>/signin/history/', views.student_signin_history_page, name='student_signin_history'),
    # Student timetable view
    path('<str:college_slug>/timetable/student/', views.student_timetable_view, name='student_timetable'),
    
    # College Landing Page (must be last to avoid conflicts with other routes)
    path('<str:college_slug>/', views.college_landing_page, name='college_landing'),
]

