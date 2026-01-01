"""
Django management command to create test data for Colleges, Lecturers, Courses, Units, and Students.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
import random
import string

from education.models import (
    College, CustomUser, CollegeCourse, CollegeUnit, Student, Enrollment, Result
)


class Command(BaseCommand):
    help = 'Create test data for Colleges, Lecturers, Courses, Units, and Students'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing test data before creating new data',
        )
        parser.add_argument(
            '--colleges',
            type=int,
            default=5,
            help='Number of colleges to create (default: 5)',
        )
        parser.add_argument(
            '--students',
            type=int,
            default=25,
            help='Number of students per college (default: 25)',
        )

    def handle(self, *args, **options):
        clear_data = options['clear']
        num_colleges = options['colleges']
        students_per_college = options['students']

        # Initialize college prefixes dictionary
        self.college_prefixes = {}

        if clear_data:
            self.stdout.write(self.style.WARNING('Clearing existing test data...'))
            self.clear_test_data()

        self.stdout.write(self.style.SUCCESS('Creating test data...'))
        self.stdout.write(f'Colleges: {num_colleges}')
        self.stdout.write(f'Students per college: {students_per_college}')

        # Create colleges
        colleges = self.create_colleges(num_colleges)

        for college in colleges:
            self.stdout.write(f'\nCreating data for {college.name}...')
            
            # Create lecturers
            lecturers = self.create_lecturers(college, random.randint(5, 8))
            
            # Create courses
            courses = self.create_courses(college, random.randint(3, 5))
            
            # Create units
            units = self.create_units(college, lecturers, random.randint(8, 12))
            
            # Create students
            students = self.create_students(college, courses, students_per_college)
            
            # Create enrollments and results
            self.create_enrollments_and_results(students, units, lecturers)

        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully created test data!'))
        self.stdout.write(f'Total Colleges: {College.objects.count()}')
        self.stdout.write(f'Total Lecturers: {CustomUser.objects.filter(role="lecturer").count()}')
        self.stdout.write(f'Total Courses: {CollegeCourse.objects.count()}')
        self.stdout.write(f'Total Units: {CollegeUnit.objects.count()}')
        self.stdout.write(f'Total Students: {Student.objects.count()}')
        self.stdout.write(f'Total Enrollments: {Enrollment.objects.count()}')
        self.stdout.write(f'Total Results: {Result.objects.count()}')

    def clear_test_data(self):
        """Delete all test data"""
        Result.objects.all().delete()
        Enrollment.objects.all().delete()
        Student.objects.all().delete()
        CollegeUnit.objects.all().delete()
        CollegeCourse.objects.all().delete()
        CustomUser.objects.filter(role='lecturer').delete()
        CustomUser.objects.filter(role='college_admin').delete()
        College.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('Test data cleared.'))

    def create_colleges(self, num_colleges):
        """Create test colleges"""
        colleges_data = [
            {
                'name': 'Nova Crest College',
                'address': '123 Education Avenue, Nairobi',
                'county': 'Nairobi',
                'email': 'info@novacrest.edu',
                'phone': '+254712345678',
                'principal_name': 'Dr. James Mwangi',
                'status': 'active',
                'prefix': 'NCC'
            },
            {
                'name': 'Tech Institute',
                'address': '456 Innovation Road, Mombasa',
                'county': 'Mombasa',
                'email': 'contact@techinstitute.edu',
                'phone': '+254723456789',
                'principal_name': 'Prof. Sarah Ochieng',
                'status': 'active',
                'prefix': 'TI'
            },
            {
                'name': 'Business Academy',
                'address': '789 Commerce Street, Kisumu',
                'county': 'Kisumu',
                'email': 'admin@businessacademy.edu',
                'phone': '+254734567890',
                'principal_name': 'Dr. Peter Kamau',
                'status': 'active',
                'prefix': 'BA'
            },
            {
                'name': 'Arts & Sciences College',
                'address': '321 Culture Lane, Nakuru',
                'county': 'Nakuru',
                'email': 'info@artsandsciences.edu',
                'phone': '+254745678901',
                'principal_name': 'Dr. Mary Wanjiku',
                'status': 'pending',
                'prefix': 'ASC'
            },
            {
                'name': 'Engineering Excellence College',
                'address': '654 Technology Drive, Eldoret',
                'county': 'Uasin Gishu',
                'email': 'contact@engineeringexcellence.edu',
                'phone': '+254756789012',
                'principal_name': 'Eng. David Kipchoge',
                'status': 'active',
                'prefix': 'EEC'
            },
        ]

        colleges = []
        for i, college_data in enumerate(colleges_data[:num_colleges]):
            college, created = College.objects.get_or_create(
                email=college_data['email'],
                defaults={
                    'name': college_data['name'],
                    'address': college_data['address'],
                    'county': college_data['county'],
                    'phone': college_data['phone'],
                    'principal_name': college_data['principal_name'],
                    'registration_status': college_data['status']
                }
            )
            # Store prefix in a dictionary for later use
            self.college_prefixes[college.id] = college_data['prefix']
            colleges.append(college)
            if created:
                self.stdout.write(f'  Created college: {college.name}')
            else:
                self.stdout.write(f'  College already exists: {college.name}')

        return colleges

    def create_lecturers(self, college, num_lecturers):
        """Create lecturers for a college"""
        first_names = ['John', 'Jane', 'Michael', 'Sarah', 'David', 'Emily', 'Robert', 'Lisa', 
                      'William', 'Jennifer', 'James', 'Mary', 'Richard', 'Patricia', 'Joseph']
        last_names = ['Mwangi', 'Ochieng', 'Kamau', 'Wanjiku', 'Kipchoge', 'Njoroge', 'Onyango',
                     'Achieng', 'Omondi', 'Wambui', 'Kariuki', 'Njeri', 'Oloo', 'Akinyi', 'Onyango']

        lecturers = []
        for i in range(num_lecturers):
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            username = f"{first_name.lower()}.{last_name.lower()}.{college.id}.{i+1}"
            email = f"{username}@{college.name.lower().replace(' ', '').replace('&', '')}.edu"
            
            # Ensure unique username
            counter = 1
            original_username = username
            while CustomUser.objects.filter(username=username).exists():
                username = f"{original_username}{counter}"
                counter += 1

            lecturer, created = CustomUser.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'phone': f"+2547{random.randint(10000000, 99999999)}",
                    'role': 'lecturer',
                    'college': college,
                    'is_active': True
                }
            )
            lecturer.set_password('lecturer123')  # Default password
            lecturer.save()

            lecturers.append(lecturer)
            if created:
                self.stdout.write(f'    Created lecturer: {lecturer.get_full_name()}')

        return lecturers

    def create_courses(self, college, num_courses):
        """Create courses for a college"""
        course_templates = [
            {'name': 'Computer Science', 'duration': 4},
            {'name': 'Business Administration', 'duration': 3},
            {'name': 'Engineering', 'duration': 4},
            {'name': 'Arts and Design', 'duration': 3},
            {'name': 'Information Technology', 'duration': 3},
            {'name': 'Accounting', 'duration': 3},
            {'name': 'Nursing', 'duration': 4},
            {'name': 'Education', 'duration': 4},
            {'name': 'Hospitality Management', 'duration': 2},
            {'name': 'Journalism', 'duration': 3},
        ]

        courses = []
        selected_courses = random.sample(course_templates, min(num_courses, len(course_templates)))
        
        for course_data in selected_courses:
            course, created = CollegeCourse.objects.get_or_create(
                college=college,
                name=course_data['name'],
                defaults={
                    'duration_years': course_data['duration']
                }
            )
            courses.append(course)
            if created:
                self.stdout.write(f'    Created course: {course.name}')

        return courses

    def create_units(self, college, lecturers, num_units):
        """Create units for a college"""
        unit_templates = [
            {'name': 'Introduction to Programming', 'code': 'CS101', 'semester': 1},
            {'name': 'Database Systems', 'code': 'CS201', 'semester': 2},
            {'name': 'Web Development', 'code': 'CS301', 'semester': 3},
            {'name': 'Software Engineering', 'code': 'CS401', 'semester': 4},
            {'name': 'Business Ethics', 'code': 'BA101', 'semester': 1},
            {'name': 'Financial Accounting', 'code': 'BA201', 'semester': 2},
            {'name': 'Marketing Principles', 'code': 'BA301', 'semester': 3},
            {'name': 'Operations Management', 'code': 'BA401', 'semester': 4},
            {'name': 'Calculus I', 'code': 'MATH101', 'semester': 1},
            {'name': 'Statistics', 'code': 'MATH201', 'semester': 2},
            {'name': 'Communication Skills', 'code': 'COM101', 'semester': 1},
            {'name': 'Research Methods', 'code': 'RES301', 'semester': 3},
            {'name': 'Project Management', 'code': 'PM301', 'semester': 3},
            {'name': 'Entrepreneurship', 'code': 'ENT201', 'semester': 2},
            {'name': 'Data Structures', 'code': 'CS202', 'semester': 2},
            {'name': 'Computer Networks', 'code': 'CS302', 'semester': 3},
            {'name': 'Operating Systems', 'code': 'CS402', 'semester': 4},
            {'name': 'Microeconomics', 'code': 'ECO101', 'semester': 1},
            {'name': 'Macroeconomics', 'code': 'ECO201', 'semester': 2},
            {'name': 'Human Resource Management', 'code': 'HRM301', 'semester': 3},
        ]

        units = []
        selected_units = random.sample(unit_templates, min(num_units, len(unit_templates)))
        
        for unit_data in selected_units:
            # Ensure unique code per college
            code = unit_data['code']
            counter = 1
            original_code = code
            while CollegeUnit.objects.filter(college=college, code=code).exists():
                code = f"{original_code}{counter}"
                counter += 1

            # Assign lecturer to 60% of units
            assigned_lecturer = None
            if random.random() < 0.6 and lecturers:
                assigned_lecturer = random.choice(lecturers)

            unit, created = CollegeUnit.objects.get_or_create(
                college=college,
                code=code,
                defaults={
                    'name': unit_data['name'],
                    'semester': unit_data['semester'],
                    'assigned_lecturer': assigned_lecturer
                }
            )
            units.append(unit)
            if created:
                self.stdout.write(f'    Created unit: {unit.code} - {unit.name}')

        return units

    def create_students(self, college, courses, num_students):
        """Create students for a college"""
        first_names = ['John', 'Jane', 'Michael', 'Sarah', 'David', 'Emily', 'Robert', 'Lisa',
                      'William', 'Jennifer', 'James', 'Mary', 'Richard', 'Patricia', 'Joseph',
                      'Linda', 'Thomas', 'Barbara', 'Charles', 'Elizabeth', 'Daniel', 'Susan',
                      'Matthew', 'Jessica', 'Anthony', 'Karen', 'Mark', 'Nancy', 'Donald', 'Betty']
        last_names = ['Mwangi', 'Ochieng', 'Kamau', 'Wanjiku', 'Kipchoge', 'Njoroge', 'Onyango',
                     'Achieng', 'Omondi', 'Wambui', 'Kariuki', 'Njeri', 'Oloo', 'Akinyi', 'Onyango',
                     'Ochieng', 'Onyango', 'Omondi', 'Achieng', 'Wanjiku', 'Njoroge', 'Kariuki',
                     'Mwangi', 'Kamau', 'Wambui', 'Njeri', 'Oloo', 'Akinyi', 'Onyango', 'Ochieng']
        
        genders = ['M', 'F', 'M', 'F', 'M', 'F', 'M', 'F', 'M', 'F']  # 50/50 distribution

        # Get college prefix from stored prefixes or generate from name
        if college.id in self.college_prefixes:
            prefix = self.college_prefixes[college.id]
        else:
            prefix = ''.join([word[0].upper() for word in college.name.split() if word[0].isalpha()])[:3]
            if not prefix:
                prefix = 'COL'

        students = []
        for i in range(num_students):
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            full_name = f"{first_name} {last_name}"
            gender = random.choice(genders)
            
            # Generate admission number
            admission_number = f"{prefix}{str(i+1).zfill(3)}"
            
            # Ensure unique admission number per college
            counter = 1
            original_admission = admission_number
            while Student.objects.filter(college=college, admission_number=admission_number).exists():
                admission_number = f"{original_admission}{counter}"
                counter += 1

            # Assign 80% of students to courses
            course = None
            if random.random() < 0.8 and courses:
                course = random.choice(courses)

            # Generate date of birth (ages 18-25)
            years_ago = random.randint(18, 25)
            date_of_birth = date.today() - timedelta(days=years_ago * 365 + random.randint(0, 365))

            # Generate email
            email = f"{first_name.lower()}.{last_name.lower()}.{i+1}@{college.name.lower().replace(' ', '').replace('&', '')}.edu"

            student, created = Student.objects.get_or_create(
                college=college,
                admission_number=admission_number,
                defaults={
                    'full_name': full_name,
                    'course': course,
                    'year_of_study': random.randint(1, 4),
                    'gender': gender,
                    'date_of_birth': date_of_birth,
                    'email': email,
                    'phone': f"+2547{random.randint(10000000, 99999999)}"
                }
            )
            students.append(student)
            if created and (i + 1) % 10 == 0:
                self.stdout.write(f'    Created {i+1} students...')

        self.stdout.write(f'    Created {len(students)} students for {college.name}')
        return students

    def create_enrollments_and_results(self, students, units, lecturers):
        """Create enrollments and some results"""
        academic_years = ['2023/2024', '2024/2025', '2025/2026']
        
        enrollments_created = 0
        results_created = 0

        # Enroll 50% of students in 2-3 units each (reduced for speed)
        enrolled_students = random.sample(students, int(len(students) * 0.5))
        
        for student in enrolled_students:
            # Select 2-3 random units for this student (reduced from 2-4)
            num_units = random.randint(2, 3)
            selected_units = random.sample(units, min(num_units, len(units)))
            academic_year = random.choice(academic_years)

            for unit in selected_units:
                # Check if enrollment already exists
                if not Enrollment.objects.filter(
                    student=student,
                    unit=unit,
                    academic_year=academic_year,
                    semester=unit.semester
                ).exists():
                    enrollment = Enrollment.objects.create(
                        student=student,
                        unit=unit,
                        academic_year=academic_year,
                        semester=unit.semester
                    )
                    enrollments_created += 1

                    # Create results for 30% of enrollments (reduced from 40%)
                    if random.random() < 0.3:
                        # Get lecturer (unit's assigned lecturer or random lecturer)
                        lecturer = unit.assigned_lecturer
                        if not lecturer and lecturers:
                            lecturer = random.choice(lecturers)

                        # Generate marks
                        cat_marks = round(random.uniform(30, 100), 2)
                        exam_marks = round(random.uniform(40, 100), 2)
                        total = round((cat_marks * 0.3) + (exam_marks * 0.7), 2)

                        Result.objects.create(
                            enrollment=enrollment,
                            cat_marks=cat_marks,
                            exam_marks=exam_marks,
                            total=total,
                            entered_by=lecturer
                        )
                        results_created += 1

        self.stdout.write(f'    Created {enrollments_created} enrollments and {results_created} results')

