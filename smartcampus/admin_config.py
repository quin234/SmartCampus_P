"""
Custom Django Admin Configuration
This ensures Django admin uses its own login mechanism
"""
from django.contrib import admin
from django.contrib.admin.sites import AdminSite

# Configure admin site to use its own login
admin.site.login_template = 'admin/login.html'  # Use Django's default admin login template
admin.site.login = admin.site.login  # Keep default login view

