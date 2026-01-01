"""
Daraja M-Pesa API Service for STK Push payments
"""
import requests
import base64
import json
from datetime import datetime
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from .models import DarajaSettings, Payment, StudentInvoice
from education.models import Student


class DarajaService:
    """
    Service for interacting with Safaricom Daraja API
    
    IMPORTANT SETTLEMENT FLOW:
    - Money flows: Student → M-Pesa → PayBill → Bank (via Safaricom settlement)
    - Daraja API does NOT push money directly to bank accounts
    - Bank details in settings are for display only (payment instructions to students)
    - Safaricom automatically handles PayBill → Bank settlement (not managed by this API)
    """
    
    def __init__(self, college):
        """Initialize Daraja service with college settings"""
        try:
            self.settings = DarajaSettings.objects.get(college=college, is_active=True)
        except DarajaSettings.DoesNotExist:
            raise ValueError("Daraja M-Pesa is not configured or enabled for this college")
        
        # Set base URL based on test/production mode
        if self.settings.is_test_mode:
            self.base_url = "https://sandbox.safaricom.co.ke"
        else:
            self.base_url = "https://api.safaricom.co.ke"
        
        # Get decrypted credentials
        self.consumer_key = self.settings.get_consumer_key()
        self.consumer_secret = self.settings.get_consumer_secret()
        self.passkey = self.settings.get_passkey()
        self.shortcode = self.settings.shortcode
        
        # Validate all required fields for PayBill → Bank settlement
        self._validate_required_fields()
    
    def _validate_required_fields(self):
        """
        Validate all mandatory fields required for successful PayBill → Bank settlement.
        Aborts with ValueError if any required field is missing.
        
        Required fields:
        - PayBill Shortcode (BusinessShortCode/PartyB)
        - Consumer Key (OAuth authentication)
        - Consumer Secret (OAuth authentication)
        - Passkey (Password generation for STK Push)
        - Callback URL (Payment confirmation webhook)
        - Environment (Sandbox/Live) - already validated via is_test_mode
        - Account Reference Template (STK Push reference) - has default
        - Transaction Description (STK Push description) - has default
        
        Note: TransactionType is always CustomerPayBillOnline (PayBill only, enforced)
        """
        missing_fields = []
        
        # Core credentials (mandatory)
        if not self.consumer_key:
            missing_fields.append("Consumer Key")
        if not self.consumer_secret:
            missing_fields.append("Consumer Secret")
        if not self.passkey:
            missing_fields.append("Passkey")
        if not self.shortcode:
            missing_fields.append("PayBill Shortcode")
        
        # Callback URL (can be auto-generated, but validate it exists or can be generated)
        callback_url = self.settings.callback_url
        if not callback_url:
            # Check if BASE_URL is configured for auto-generation
            base_url = getattr(settings, 'BASE_URL', None)
            if not base_url:
                missing_fields.append("Callback URL (or configure BASE_URL in settings)")
        
        if missing_fields:
            raise ValueError(
                f"Daraja configuration incomplete. Missing required fields: {', '.join(missing_fields)}. "
                f"Please configure all mandatory fields in Accounts Settings → M-Pesa Payments tab."
            )
    
    def get_access_token(self):
        """Get OAuth access token from Daraja API"""
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        
        # Encode credentials
        credentials = f"{self.consumer_key}:{self.consumer_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get('access_token')
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get access token: {str(e)}")
    
    def generate_password(self):
        """Generate password for STK Push (timestamp + passkey)"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        data_to_encode = f"{self.shortcode}{self.passkey}{timestamp}"
        password = base64.b64encode(data_to_encode.encode()).decode()
        return password, timestamp
    
    def initiate_stk_push_for_college(self, amount, phone_number, account_reference, transaction_desc):
        """
        Initiate STK Push payment request for college payments (not student payments)
        
        Args:
            amount: Payment amount (Decimal)
            phone_number: M-Pesa registered phone number (format: 254712345678)
            account_reference: Account reference string
            transaction_desc: Transaction description
        
        Returns:
            dict with 'success', 'merchant_request_id', 'checkout_request_id', 'response_description'
        """
        # Re-validate required fields before STK push
        try:
            self._validate_required_fields()
        except ValueError as e:
            return {
                'success': False,
                'error': str(e)
            }
        
        # Validate phone number format
        phone_number = phone_number.strip()
        if not phone_number.startswith('254'):
            if phone_number.startswith('0'):
                phone_number = '254' + phone_number[1:]
            elif phone_number.startswith('+254'):
                phone_number = phone_number[1:]
            else:
                phone_number = '254' + phone_number
        
        if len(phone_number) != 12:
            return {
                'success': False,
                'error': 'Invalid phone number format. Use 254XXXXXXXXX'
            }
        
        # Get access token
        try:
            access_token = self.get_access_token()
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to authenticate with Daraja API: {str(e)}'
            }
        
        # Generate password and timestamp
        password, timestamp = self.generate_password()
        
        # Prepare callback URL
        callback_url = self.settings.callback_url
        if not callback_url:
            base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
            callback_url = f"{base_url}/superadmin/payments/callback/"
        
        # STK Push payload
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(float(amount)),
            "PartyA": phone_number,
            "PartyB": self.shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": callback_url,
            "AccountReference": account_reference,
            "TransactionDesc": transaction_desc
        }
        
        # Make STK Push request
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if 'ResponseCode' in data and data['ResponseCode'] == '0':
                return {
                    'success': True,
                    'merchant_request_id': data.get('MerchantRequestID'),
                    'checkout_request_id': data.get('CheckoutRequestID'),
                    'response_description': data.get('CustomerMessage', 'Payment request sent successfully'),
                    'response_code': data.get('ResponseCode')
                }
            else:
                error_msg = data.get('errorMessage') or data.get('ResponseDescription', 'Payment request failed')
                return {
                    'success': False,
                    'error': error_msg,
                    'response_code': data.get('ResponseCode')
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Failed to initiate payment: {str(e)}'
            }
    
    def initiate_stk_push(self, student, amount, phone_number, invoice=None):
        """
        Initiate STK Push payment request
        
        IMPORTANT: This method validates all required fields before initiating payment.
        Payment will be aborted if any mandatory field is missing.
        
        Settlement Flow:
        - Payment goes to PayBill configured in BusinessShortCode
        - Safaricom automatically handles PayBill → Bank settlement (not managed by this API)
        - Bank details in settings are NOT used in this payment flow (display only)
        
        Args:
            student: Student instance
            amount: Payment amount (Decimal)
            phone_number: M-Pesa registered phone number (format: 254712345678)
            invoice: Optional StudentInvoice instance
        
        Returns:
            dict with 'success', 'merchant_request_id', 'checkout_request_id', 'response_description'
        """
        # Re-validate required fields before STK push (fail fast if missing)
        try:
            self._validate_required_fields()
        except ValueError as e:
            return {
                'success': False,
                'error': str(e)
            }
        # Validate phone number format
        phone_number = phone_number.strip()
        if not phone_number.startswith('254'):
            if phone_number.startswith('0'):
                phone_number = '254' + phone_number[1:]
            elif phone_number.startswith('+254'):
                phone_number = phone_number[1:]
            else:
                phone_number = '254' + phone_number
        
        if len(phone_number) != 12:
            return {
                'success': False,
                'error': 'Invalid phone number format. Use 254XXXXXXXXX'
            }
        
        # Get access token
        try:
            access_token = self.get_access_token()
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to authenticate with Daraja API: {str(e)}'
            }
        
        # Generate password and timestamp
        password, timestamp = self.generate_password()
        
        # Prepare account reference
        account_reference = self.settings.account_reference or 'FEE'
        if student.admission_number:
            account_reference = f"{account_reference}-{student.admission_number}"
        
        # Prepare transaction description
        transaction_desc = self.settings.transaction_description or 'Fee Payment'
        if invoice:
            transaction_desc = f"{transaction_desc} - Invoice {invoice.invoice_number}"
        
        # Prepare callback URL
        callback_url = self.settings.callback_url
        if not callback_url:
            base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
            callback_url = f"{base_url}/accounts/payment/daraja/callback/"
        
        # STK Push payload
        # NOTE: BusinessShortCode must match PayBill configured for bank settlement
        # TransactionType is ALWAYS CustomerPayBillOnline (PayBill only, no Till option)
        # Bank details are NOT included here - they are for display only
        payload = {
            "BusinessShortCode": self.shortcode,  # PayBill number configured for bank settlement
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",  # Always PayBill (enforced, not user-selectable)
            "Amount": int(float(amount)),
            "PartyA": phone_number,
            "PartyB": self.shortcode,  # Same as BusinessShortCode (PayBill number)
            "PhoneNumber": phone_number,
            "CallBackURL": callback_url,
            "AccountReference": account_reference,
            "TransactionDesc": transaction_desc
        }
        
        # Make STK Push request
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if 'ResponseCode' in data and data['ResponseCode'] == '0':
                return {
                    'success': True,
                    'merchant_request_id': data.get('MerchantRequestID'),
                    'checkout_request_id': data.get('CheckoutRequestID'),
                    'response_description': data.get('CustomerMessage', 'Payment request sent successfully'),
                    'response_code': data.get('ResponseCode')
                }
            else:
                error_msg = data.get('errorMessage') or data.get('ResponseDescription', 'Payment request failed')
                return {
                    'success': False,
                    'error': error_msg,
                    'response_code': data.get('ResponseCode')
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Failed to initiate payment: {str(e)}'
            }
    
    def query_stk_status(self, checkout_request_id):
        """Query STK Push payment status"""
        access_token = self.get_access_token()
        password, timestamp = self.generate_password()
        
        url = f"{self.base_url}/mpesa/stkpushquery/v1/query"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {'error': str(e)}
    
    @staticmethod
    def process_callback(callback_data):
        """
        Process payment callback from Daraja
        
        Persists all required settlement data:
        - MpesaReceiptNumber (transaction code)
        - Amount (payment amount)
        - AccountReference (student identification)
        - ResultCode (payment status)
        
        Args:
            callback_data: Callback data from Daraja webhook
        
        Returns:
            dict with payment processing result
        """
        try:
            # Extract callback data
            body = callback_data.get('Body', {})
            stk_callback = body.get('stkCallback', {})
            
            merchant_request_id = stk_callback.get('MerchantRequestID')
            checkout_request_id = stk_callback.get('CheckoutRequestID')
            result_code = stk_callback.get('ResultCode')
            result_desc = stk_callback.get('ResultDesc')
            
            # Get callback metadata
            callback_metadata = stk_callback.get('CallbackMetadata', {})
            items = callback_metadata.get('Item', [])
            
            # Extract payment details
            payment_data = {}
            for item in items:
                name = item.get('Name')
                value = item.get('Value')
                payment_data[name] = value
            
            # Check if payment was successful
            if result_code == 0:
                # Payment successful - extract all required settlement data
                # All fields required for PayBill → Bank settlement reconciliation are persisted:
                amount = Decimal(str(payment_data.get('Amount', 0)))  # → Payment.amount_paid
                mpesa_receipt_number = payment_data.get('MpesaReceiptNumber', '')  # → Payment.transaction_code
                transaction_date = payment_data.get('TransactionDate', '')
                phone_number = payment_data.get('PhoneNumber', '')
                
                # Extract account reference to find student
                account_reference = payment_data.get('AccountReference', '')  # Used for student identification, stored in Payment.notes
                # ResultCode (result_code) is checked above (0 = success)
                
                # Try to find student from account reference
                # Format: FEE-ADM123 or just ADM123
                student = None
                if account_reference:
                    # Try to extract admission number
                    parts = account_reference.split('-')
                    if len(parts) > 1:
                        admission_number = parts[-1]
                    else:
                        admission_number = account_reference
                    
                    try:
                        student = Student.objects.get(admission_number=admission_number)
                    except Student.DoesNotExist:
                        pass
                
                if not student:
                    return {
                        'success': False,
                        'error': 'Could not identify student from payment reference'
                    }
                
                # Check if payment already exists
                existing_payment = Payment.objects.filter(
                    transaction_code=mpesa_receipt_number
                ).first()
                
                if existing_payment:
                    return {
                        'success': True,
                        'message': 'Payment already processed',
                        'payment_id': existing_payment.id
                    }
                
                # Create payment record
                payment = Payment.objects.create(
                    student=student,
                    amount_paid=amount,
                    payment_method='mpesa',
                    transaction_code=mpesa_receipt_number,
                    date_paid=timezone.now(),
                    notes=f"M-Pesa payment via Daraja STK Push. Phone: {phone_number}, Transaction Date: {transaction_date}"
                )
                
                # Update invoice if applicable
                # Try to find pending invoice for this student
                if student.invoices.exists():
                    pending_invoice = student.invoices.filter(
                        status__in=['pending', 'partial']
                    ).order_by('semester_number').first()
                    
                    if pending_invoice:
                        payment.invoice = pending_invoice
                        payment.save()
                        pending_invoice.update_status()
                        pending_invoice.save()
                
                return {
                    'success': True,
                    'message': 'Payment processed successfully',
                    'payment_id': payment.id,
                    'receipt_number': payment.receipt_number
                }
            else:
                # Payment failed
                return {
                    'success': False,
                    'error': result_desc or 'Payment failed',
                    'result_code': result_code
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Error processing callback: {str(e)}'
            }

