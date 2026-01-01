from django.test import TestCase
from django.contrib.auth import get_user_model
from education.models import College, CollegeCourse, Student
from .models import FeeStructure, Payment
from decimal import Decimal

User = get_user_model()


class AccountsModelsTestCase(TestCase):
    def setUp(self):
        """Set up test data"""
        self.college = College.objects.create(
            name="Test College",
            address="123 Test St",
            county="Nairobi",
            email="test@college.com",
            phone="1234567890",
            principal_name="Test Principal"
        )
        
        self.user = User.objects.create_user(
            username="testadmin",
            password="testpass123",
            role="college_admin",
            college=self.college
        )
        
        self.course = CollegeCourse.objects.create(
            college=self.college,
            name="Test Course",
            duration_years=3
        )
        
        self.student = Student.objects.create(
            college=self.college,
            admission_number="ST001",
            full_name="Test Student",
            course=self.course,
            year_of_study=1,
            gender="M",
            date_of_birth="2000-01-01"
        )
    
    def test_fee_structure_creation(self):
        """Test fee structure creation"""
        fee = FeeStructure.objects.create(
            college=self.college,
            course=self.course,
            semester_number=1,
            amount=Decimal('50000.00'),
            fee_type='tuition',
            is_active=True,
            is_current_version=True
        )
        self.assertEqual(fee.amount, Decimal('50000.00'))
    
    def test_payment_recording(self):
        """Test payment recording"""
        payment = Payment.objects.create(
            student=self.student,
            amount_paid=Decimal('30000.00'),
            payment_method='mpesa',
            transaction_code='MP123456',
            recorded_by=self.user
        )
        
        self.assertIsNotNone(payment.receipt_number)
        self.assertEqual(payment.amount_paid, Decimal('30000.00'))
        self.assertEqual(payment.payment_method, 'mpesa')

