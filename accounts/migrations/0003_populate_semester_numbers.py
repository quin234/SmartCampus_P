# Generated migration to populate semester_number from term data

from django.db import migrations
from django.utils import timezone


def populate_semester_numbers(apps, schema_editor):
    """Populate semester_number for existing FeeStructure records"""
    FeeStructure = apps.get_model('accounts', 'FeeStructure')
    
    # For existing fee structures, we need to calculate semester_number
    # Since we removed the term FK, we'll need to handle this carefully
    # For now, set a default value of 1 for existing records
    # This should be manually reviewed and updated
    
    FeeStructure.objects.filter(semester_number__isnull=True).update(semester_number=1)
    
    # Set default versioning fields for existing records
    FeeStructure.objects.filter(version_number__isnull=True).update(
        version_number=1,
        is_current_version=True,
        effective_from=timezone.now().date()
    )


def reverse_populate_semester_numbers(apps, schema_editor):
    """Reverse migration - set semester_number to None"""
    FeeStructure = apps.get_model('accounts', 'FeeStructure')
    FeeStructure.objects.update(semester_number=None)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_add_fee_structure_versioning'),
    ]

    operations = [
        migrations.RunPython(
            populate_semester_numbers,
            reverse_populate_semester_numbers
        ),
    ]


