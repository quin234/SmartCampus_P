"""
Super Admin API URL Configuration
"""
from django.urls import path
from . import api_views

urlpatterns = [
    # Overview/Statistics
    path('overview/', api_views.api_overview, name='api_overview'),
    
    # Colleges Management
    path('colleges/', api_views.api_colleges, name='api_colleges'),
    
    # Individual college operations (must come before bulk operations for proper routing)
    path('colleges/<int:college_id>/', api_views.api_college_detail, name='api_college_detail'),
    path('colleges/<int:college_id>/approve/', api_views.api_college_approve, name='api_college_approve'),
    path('colleges/<int:college_id>/suspend/', api_views.api_college_suspend, name='api_college_suspend'),
    
    # Bulk operations
    path('colleges/bulk-approve/', api_views.api_colleges_bulk_approve, name='api_colleges_bulk_approve'),
    path('colleges/bulk-suspend/', api_views.api_colleges_bulk_suspend, name='api_colleges_bulk_suspend'),
    path('colleges/bulk-delete/', api_views.api_colleges_bulk_delete, name='api_colleges_bulk_delete'),
    
    # Analytics
    path('analytics/', api_views.api_analytics, name='api_analytics'),
    
    # Settings
    path('settings/', api_views.api_settings, name='api_settings'),
    
    # Profile
    path('profile/', api_views.api_profile, name='api_profile'),
    
    # Detail endpoints for analytics cards
    path('students/detail/', api_views.api_students_detail, name='api_students_detail'),
    path('lecturers/detail/', api_views.api_lecturers_detail, name='api_lecturers_detail'),
    path('colleges/detail/', api_views.api_colleges_detail, name='api_colleges_detail'),
    path('colleges/cards/', api_views.api_colleges_cards, name='api_colleges_cards'),
]

