from django.contrib import admin
from .models import Department, FeeStructure, Payment, AccountsSettings, FeeItem, CourseFeeStructure


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['department_name', 'college', 'created_at']
    list_filter = ['college']
    search_fields = ['department_name']


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ['course', 'semester_number', 'fee_type', 'amount', 'version_number', 'is_current_version', 'is_active']
    list_filter = ['college', 'course', 'semester_number', 'fee_type', 'is_current_version', 'is_active']
    search_fields = ['course__name']
    readonly_fields = ['version_number', 'replaced_by_version', 'created_at', 'updated_at']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'student', 'amount_paid', 'payment_method', 'date_paid']
    list_filter = ['payment_method', 'date_paid']
    search_fields = ['receipt_number', 'student__admission_number', 'transaction_code']
    readonly_fields = ['receipt_number', 'created_at', 'updated_at']


@admin.register(AccountsSettings)
class AccountsSettingsAdmin(admin.ModelAdmin):
    list_display = ['college', 'sponsorship_enabled', 'sponsorship_default_discount_type', 'sponsorship_default_discount_value']
    list_filter = ['sponsorship_enabled']
    search_fields = ['college__name']


@admin.register(FeeItem)
class FeeItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'created_at', 'updated_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(CourseFeeStructure)
class CourseFeeStructureAdmin(admin.ModelAdmin):
    list_display = ['course', 'fee_item', 'amount', 'created_at', 'updated_at']
    list_filter = ['course', 'fee_item', 'course__college']
    search_fields = ['course__name', 'fee_item__name']
    readonly_fields = ['created_at', 'updated_at']

