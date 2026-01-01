# Generated migration for examination and results management system

from django.db import migrations, models
from django.utils import timezone


def set_default_draft_status(apps, schema_editor):
    """Set default status='draft' for existing results"""
    Result = apps.get_model('education', 'Result')
    Result.objects.filter(status__isnull=True).update(status='draft')


class Migration(migrations.Migration):

    dependencies = [
        ('education', '0005_update_semester_to_3'),
    ]

    operations = [
        # Add exam registration fields to Enrollment
        migrations.AddField(
            model_name='enrollment',
            name='exam_registered',
            field=models.BooleanField(default=False, help_text='Whether student has registered for examination'),
        ),
        migrations.AddField(
            model_name='enrollment',
            name='exam_registered_at',
            field=models.DateTimeField(blank=True, help_text='Date and time when student registered for examination', null=True),
        ),
        # Add status and submitted_at fields to Result
        migrations.AddField(
            model_name='result',
            name='status',
            field=models.CharField(choices=[('draft', 'Draft'), ('submitted', 'Submitted')], default='draft', help_text='Result status: draft or submitted', max_length=20),
        ),
        migrations.AddField(
            model_name='result',
            name='submitted_at',
            field=models.DateTimeField(blank=True, help_text='Date and time when result was submitted', null=True),
        ),
        # Set default status for existing results
        migrations.RunPython(set_default_draft_status, migrations.RunPython.noop),
    ]

