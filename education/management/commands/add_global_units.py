"""
Django management command to add common Kenyan college units to GlobalUnit database
"""
from django.core.management.base import BaseCommand
from education.models import GlobalUnit


class Command(BaseCommand):
    help = 'Adds common Kenyan college units to the GlobalUnit database'

    def handle(self, *args, **options):
        units_data = [
            # COMMON/GENERAL EDUCATION UNITS
            {'name': 'Communication Skills', 'code': 'CCS 001'},
            {'name': 'Fundamentals of Development and Their Applications in Kenya', 'code': 'CCS 002'},
            {'name': 'Human Health', 'code': 'CCS 003'},
            {'name': 'Law in Society', 'code': 'CCS 004'},
            {'name': 'Environmental Science', 'code': 'CCS 005'},
            {'name': 'Chemistry and Its Applications', 'code': 'CCS 006'},
            {'name': 'Science and Technology in Development', 'code': 'CCS 007'},
            {'name': 'Elements of Philosophy', 'code': 'CCS 008'},
            {'name': 'Elements of Economics', 'code': 'CCS 009'},
            {'name': 'HIV & AIDS', 'code': 'CCS 010'},
            {'name': 'National Cohesion, Values, and Principles of Good Governance', 'code': 'CCS 011'},
            {'name': 'Entrepreneurship Education', 'code': 'ENT 101'},
            {'name': 'Life Skills', 'code': 'LSK 101'},
            {'name': 'Civic Education', 'code': 'CVE 101'},
            
            # MATHEMATICS & STATISTICS
            {'name': 'Mathematics', 'code': 'MAT 101'},
            {'name': 'Business Mathematics', 'code': 'BMAT 101'},
            {'name': 'Calculus', 'code': 'MAT 102'},
            {'name': 'Statistics', 'code': 'STA 101'},
            {'name': 'Business Statistics', 'code': 'BSTA 101'},
            {'name': 'Quantitative Methods', 'code': 'QTM 101'},
            {'name': 'Discrete Mathematics', 'code': 'DMAT 201'},
            
            # BUSINESS & COMMERCE UNITS
            {'name': 'Introduction to Business', 'code': 'BUS 101'},
            {'name': 'Business Management', 'code': 'BMG 101'},
            {'name': 'Principles of Management', 'code': 'POM 101'},
            {'name': 'Organizational Behavior', 'code': 'OB 201'},
            {'name': 'Strategic Management', 'code': 'SMG 301'},
            {'name': 'Financial Accounting', 'code': 'FAC 101'},
            {'name': 'Cost Accounting', 'code': 'CAC 201'},
            {'name': 'Management Accounting', 'code': 'MAC 201'},
            {'name': 'Financial Management', 'code': 'FMG 201'},
            {'name': 'Corporate Finance', 'code': 'CF 301'},
            {'name': 'Principles of Marketing', 'code': 'POMK 101'},
            {'name': 'Marketing Management', 'code': 'MMG 201'},
            {'name': 'Consumer Behavior', 'code': 'CB 201'},
            {'name': 'Sales Management', 'code': 'SALM 201'},
            {'name': 'Human Resource Management', 'code': 'HRM 201'},
            {'name': 'Recruitment and Selection', 'code': 'RAS 201'},
            {'name': 'Training and Development', 'code': 'TAD 201'},
            {'name': 'Compensation Management', 'code': 'CM 301'},
            {'name': 'Business Law', 'code': 'BLW 201'},
            {'name': 'Company Law', 'code': 'CLW 301'},
            {'name': 'Business Ethics', 'code': 'BET 201'},
            {'name': 'Operations Management', 'code': 'OM 201'},
            {'name': 'Supply Chain Management', 'code': 'SCM 201'},
            {'name': 'Procurement Management', 'code': 'PCM 201'},
            {'name': 'Project Management', 'code': 'PJM 201'},
            {'name': 'Business Research Methods', 'code': 'BRM 201'},
            {'name': 'Business Communication', 'code': 'BCM 101'},
            {'name': 'Office Administration', 'code': 'OAD 101'},
            {'name': 'Secretarial Practice', 'code': 'SP 101'},
            {'name': 'Banking Operations', 'code': 'BOP 201'},
            {'name': 'Banking and Finance', 'code': 'BAF 201'},
            {'name': 'Insurance Principles', 'code': 'INSP 201'},
            {'name': 'Cooperative Management', 'code': 'COM 201'},
            {'name': 'Microeconomics', 'code': 'MICRO 201'},
            {'name': 'Macroeconomics', 'code': 'MACRO 201'},
            
            # INFORMATION TECHNOLOGY & COMPUTING
            {'name': 'Introduction to Information Technology', 'code': 'IT 101'},
            {'name': 'Computer Fundamentals', 'code': 'COMF 101'},
            {'name': 'Introduction to Computing', 'code': 'IC 101'},
            {'name': 'Computer Applications', 'code': 'CA 101'},
            {'name': 'Microsoft Office Applications', 'code': 'MOA 101'},
            {'name': 'Introduction to Programming', 'code': 'IPROG 101'},
            {'name': 'Programming Fundamentals', 'code': 'PF 101'},
            {'name': 'Object Oriented Programming', 'code': 'OOP 201'},
            {'name': 'Data Structures and Algorithms', 'code': 'DSA 201'},
            {'name': 'Database Management Systems', 'code': 'DBMS 201'},
            {'name': 'Database Design', 'code': 'DBD 201'},
            {'name': 'SQL Programming', 'code': 'SQL 201'},
            {'name': 'Web Development', 'code': 'WD 201'},
            {'name': 'Web Programming', 'code': 'WP 201'},
            {'name': 'HTML and CSS', 'code': 'HC 101'},
            {'name': 'JavaScript Programming', 'code': 'JS 201'},
            {'name': 'PHP Programming', 'code': 'PHP 201'},
            {'name': 'Java Programming', 'code': 'JAVA 201'},
            {'name': 'Python Programming', 'code': 'PY 201'},
            {'name': 'C++ Programming', 'code': 'CPP 201'},
            {'name': 'C# Programming', 'code': 'CSH 201'},
            {'name': 'Software Engineering', 'code': 'SE 201'},
            {'name': 'System Analysis and Design', 'code': 'SAD 201'},
            {'name': 'Software Development Life Cycle', 'code': 'SDLC 201'},
            {'name': 'Computer Networks', 'code': 'CN 201'},
            {'name': 'Network Administration', 'code': 'NA 201'},
            {'name': 'Network Security', 'code': 'NS 301'},
            {'name': 'Cybersecurity Fundamentals', 'code': 'CSF 201'},
            {'name': 'Information Security', 'code': 'IS 301'},
            {'name': 'Operating Systems', 'code': 'OS 201'},
            {'name': 'Linux Administration', 'code': 'LA 201'},
            {'name': 'Computer Hardware', 'code': 'CH 101'},
            {'name': 'Computer Maintenance', 'code': 'COMPM 201'},
            {'name': 'Multimedia Systems', 'code': 'MS 201'},
            {'name': 'Graphics Design', 'code': 'GRD 201'},
            {'name': 'Mobile Application Development', 'code': 'MAD 301'},
            {'name': 'E-Commerce', 'code': 'ECOMM 201'},
            {'name': 'Information Systems', 'code': 'INSYS 201'},
            {'name': 'Management Information Systems', 'code': 'MIS 201'},
            {'name': 'Data Communication', 'code': 'DC 201'},
            {'name': 'Internet Technologies', 'code': 'IT 201'},
            {'name': 'Cloud Computing', 'code': 'CC 301'},
            
            # ENGINEERING UNITS
            {'name': 'Engineering Mathematics', 'code': 'EM 101'},
            {'name': 'Engineering Physics', 'code': 'EP 101'},
            {'name': 'Engineering Chemistry', 'code': 'ENGCH 101'},
            {'name': 'Engineering Drawing', 'code': 'ED 101'},
            {'name': 'Technical Drawing', 'code': 'TECD 101'},
            {'name': 'Workshop Technology', 'code': 'WT 101'},
            {'name': 'Engineering Materials', 'code': 'EMAT 201'},
            {'name': 'Strength of Materials', 'code': 'STMAT 201'},
            {'name': 'Thermodynamics', 'code': 'THERM 201'},
            {'name': 'Fluid Mechanics', 'code': 'FLUID 201'},
            {'name': 'Electrical Circuits', 'code': 'ELEC 201'},
            {'name': 'Digital Electronics', 'code': 'DE 201'},
            {'name': 'Analog Electronics', 'code': 'AE 201'},
            {'name': 'Electrical Machines', 'code': 'ELM 201'},
            {'name': 'Power Systems', 'code': 'PS 301'},
            {'name': 'Control Systems', 'code': 'CONTS 301'},
            {'name': 'Structural Analysis', 'code': 'SA 201'},
            {'name': 'Reinforced Concrete Design', 'code': 'RCD 301'},
            {'name': 'Steel Structures', 'code': 'STST 301'},
            {'name': 'Surveying', 'code': 'SUR 201'},
            {'name': 'Highway Engineering', 'code': 'HE 301'},
            {'name': 'Water Supply Engineering', 'code': 'WSE 301'},
            {'name': 'Waste Water Engineering', 'code': 'WWE 301'},
            {'name': 'Building Construction', 'code': 'BC 201'},
            {'name': 'Construction Management', 'code': 'CONM 301'},
            {'name': 'AutoCAD', 'code': 'CAD 201'},
            {'name': 'Mechanical Drawing', 'code': 'MD 201'},
            {'name': 'Machine Design', 'code': 'MCHD 301'},
            {'name': 'Internal Combustion Engines', 'code': 'ICE 301'},
            {'name': 'Automotive Technology', 'code': 'AT 201'},
            
            # HEALTH SCIENCES UNITS
            {'name': 'Human Anatomy', 'code': 'ANA 101'},
            {'name': 'Human Physiology', 'code': 'PHY 101'},
            {'name': 'Medical Biochemistry', 'code': 'MB 201'},
            {'name': 'Pathology', 'code': 'PAT 201'},
            {'name': 'Pharmacology', 'code': 'PHM 201'},
            {'name': 'Microbiology', 'code': 'MICROB 201'},
            {'name': 'Parasitology', 'code': 'PAR 201'},
            {'name': 'Immunology', 'code': 'IMM 201'},
            {'name': 'Nursing Fundamentals', 'code': 'NF 101'},
            {'name': 'Medical-Surgical Nursing', 'code': 'MSN 201'},
            {'name': 'Maternal and Child Health', 'code': 'MCH 201'},
            {'name': 'Community Health Nursing', 'code': 'CHN 201'},
            {'name': 'Mental Health Nursing', 'code': 'MHN 201'},
            {'name': 'Health Assessment', 'code': 'HA 201'},
            {'name': 'Clinical Medicine', 'code': 'CLMED 201'},
            {'name': 'Public Health', 'code': 'PH 201'},
            {'name': 'Epidemiology', 'code': 'EPI 201'},
            {'name': 'Health Education', 'code': 'HEDU 201'},
            {'name': 'Nutrition', 'code': 'NUT 101'},
            {'name': 'Dietetics', 'code': 'DIE 201'},
            {'name': 'Health Records Management', 'code': 'HREC 201'},
            {'name': 'Medical Laboratory Techniques', 'code': 'MLT 201'},
            {'name': 'Clinical Chemistry', 'code': 'CLCH 201'},
            {'name': 'Hematology', 'code': 'HEM 201'},
            {'name': 'Medical Ethics', 'code': 'ME 201'},
            
            # HOSPITALITY & TOURISM UNITS
            {'name': 'Introduction to Hospitality Industry', 'code': 'IHI 101'},
            {'name': 'Food and Beverage Service', 'code': 'FBS 101'},
            {'name': 'Food Production', 'code': 'FP 101'},
            {'name': 'Culinary Arts', 'code': 'CA 201'},
            {'name': 'Bakery and Pastry', 'code': 'BP 201'},
            {'name': 'Menu Planning', 'code': 'MP 201'},
            {'name': 'Food Safety and Hygiene', 'code': 'FSH 101'},
            {'name': 'Housekeeping Operations', 'code': 'HO 101'},
            {'name': 'Front Office Operations', 'code': 'FOO 101'},
            {'name': 'Hotel Management', 'code': 'HM 201'},
            {'name': 'Restaurant Management', 'code': 'RM 201'},
            {'name': 'Introduction to Tourism', 'code': 'ITOUR 101'},
            {'name': 'Tourism Geography', 'code': 'TGEO 201'},
            {'name': 'Travel and Tour Operations', 'code': 'TTO 201'},
            {'name': 'Tour Guiding', 'code': 'TGUID 201'},
            {'name': 'Event Management', 'code': 'EVENT 201'},
            {'name': 'Customer Service', 'code': 'CUS 101'},
            {'name': 'Hospitality Marketing', 'code': 'HMKT 201'},
            
            # EDUCATION UNITS
            {'name': 'Introduction to Education', 'code': 'IE 101'},
            {'name': 'Educational Psychology', 'code': 'EDPSY 201'},
            {'name': 'Curriculum Development', 'code': 'CURD 201'},
            {'name': 'Teaching Methods', 'code': 'TCHM 201'},
            {'name': 'Educational Assessment', 'code': 'EA 201'},
            {'name': 'Classroom Management', 'code': 'CLRM 201'},
            {'name': 'Educational Technology', 'code': 'EDTECH 201'},
            {'name': 'History of Education', 'code': 'HEDU 201'},
            {'name': 'Philosophy of Education', 'code': 'POE 201'},
            {'name': 'Sociology of Education', 'code': 'SOE 201'},
            {'name': 'Early Childhood Development', 'code': 'ECD 201'},
            {'name': 'Special Needs Education', 'code': 'SNE 201'},
            {'name': 'Guidance and Counselling', 'code': 'GC 201'},
            
            # AGRICULTURE UNITS
            {'name': 'Introduction to Agriculture', 'code': 'IA 101'},
            {'name': 'Crop Production', 'code': 'CP 101'},
            {'name': 'Animal Production', 'code': 'AP 101'},
            {'name': 'Soil Science', 'code': 'SOIL 201'},
            {'name': 'Agricultural Economics', 'code': 'AGEC 201'},
            {'name': 'Farm Management', 'code': 'FARM 201'},
            {'name': 'Agricultural Extension', 'code': 'AEX 201'},
            {'name': 'Agribusiness', 'code': 'AGB 201'},
            {'name': 'Horticulture', 'code': 'HORT 201'},
            {'name': 'Animal Health', 'code': 'ANH 201'},
            {'name': 'Veterinary Science', 'code': 'VS 201'},
            {'name': 'Agricultural Engineering', 'code': 'AGE 201'},
            {'name': 'Agricultural Marketing', 'code': 'AGM 201'},
            {'name': 'Food Security', 'code': 'FOSEC 201'},
            {'name': 'Environmental Conservation', 'code': 'ENVC 201'},
            
            # MEDIA & COMMUNICATION UNITS
            {'name': 'Introduction to Journalism', 'code': 'IJ 101'},
            {'name': 'News Writing and Reporting', 'code': 'NWR 201'},
            {'name': 'Feature Writing', 'code': 'FW 201'},
            {'name': 'Photojournalism', 'code': 'PJ 201'},
            {'name': 'Broadcast Journalism', 'code': 'BJ 201'},
            {'name': 'Radio Production', 'code': 'RP 201'},
            {'name': 'Television Production', 'code': 'TP 201'},
            {'name': 'Media Law and Ethics', 'code': 'MLE 201'},
            {'name': 'Public Relations', 'code': 'PR 201'},
            {'name': 'Advertising', 'code': 'ADV 201'},
            {'name': 'Media Research', 'code': 'MR 201'},
            {'name': 'Digital Media', 'code': 'DM 201'},
            {'name': 'Film Production', 'code': 'FP 201'},
            {'name': 'Script Writing', 'code': 'SW 201'},
            
            # SOCIAL SCIENCES UNITS
            {'name': 'Introduction to Sociology', 'code': 'ISOC 101'},
            {'name': 'Introduction to Psychology', 'code': 'IPSY 101'},
            {'name': 'Social Work Practice', 'code': 'SWP 201'},
            {'name': 'Community Development', 'code': 'COMD 201'},
            {'name': 'Counselling Skills', 'code': 'COUN 201'},
            {'name': 'Social Policy', 'code': 'SOP 201'},
            {'name': 'Criminology', 'code': 'CRI 201'},
            {'name': 'Security Studies', 'code': 'SECS 201'},
            {'name': 'Human Rights', 'code': 'HR 201'},
            {'name': 'Social Research Methods', 'code': 'SRM 201'},
            
            # CREATIVE ARTS & DESIGN UNITS
            {'name': 'Introduction to Art', 'code': 'IART 101'},
            {'name': 'Drawing and Painting', 'code': 'DP 101'},
            {'name': 'Graphic Design', 'code': 'GRD 201'},
            {'name': 'Fashion Design', 'code': 'FD 201'},
            {'name': 'Textile Design', 'code': 'TEXD 201'},
            {'name': 'Interior Design', 'code': 'ID 201'},
            {'name': 'Computer Aided Design', 'code': 'CAD 201'},
            {'name': 'Photography', 'code': 'PHO 201'},
            {'name': 'Art History', 'code': 'ARTH 201'},
            
            # OTHER PROFESSIONAL UNITS
            {'name': 'Library Science', 'code': 'LS 201'},
            {'name': 'Information Organization', 'code': 'IO 201'},
            {'name': 'Archival Management', 'code': 'ARCHM 201'},
            {'name': 'Records Management', 'code': 'RECM 201'},
            {'name': 'Logistics Management', 'code': 'LM 201'},
            {'name': 'Transport Management', 'code': 'TRANS 201'},
            {'name': 'Warehouse Management', 'code': 'WM 201'},
        ]
        
        created_count = 0
        skipped_count = 0
        
        for unit_data in units_data:
            unit, created = GlobalUnit.objects.get_or_create(
                code=unit_data['code'],
                defaults={
                    'name': unit_data['name']
                }
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'[+] Created: {unit_data["code"]} - {unit_data["name"]}')
                )
            else:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(f'[-] Skipped (already exists): {unit_data["code"]} - {unit_data["name"]}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n\nSummary: {created_count} units created, {skipped_count} units already existed'
            )
        )

