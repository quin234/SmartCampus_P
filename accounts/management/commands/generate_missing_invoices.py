"""
Management command to generate missing invoices for students who should have them
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from accounts.models import generate_student_invoice, StudentInvoice
from education.models import Student
from django.utils import timezone


class Command(BaseCommand):
    help = 'Generate missing invoices for students who have courses but no invoices'

    def add_arguments(self, parser):
        parser.add_argument(
            '--college-id',
            type=int,
            help='Generate invoices for a specific college only',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be generated without actually creating invoices',
        )

    def handle(self, *args, **options):
        college_id = options.get('college_id')
        dry_run = options.get('dry_run', False)
        
        # Get students with courses
        students = Student.objects.filter(course__isnull=False).select_related('course', 'college')
        
        if college_id:
            students = students.filter(college_id=college_id)
        
        total_generated = 0
        total_skipped = 0
        errors = []
        
        self.stdout.write(f"Processing {students.count()} students...")
        
        for student in students:
            try:
                # Get student's current semester number in course
                current_semester_number = student.get_course_semester_number()
                
                if not current_semester_number:
                    continue
                
                # Generate invoices for all semesters up to current semester
                for sem_num in range(1, current_semester_number + 1):
                    # Check if invoice already exists
                    if StudentInvoice.objects.filter(student=student, semester_number=sem_num).exists():
                        continue
                    
                    if dry_run:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[DRY RUN] Would generate invoice for {student.admission_number} - Semester {sem_num}"
                            )
                        )
                        total_generated += 1
                    else:
                        # Generate invoice
                        invoice = generate_student_invoice(
                            student=student,
                            semester_number=sem_num,
                            academic_year=student.college.current_academic_year
                        )
                        
                        if invoice:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Generated invoice {invoice.invoice_number} for {student.admission_number} - Semester {sem_num}"
                                )
                            )
                            total_generated += 1
                        else:
                            total_skipped += 1
                            
            except Exception as e:
                error_msg = f"Error processing student {student.admission_number}: {str(e)}"
                errors.append(error_msg)
                self.stdout.write(self.style.ERROR(error_msg))
        
        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(f"Summary:"))
        self.stdout.write(f"  Generated: {total_generated}")
        self.stdout.write(f"  Skipped: {total_skipped}")
        if errors:
            self.stdout.write(self.style.ERROR(f"  Errors: {len(errors)}"))
            for error in errors[:10]:  # Show first 10 errors
                self.stdout.write(self.style.ERROR(f"    - {error}"))

