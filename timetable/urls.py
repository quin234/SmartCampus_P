from django.urls import path
from . import views

app_name = 'timetable'

urlpatterns = [
    # Upload Timetable - Only Registrar
    path('upload/', views.upload_timetable, name='upload_timetable'),
    
    # General Timetable - Registrar and others (Director blocked)
    path('general/', views.general_timetable, name='general_timetable'),
    
    # Course-Specific Timetable - Registrar and others (Director blocked)
    path('course/', views.course_specific_timetable, name='course_specific_timetable'),
    path('course/<int:course_id>/', views.course_specific_timetable, name='course_specific_timetable_detail'),
    
    # Generate Timetable - Only Registrar
    path('generate/', views.generate_timetable, name='generate_timetable'),
    
    # Deploy Timetable - Only Registrar
    path('deploy/<int:timetable_run_id>/', views.deploy_timetable, name='deploy_timetable'),
    
    # Export PDF - Registrar and others (Director blocked)
    path('export/<int:timetable_run_id>/pdf/', views.export_timetable_pdf, name='export_timetable_pdf'),
    
    # Edit Timetable - Only Registrar
    path('edit/<int:timetable_id>/', views.edit_timetable, name='edit_timetable'),
    
    # Delete Timetable - Only Registrar
    path('delete/<int:timetable_id>/', views.delete_timetable, name='delete_timetable'),
    
    # Manage Reference Data - Visible to all except Director (editing restricted to Registrar)
    path('manage/classrooms/', views.manage_classrooms, name='manage_classrooms'),
    path('manage/days/', views.manage_days, name='manage_days'),
    path('manage/time-slots/', views.manage_time_slots, name='manage_time_slots'),
    
    # My Timetable - Registrar, Principal, Lecturer
    path('my-timetable/', views.my_timetable, name='my_timetable'),
    
    # API endpoints for grid editing
    path('api/entry/<int:entry_id>/edit/', views.edit_timetable_entry, name='edit_timetable_entry'),
    path('api/run/<int:run_id>/toggle-edit/', views.toggle_edit_mode, name='toggle_edit_mode'),
    path('api/run/<int:run_id>/grid-data/', views.get_grid_data, name='get_grid_data'),
    path('api/grid-init/', views.api_grid_init, name='api_grid_init'),
]

