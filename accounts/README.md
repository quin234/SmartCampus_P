# Accounts & Finance Module

A comprehensive finance management system for Kenyan colleges and universities, integrated into the SmartCampus platform.

## Features

### Core Functionality

1. **Term Management**
   - Create and manage academic terms/semesters
   - Set active term (only one active at a time)
   - Track academic years (format: YYYY/YYYY)

2. **Fee Structure**
   - Define fees per course per semester
   - Multiple fee types (Tuition, Registration, Library, Examination, etc.)
   - Flexible fee structure management with versioning

3. **Automatic Fee Calculation**
   - Fees are automatically calculated based on student's course and current semester
   - Cumulative calculation: sums all fees from semester 1 to current semester
   - No manual invoice creation required
   - Real-time fee calculation based on fee structures

4. **Payment Tracking**
   - Record payments with multiple methods (Cash, MPesa, Bank Transfer, Scholarship, etc.)
   - Automatic receipt number generation
   - Payments recorded directly against students
   - Scholarship payments treated as normal payments

5. **Reports**
   - Balance Report: Shows expected fees (up to current semester), total paid, and outstanding balance for all students
   - Debtors Report: Students with outstanding balances
   - Payments by Term: Financial summary grouped by term

## Database Schema

### Tables

1. **departments** - College departments
2. **terms** - Academic terms/semesters
3. **fee_structures** - Fee definitions per course per semester
4. **payments** - Payment records

### Key Relationships

- Terms → Fee Structures (One-to-Many)
- Courses → Fee Structures (One-to-Many)
- Students → Payments (One-to-Many)

## Fee Calculation

The system automatically calculates expected fees for each student:

1. **Get Student's Current Semester**: Based on year of study and current semester
2. **Calculate Expected Fees**: Sum all fee structures from semester 1 to current semester for the student's course
3. **Calculate Balance**: Expected Fees - Total Payments

```
Expected Fees = SUM(Fee Structures for Semesters 1 to Current Semester)
Outstanding Balance = Expected Fees - SUM(All Payments)
```

Fees are calculated dynamically based on:
- Student's course
- Student's current semester number
- Active fee structures for that course and semester range

## Scholarship Handling

Scholarships are recorded as normal payments with `payment_method='scholarship'`. No separate tracking is required - they are included in all payment calculations and reports.

## Usage

### Accessing the Module

1. Login as College Admin
2. Navigate to `/accounts/dashboard/`
3. Use the sidebar to access different sections

### Setting Up Fee Structure

1. Go to **Fee Structure** → **Create Fee Structure**
2. Select course and semester number
3. Enter fee type and amount
4. Set effective dates
5. Save

Fees are automatically calculated for students based on their course and current semester.

### Recording a Payment

1. Go to **Payments** → **Record Payment**
2. Select student
3. Enter amount and payment method
4. Add transaction code (MPesa code, cheque number, etc.)
5. Save

Payments are recorded directly against the student and automatically reflected in balance calculations.

### Viewing Student Balances

1. Go to **Reports** → **Balance Report**
2. View all students with their:
   - Expected fees (up to current semester)
   - Total payments made
   - Outstanding balance

## Integration

The accounts app is fully integrated with the existing SmartCampus system:

- Uses existing `College`, `Student`, and `CollegeCourse` models
- Respects college-level data isolation
- Uses existing authentication and authorization
- Follows the same UI/UX patterns

## URL Structure

- `/accounts/dashboard/` - Dashboard
- `/accounts/terms/` - Terms management
- `/accounts/fee-structure/` - Fee structure
- `/accounts/payments/` - Payment management
- `/accounts/reports/` - Financial reports

## Permissions

- **College Admin**: Full access to all accounts features
- **Lecturer**: No access (can be extended if needed)
- **Super Admin**: No access (uses superadmin interface)

## Student Portal

Students can view their fee information in their portal:
- Expected fees up to their current semester
- Total payments made
- Outstanding balance
- Payment history
- Semester-by-semester fee breakdown

## Future Enhancements

- Payment reminders
- Email notifications for outstanding balances
- Payment receipts PDF generation
- Financial analytics dashboard
- Export reports to Excel/PDF
- Payment plan support
- Refund management

