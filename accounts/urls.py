from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.accounts_dashboard, name='dashboard'),
    
    # Departments
    path('departments/', views.department_list, name='department_list'),
    path('departments/create/', views.department_create, name='department_create'),
    
    
    # Fee Structure
    path('fee-structure/', views.fee_structure_list, name='fee_structure_list'),
    path('fee-structure/create/', views.fee_structure_create, name='fee_structure_create'),
    path('fee-structure/<int:pk>/edit/', views.fee_structure_edit, name='fee_structure_edit'),
    # New redesigned fee structure flow
    path('fee-structure/courses/', views.fee_structure_courses_list, name='fee_structure_courses_list'),
    path('fee-structure/course/<int:course_id>/', views.fee_structure_course_detail, name='fee_structure_course_detail'),
    # Fee Item Management
    path('fee-structure/fee-items/', views.fee_item_list, name='fee_item_list'),
    path('fee-structure/fee-items/create/', views.fee_item_create, name='fee_item_create'),
    path('fee-structure/fee-items/<int:fee_item_id>/edit/', views.fee_item_edit, name='fee_item_edit'),
    
    # Payments
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/create/', views.payment_create, name='payment_create'),
    path('payments/<int:pk>/', views.payment_detail, name='payment_detail'),
    
    # Reports
    path('reports/balances/', views.balance_report, name='balance_report'),
    path('reports/debtors/', views.debtors_report, name='debtors_report'),
    path('reports/payments-by-term/', views.payments_by_term_report, name='payments_by_term_report'),
    
    # Settings
    path('settings/', views.accounts_settings, name='accounts_settings'),
    
    # Student Balances
    path('balances/', views.student_balances, name='student_balances'),
    
    # Invoice
    path('invoice/', views.invoice_list, name='invoice_list'),
    path('invoice/generate/<int:student_id>/', views.generate_student_invoices, name='generate_student_invoices'),
    
    # Daraja M-Pesa Payment
    path('payment/daraja/callback/', views.daraja_payment_callback, name='daraja_payment_callback'),
    
    # Daily Expenditure
    path('expenditure/draft/', views.daily_expenditure_draft, name='daily_expenditure_draft'),
    path('expenditure/draft/<int:pk>/edit/', views.daily_expenditure_draft, name='daily_expenditure_edit'),
    path('expenditure/submit/', views.submit_daily_expenditure, name='submit_daily_expenditure'),
    path('expenditure/report/', views.daily_expenditure_report, name='daily_expenditure_report'),
    path('expenditure/graph-data/', views.daily_expenditure_graph_data, name='daily_expenditure_graph_data'),
]

