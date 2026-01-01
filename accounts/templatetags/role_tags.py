from django import template

register = template.Library()


@register.filter
def can_edit(user):
    """Check if user can edit (not read-only)"""
    return not user.is_read_only()


@register.filter
def can_manage_students(user):
    """Check if user can manage students"""
    return user.can_manage_students() if hasattr(user, 'can_manage_students') else False


@register.filter
def can_manage_courses(user):
    """Check if user can manage courses"""
    return user.can_manage_courses() if hasattr(user, 'can_manage_courses') else False


@register.filter
def can_manage_finance(user):
    """Check if user can manage finance"""
    return user.can_manage_finance() if hasattr(user, 'can_manage_finance') else False


@register.filter
def can_manage_fee_structure(user):
    """Check if user can manage fee structure (Director and College Admin)"""
    return user.can_manage_fee_structure() if hasattr(user, 'can_manage_fee_structure') else False


@register.filter
def can_record_payments(user):
    """Check if user can record payments (Accounts Officer only)"""
    return user.can_record_payments() if hasattr(user, 'can_record_payments') else False


@register.filter
def can_manage_payment_settings(user):
    """Check if user can manage payment settings (MPESA, Bank - Director only)"""
    return user.can_manage_payment_settings() if hasattr(user, 'can_manage_payment_settings') else False


@register.filter
def can_enter_all_marks(user):
    """Check if user can enter marks for all units"""
    return user.can_enter_all_marks() if hasattr(user, 'can_enter_all_marks') else False


@register.filter
def can_export(user):
    """Check if user can export data"""
    return user.can_export_data() if hasattr(user, 'can_export_data') else False

