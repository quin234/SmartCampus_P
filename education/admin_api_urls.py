"""
Admin Portal API URL patterns (without college_slug)
These endpoints get the college from the logged-in user
"""
from django.urls import path
from . import api_views

urlpatterns = [
    # Admin Portal API Endpoints
    path('dashboard/stats', api_views.api_admin_dashboard_stats, name='api_admin_dashboard_stats'),
    path('announcements/recent', api_views.api_admin_announcements_recent, name='api_admin_announcements_recent'),
    path('activity/recent', api_views.api_admin_activity_recent, name='api_admin_activity_recent'),
    path('user/profile', api_views.api_admin_user_profile, name='api_admin_user_profile'),
    path('logout', api_views.api_admin_logout, name='api_admin_logout'),
]





























