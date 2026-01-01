# Generated migration for automatic invoice generation

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_payment_academic_year_payment_semester_number_and_more'),
        ('education', '0017_student_is_sponsored_student_sponsorship_approved_at_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentInvoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('invoice_number', models.CharField(db_index=True, max_length=50, unique=True)),
                ('semester_number', models.IntegerField(help_text='Course semester number (1, 2, 3...)', validators=[django.core.validators.MinValueValidator(1)])),
                ('academic_year', models.CharField(help_text='Academic year (e.g., 2024/2025)', max_length=20)),
                ('fee_amount', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))])),
                ('date_created', models.DateTimeField(default=timezone.now)),
                ('due_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('partial', 'Partially Paid'), ('paid', 'Fully Paid'), ('overdue', 'Overdue'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('notes', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_invoices', to=settings.AUTH_USER_MODEL)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='education.student')),
            ],
            options={
                'db_table': 'student_invoices',
                'ordering': ['-date_created'],
            },
        ),
        migrations.AddField(
            model_name='payment',
            name='invoice',
            field=models.ForeignKey(blank=True, help_text='Invoice this payment is for (optional)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payments', to='accounts.studentinvoice'),
        ),
        migrations.AddIndex(
            model_name='studentinvoice',
            index=models.Index(fields=['student', 'semester_number'], name='student_inv_student_sem_idx'),
        ),
        migrations.AddIndex(
            model_name='studentinvoice',
            index=models.Index(fields=['status'], name='student_inv_status_idx'),
        ),
        migrations.AddIndex(
            model_name='studentinvoice',
            index=models.Index(fields=['invoice_number'], name='student_inv_invoice_num_idx'),
        ),
        migrations.AddIndex(
            model_name='studentinvoice',
            index=models.Index(fields=['academic_year'], name='student_inv_academic_year_idx'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['invoice'], name='payments_invoice_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='studentinvoice',
            unique_together={('student', 'semester_number')},
        ),
    ]

