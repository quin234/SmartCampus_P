"""
Django management command to create examination test data.
This command adds exam registrations and results with different statuses to existing enrollments.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import random

from education.models import (
    College, Student, Enrollment, Result, CustomUser, CollegeUnit
)


class Command(BaseCommand):
    help = 'Create examination test data: exam registrations and results with different statuses'

    def add_arguments(self, parser):
        parser.add_argument(
            '--college',
            type=str,
            help='College slug or name to create test data for (optional, creates for all colleges if not specified)',
        )
        parser.add_argument(
            '--registration-rate',
            type=float,
            default=0.7,
            help='Percentage of enrollments to register for exams (default: 0.7 = 70%%)',
        )
        parser.add_argument(
            '--result-rate',
            type=float,
            default=0.6,
            help='Percentage of exam-registered enrollments to create results for (default: 0.6 = 60%%)',
        )
        parser.add_argument(
            '--submitted-rate',
            type=float,
            default=0.4,
            help='Percentage of results to mark as submitted (default: 0.4 = 40%%)',
        )

    def handle(self, *args, **options):
        college_filter = options.get('college')
        registration_rate = options['registration_rate']
        result_rate = options['result_rate']
        submitted_rate = options['submitted_rate']

        self.stdout.write(self.style.SUCCESS('Creating examination test data...'))
        self.stdout.write(f'Registration rate: {registration_rate * 100}%')
        self.stdout.write(f'Result creation rate: {result_rate * 100}%')
        self.stdout.write(f'Submitted rate: {submitted_rate * 100}%')

        # Get colleges to process
        if college_filter:
            try:
                colleges = [College.objects.get(name__icontains=college_filter)]
            except College.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'College "{college_filter}" not found'))
                return
            except College.MultipleObjectsReturned:
                self.stdout.write(self.style.WARNING(f'Multiple colleges found for "{college_filter}", using first match'))
                colleges = [College.objects.filter(name__icontains=college_filter).first()]
        else:
            colleges = College.objects.filter(registration_status='active')

        if not colleges:
            self.stdout.write(self.style.ERROR('No active colleges found'))
            return

        total_registrations = 0
        total_results = 0
        total_submitted = 0

        for college in colleges:
            self.stdout.write(f'\nProcessing {college.name}...')

            # Get current academic year enrollments
            current_year = timezone.now().year
            current_academic_year = f"{current_year}/{current_year + 1}"

            # Get enrollments for current academic year
            enrollments = Enrollment.objects.filter(
                student__college=college,
                academic_year=current_academic_year
            ).select_related('student', 'unit', 'unit__assigned_lecturer')

            if not enrollments.exists():
                self.stdout.write(self.style.WARNING(f'  No enrollments found for {current_academic_year}'))
                continue

            self.stdout.write(f'  Found {enrollments.count()} enrollments')

            # Step 1: Register students for exams
            registrations_created = self.register_students_for_exams(
                enrollments, registration_rate
            )
            total_registrations += registrations_created
            self.stdout.write(f'  Registered {registrations_created} students for exams')

            # Step 2: Get exam-registered enrollments
            exam_registered_enrollments = Enrollment.objects.filter(
                student__college=college,
                academic_year=current_academic_year,
                exam_registered=True
            ).select_related('student', 'unit', 'unit__assigned_lecturer')

            # Step 3: Create results for exam-registered enrollments
            results_created, submitted_count = self.create_results(
                exam_registered_enrollments, result_rate, submitted_rate
            )
            total_results += results_created
            total_submitted += submitted_count
            self.stdout.write(f'  Created {results_created} results ({submitted_count} submitted, {results_created - submitted_count} draft)')

        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '='*50))
        self.stdout.write(self.style.SUCCESS('Examination Test Data Summary:'))
        self.stdout.write(f'  Total Exam Registrations: {total_registrations}')
        self.stdout.write(f'  Total Results Created: {total_results}')
        self.stdout.write(f'  - Submitted Results: {total_submitted}')
        self.stdout.write(f'  - Draft Results: {total_results - total_submitted}')
        self.stdout.write(self.style.SUCCESS('='*50))

    def register_students_for_exams(self, enrollments, registration_rate):
        """Register students for examinations"""
        registrations_created = 0
        registered_time = timezone.now() - timedelta(days=random.randint(1, 30))

        # Select enrollments to register (based on rate)
        num_to_register = int(len(enrollments) * registration_rate)
        enrollments_to_register = random.sample(list(enrollments), min(num_to_register, len(enrollments)))

        for enrollment in enrollments_to_register:
            if not enrollment.exam_registered:
                # Random registration time within last 30 days
                registration_time = timezone.now() - timedelta(
                    days=random.randint(1, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )
                enrollment.exam_registered = True
                enrollment.exam_registered_at = registration_time
                enrollment.save(update_fields=['exam_registered', 'exam_registered_at'])
                registrations_created += 1

        return registrations_created

    def create_results(self, enrollments, result_rate, submitted_rate):
        """Create results for exam-registered enrollments"""
        results_created = 0
        submitted_count = 0

        # Select enrollments to create results for
        num_results = int(len(enrollments) * result_rate)
        enrollments_for_results = random.sample(list(enrollments), min(num_results, len(enrollments)))

        for enrollment in enrollments_for_results:
            # Skip if result already exists
            if hasattr(enrollment, 'result'):
                continue

            # Get lecturer (unit's assigned lecturer or find a lecturer from the college)
            lecturer = enrollment.unit.assigned_lecturer
            if not lecturer:
                lecturers = CustomUser.objects.filter(
                    college=enrollment.student.college,
                    role='lecturer',
                    is_active=True
                )
                if lecturers.exists():
                    lecturer = random.choice(list(lecturers))
                else:
                    # If no lecturer, skip this enrollment
                    continue

            # Generate realistic marks
            # CAT marks: 30-100 (most students score 50-90)
            cat_marks = round(random.uniform(30, 100), 2)
            if random.random() < 0.7:  # 70% chance of good marks
                cat_marks = round(random.uniform(50, 90), 2)

            # Exam marks: 40-100 (most students score 50-85)
            exam_marks = round(random.uniform(40, 100), 2)
            if random.random() < 0.7:  # 70% chance of good marks
                exam_marks = round(random.uniform(50, 85), 2)

            # Calculate total
            total = round((cat_marks * 0.3) + (exam_marks * 0.7), 2)

            # Determine status
            is_submitted = random.random() < submitted_rate
            status = 'submitted' if is_submitted else 'draft'
            submitted_at = None
            if is_submitted:
                # Submitted within last 7 days
                submitted_at = timezone.now() - timedelta(
                    days=random.randint(0, 7),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )
                submitted_count += 1

            # Create result
            Result.objects.create(
                enrollment=enrollment,
                cat_marks=cat_marks,
                exam_marks=exam_marks,
                total=total,
                status=status,
                submitted_at=submitted_at,
                entered_by=lecturer
            )
            results_created += 1

        return results_created, submitted_count

