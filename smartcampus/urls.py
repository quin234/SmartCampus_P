"""
URL configuration for smartcampus project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from education import views

# Configure Django admin to use a separate login template
admin.site.login_template = 'admin/django_admin_login.html'

urlpatterns = [
    # Django admin interface - MUST come first to avoid conflicts
    # Accessible at /django-admin/ (uses separate Django admin login template)
    path('django-admin/', admin.site.urls),
    
    # Landing page at root
    path('', views.landing_page, name='landing'),
    
    # Registration API
    path('api/schools/register', views.register_school, name='register_school'),
    
    # Super Admin App (completely separate)
    path('superadmin/', include('superadmin.urls')),
    
    # Super Admin API endpoints
    path('api/superadmin/', include('superadmin.api_urls')),
    
    # Admin Portal API endpoints (without college_slug - gets college from logged-in user)
    path('api/admin/', include('education.admin_api_urls')),
    
    # College-specific API endpoints
    path('api/<str:college_slug>/', include('education.api_urls')),
    
    # Accounts app routes (must come before education URLs to avoid catch-all pattern)
    path('accounts/', include('accounts.urls')),
    
    # Timetable app routes
    path('timetable/', include('timetable.urls')),
    
    # Education app routes (college admin portal, college-specific pages)
    path('', include('education.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
