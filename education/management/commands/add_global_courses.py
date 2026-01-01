"""
Django management command to add common Kenyan college courses to GlobalCourse database
"""
from django.core.management.base import BaseCommand
from education.models import GlobalCourse


class Command(BaseCommand):
    help = 'Adds common Kenyan college courses to the GlobalCourse database'

    def handle(self, *args, **options):
        courses_data = [
            # BUSINESS & COMMERCE
            {'name': 'Certificate in Business Administration', 'level': 'certificate', 'category': 'Business & Commerce'},
            {'name': 'Diploma in Business Administration', 'level': 'diploma', 'category': 'Business & Commerce'},
            {'name': 'Higher Diploma in Business Administration', 'level': 'higher_diploma', 'category': 'Business & Commerce'},
            {'name': 'Certificate in Business Management', 'level': 'certificate', 'category': 'Business & Commerce'},
            {'name': 'Diploma in Business Management', 'level': 'diploma', 'category': 'Business & Commerce'},
            {'name': 'Higher Diploma in Business Management', 'level': 'higher_diploma', 'category': 'Business & Commerce'},
            {'name': 'Certificate in Accounting and Finance', 'level': 'certificate', 'category': 'Business & Commerce'},
            {'name': 'Diploma in Accounting and Finance', 'level': 'diploma', 'category': 'Business & Commerce'},
            {'name': 'Higher Diploma in Accounting and Finance', 'level': 'higher_diploma', 'category': 'Business & Commerce'},
            {'name': 'Certificate in Human Resource Management', 'level': 'certificate', 'category': 'Business & Commerce'},
            {'name': 'Diploma in Human Resource Management', 'level': 'diploma', 'category': 'Business & Commerce'},
            {'name': 'Higher Diploma in Human Resource Management', 'level': 'higher_diploma', 'category': 'Business & Commerce'},
            {'name': 'Certificate in Marketing', 'level': 'certificate', 'category': 'Business & Commerce'},
            {'name': 'Diploma in Marketing', 'level': 'diploma', 'category': 'Business & Commerce'},
            {'name': 'Higher Diploma in Marketing', 'level': 'higher_diploma', 'category': 'Business & Commerce'},
            {'name': 'Certificate in Entrepreneurship', 'level': 'certificate', 'category': 'Business & Commerce'},
            {'name': 'Diploma in Entrepreneurship', 'level': 'diploma', 'category': 'Business & Commerce'},
            {'name': 'Certificate in Banking and Finance', 'level': 'certificate', 'category': 'Business & Commerce'},
            {'name': 'Diploma in Banking and Finance', 'level': 'diploma', 'category': 'Business & Commerce'},
            {'name': 'Higher Diploma in Banking and Finance', 'level': 'higher_diploma', 'category': 'Business & Commerce'},
            {'name': 'Diploma in Procurement and Supply Chain Management', 'level': 'diploma', 'category': 'Business & Commerce'},
            {'name': 'Higher Diploma in Procurement and Supply Chain Management', 'level': 'higher_diploma', 'category': 'Business & Commerce'},
            {'name': 'Diploma in Cooperative Management', 'level': 'diploma', 'category': 'Business & Commerce'},
            
            # INFORMATION TECHNOLOGY & COMPUTING
            {'name': 'Certificate in Information Technology', 'level': 'certificate', 'category': 'Information Technology & Computing'},
            {'name': 'Diploma in Information Technology', 'level': 'diploma', 'category': 'Information Technology & Computing'},
            {'name': 'Higher Diploma in Information Technology', 'level': 'higher_diploma', 'category': 'Information Technology & Computing'},
            {'name': 'Diploma in Computer Science', 'level': 'diploma', 'category': 'Information Technology & Computing'},
            {'name': 'Higher Diploma in Computer Science', 'level': 'higher_diploma', 'category': 'Information Technology & Computing'},
            {'name': 'Diploma in Software Engineering', 'level': 'diploma', 'category': 'Information Technology & Computing'},
            {'name': 'Higher Diploma in Software Engineering', 'level': 'higher_diploma', 'category': 'Information Technology & Computing'},
            {'name': 'Certificate in Computer Applications', 'level': 'certificate', 'category': 'Information Technology & Computing'},
            {'name': 'Diploma in Computer Applications', 'level': 'diploma', 'category': 'Information Technology & Computing'},
            {'name': 'Certificate in Information Communication Technology', 'level': 'certificate', 'category': 'Information Technology & Computing'},
            {'name': 'Diploma in Information Communication Technology', 'level': 'diploma', 'category': 'Information Technology & Computing'},
            {'name': 'Higher Diploma in Information Communication Technology', 'level': 'higher_diploma', 'category': 'Information Technology & Computing'},
            {'name': 'Diploma in Cybersecurity', 'level': 'diploma', 'category': 'Information Technology & Computing'},
            {'name': 'Higher Diploma in Cybersecurity', 'level': 'higher_diploma', 'category': 'Information Technology & Computing'},
            {'name': 'Diploma in Database Management', 'level': 'diploma', 'category': 'Information Technology & Computing'},
            
            # ENGINEERING & TECHNICAL
            {'name': 'Certificate in Civil Engineering', 'level': 'certificate', 'category': 'Engineering & Technical'},
            {'name': 'Diploma in Civil Engineering', 'level': 'diploma', 'category': 'Engineering & Technical'},
            {'name': 'Higher Diploma in Civil Engineering', 'level': 'higher_diploma', 'category': 'Engineering & Technical'},
            {'name': 'Certificate in Electrical Engineering', 'level': 'certificate', 'category': 'Engineering & Technical'},
            {'name': 'Diploma in Electrical Engineering', 'level': 'diploma', 'category': 'Engineering & Technical'},
            {'name': 'Higher Diploma in Electrical Engineering', 'level': 'higher_diploma', 'category': 'Engineering & Technical'},
            {'name': 'Certificate in Mechanical Engineering', 'level': 'certificate', 'category': 'Engineering & Technical'},
            {'name': 'Diploma in Mechanical Engineering', 'level': 'diploma', 'category': 'Engineering & Technical'},
            {'name': 'Higher Diploma in Mechanical Engineering', 'level': 'higher_diploma', 'category': 'Engineering & Technical'},
            {'name': 'Certificate in Automotive Engineering', 'level': 'certificate', 'category': 'Engineering & Technical'},
            {'name': 'Diploma in Automotive Engineering', 'level': 'diploma', 'category': 'Engineering & Technical'},
            {'name': 'Certificate in Building and Construction', 'level': 'certificate', 'category': 'Engineering & Technical'},
            {'name': 'Diploma in Building and Construction', 'level': 'diploma', 'category': 'Engineering & Technical'},
            {'name': 'Diploma in Architecture', 'level': 'diploma', 'category': 'Engineering & Technical'},
            {'name': 'Higher Diploma in Architecture', 'level': 'higher_diploma', 'category': 'Engineering & Technical'},
            {'name': 'Certificate in Surveying', 'level': 'certificate', 'category': 'Engineering & Technical'},
            {'name': 'Diploma in Surveying', 'level': 'diploma', 'category': 'Engineering & Technical'},
            {'name': 'Diploma in Telecommunication Engineering', 'level': 'diploma', 'category': 'Engineering & Technical'},
            {'name': 'Higher Diploma in Telecommunication Engineering', 'level': 'higher_diploma', 'category': 'Engineering & Technical'},
            
            # HEALTH SCIENCES
            {'name': 'Certificate in Nursing', 'level': 'certificate', 'category': 'Health Sciences'},
            {'name': 'Diploma in Nursing', 'level': 'diploma', 'category': 'Health Sciences'},
            {'name': 'Higher Diploma in Nursing', 'level': 'higher_diploma', 'category': 'Health Sciences'},
            {'name': 'Diploma in Clinical Medicine', 'level': 'diploma', 'category': 'Health Sciences'},
            {'name': 'Higher Diploma in Clinical Medicine', 'level': 'higher_diploma', 'category': 'Health Sciences'},
            {'name': 'Diploma in Pharmacy', 'level': 'diploma', 'category': 'Health Sciences'},
            {'name': 'Higher Diploma in Pharmacy', 'level': 'higher_diploma', 'category': 'Health Sciences'},
            {'name': 'Diploma in Public Health', 'level': 'diploma', 'category': 'Health Sciences'},
            {'name': 'Higher Diploma in Public Health', 'level': 'higher_diploma', 'category': 'Health Sciences'},
            {'name': 'Certificate in Medical Laboratory Technology', 'level': 'certificate', 'category': 'Health Sciences'},
            {'name': 'Diploma in Medical Laboratory Technology', 'level': 'diploma', 'category': 'Health Sciences'},
            {'name': 'Certificate in Community Health', 'level': 'certificate', 'category': 'Health Sciences'},
            {'name': 'Diploma in Community Health', 'level': 'diploma', 'category': 'Health Sciences'},
            {'name': 'Certificate in Health Records and Information', 'level': 'certificate', 'category': 'Health Sciences'},
            {'name': 'Diploma in Health Records and Information', 'level': 'diploma', 'category': 'Health Sciences'},
            {'name': 'Diploma in Nutrition and Dietetics', 'level': 'diploma', 'category': 'Health Sciences'},
            
            # HOSPITALITY & TOURISM
            {'name': 'Certificate in Hospitality Management', 'level': 'certificate', 'category': 'Hospitality & Tourism'},
            {'name': 'Diploma in Hospitality Management', 'level': 'diploma', 'category': 'Hospitality & Tourism'},
            {'name': 'Higher Diploma in Hospitality Management', 'level': 'higher_diploma', 'category': 'Hospitality & Tourism'},
            {'name': 'Certificate in Tourism Management', 'level': 'certificate', 'category': 'Hospitality & Tourism'},
            {'name': 'Diploma in Tourism Management', 'level': 'diploma', 'category': 'Hospitality & Tourism'},
            {'name': 'Higher Diploma in Tourism Management', 'level': 'higher_diploma', 'category': 'Hospitality & Tourism'},
            {'name': 'Certificate in Hotel and Restaurant Management', 'level': 'certificate', 'category': 'Hospitality & Tourism'},
            {'name': 'Diploma in Hotel and Restaurant Management', 'level': 'diploma', 'category': 'Hospitality & Tourism'},
            {'name': 'Certificate in Culinary Arts', 'level': 'certificate', 'category': 'Hospitality & Tourism'},
            {'name': 'Diploma in Culinary Arts', 'level': 'diploma', 'category': 'Hospitality & Tourism'},
            {'name': 'Certificate in Travel and Tourism', 'level': 'certificate', 'category': 'Hospitality & Tourism'},
            {'name': 'Diploma in Travel and Tourism', 'level': 'diploma', 'category': 'Hospitality & Tourism'},
            
            # EDUCATION
            {'name': 'Diploma in Education (Arts)', 'level': 'diploma', 'category': 'Education'},
            {'name': 'Higher Diploma in Education (Arts)', 'level': 'higher_diploma', 'category': 'Education'},
            {'name': 'Diploma in Education (Science)', 'level': 'diploma', 'category': 'Education'},
            {'name': 'Higher Diploma in Education (Science)', 'level': 'higher_diploma', 'category': 'Education'},
            {'name': 'Certificate in Early Childhood Development', 'level': 'certificate', 'category': 'Education'},
            {'name': 'Diploma in Early Childhood Development', 'level': 'diploma', 'category': 'Education'},
            {'name': 'Diploma in Special Needs Education', 'level': 'diploma', 'category': 'Education'},
            
            # AGRICULTURE & ENVIRONMENTAL
            {'name': 'Certificate in Agricultural Technology', 'level': 'certificate', 'category': 'Agriculture & Environmental'},
            {'name': 'Diploma in Agricultural Technology', 'level': 'diploma', 'category': 'Agriculture & Environmental'},
            {'name': 'Higher Diploma in Agricultural Technology', 'level': 'higher_diploma', 'category': 'Agriculture & Environmental'},
            {'name': 'Diploma in Agribusiness Management', 'level': 'diploma', 'category': 'Agriculture & Environmental'},
            {'name': 'Higher Diploma in Agribusiness Management', 'level': 'higher_diploma', 'category': 'Agriculture & Environmental'},
            {'name': 'Certificate in Animal Health and Production', 'level': 'certificate', 'category': 'Agriculture & Environmental'},
            {'name': 'Diploma in Animal Health and Production', 'level': 'diploma', 'category': 'Agriculture & Environmental'},
            {'name': 'Certificate in Horticulture', 'level': 'certificate', 'category': 'Agriculture & Environmental'},
            {'name': 'Diploma in Horticulture', 'level': 'diploma', 'category': 'Agriculture & Environmental'},
            {'name': 'Diploma in Environmental Science', 'level': 'diploma', 'category': 'Agriculture & Environmental'},
            {'name': 'Higher Diploma in Environmental Science', 'level': 'higher_diploma', 'category': 'Agriculture & Environmental'},
            {'name': 'Diploma in Wildlife Management', 'level': 'diploma', 'category': 'Agriculture & Environmental'},
            
            # MEDIA & COMMUNICATION
            {'name': 'Diploma in Journalism and Mass Communication', 'level': 'diploma', 'category': 'Media & Communication'},
            {'name': 'Higher Diploma in Journalism and Mass Communication', 'level': 'higher_diploma', 'category': 'Media & Communication'},
            {'name': 'Diploma in Public Relations', 'level': 'diploma', 'category': 'Media & Communication'},
            {'name': 'Higher Diploma in Public Relations', 'level': 'higher_diploma', 'category': 'Media & Communication'},
            {'name': 'Diploma in Film Production', 'level': 'diploma', 'category': 'Media & Communication'},
            {'name': 'Certificate in Broadcasting', 'level': 'certificate', 'category': 'Media & Communication'},
            {'name': 'Diploma in Broadcasting', 'level': 'diploma', 'category': 'Media & Communication'},
            
            # SOCIAL SCIENCES
            {'name': 'Diploma in Social Work', 'level': 'diploma', 'category': 'Social Sciences'},
            {'name': 'Higher Diploma in Social Work', 'level': 'higher_diploma', 'category': 'Social Sciences'},
            {'name': 'Certificate in Community Development', 'level': 'certificate', 'category': 'Social Sciences'},
            {'name': 'Diploma in Community Development', 'level': 'diploma', 'category': 'Social Sciences'},
            {'name': 'Diploma in Counselling Psychology', 'level': 'diploma', 'category': 'Social Sciences'},
            {'name': 'Higher Diploma in Counselling Psychology', 'level': 'higher_diploma', 'category': 'Social Sciences'},
            {'name': 'Diploma in Criminology and Security Studies', 'level': 'diploma', 'category': 'Social Sciences'},
            
            # CREATIVE ARTS & DESIGN
            {'name': 'Certificate in Graphic Design', 'level': 'certificate', 'category': 'Creative Arts & Design'},
            {'name': 'Diploma in Graphic Design', 'level': 'diploma', 'category': 'Creative Arts & Design'},
            {'name': 'Certificate in Fashion Design', 'level': 'certificate', 'category': 'Creative Arts & Design'},
            {'name': 'Diploma in Fashion Design', 'level': 'diploma', 'category': 'Creative Arts & Design'},
            {'name': 'Diploma in Interior Design', 'level': 'diploma', 'category': 'Creative Arts & Design'},
            {'name': 'Diploma in Fine Arts', 'level': 'diploma', 'category': 'Creative Arts & Design'},
            
            # OTHER PROFESSIONAL COURSES
            {'name': 'Certificate in Secretarial Studies', 'level': 'certificate', 'category': 'Other Professional Courses'},
            {'name': 'Diploma in Secretarial Studies', 'level': 'diploma', 'category': 'Other Professional Courses'},
            {'name': 'Certificate in Library and Information Science', 'level': 'certificate', 'category': 'Other Professional Courses'},
            {'name': 'Diploma in Library and Information Science', 'level': 'diploma', 'category': 'Other Professional Courses'},
            {'name': 'Diploma in Archival Studies', 'level': 'diploma', 'category': 'Other Professional Courses'},
            {'name': 'Diploma in Logistics and Transport Management', 'level': 'diploma', 'category': 'Other Professional Courses'},
        ]
        
        created_count = 0
        skipped_count = 0
        
        for course_data in courses_data:
            course, created = GlobalCourse.objects.get_or_create(
                name=course_data['name'],
                defaults={
                    'level': course_data['level'],
                    'category': course_data['category']
                }
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'[+] Created: {course_data["name"]}')
                )
            else:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(f'[-] Skipped (already exists): {course_data["name"]}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n\nSummary: {created_count} courses created, {skipped_count} courses already existed'
            )
        )

