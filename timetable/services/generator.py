"""
Timetable generation service
Automatically generates timetable entries with conflict prevention
"""
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q, Count
from django.db import transaction
from education.models import CollegeCourse, CollegeCourseUnit, CollegeUnit, CustomUser, Student
from timetable.models import TimetableRun, TimetableEntry, TimetableDay, TimeSlot, Classroom
from .validation import validate_timetable_run, ValidationError


class GenerationError(Exception):
    """Custom exception for generation errors"""
    def __init__(self, message, recommendations=None):
        self.message = message
        self.recommendations = recommendations or []
        super().__init__(self.message)


def generate_timetable(timetable_run):
    """
    Generate timetable entries for a TimetableRun.
    
    Algorithm:
    1. Validate prerequisites
    2. Get all units to schedule
    3. Get available days, time slots, and classrooms
    4. Distribute units evenly across days
    5. Assign time slots and classrooms avoiding conflicts
    6. Create TimetableEntry records
    7. Mark timetable as generated
    
    Args:
        timetable_run: TimetableRun instance
    
    Returns:
        dict: {
            'success': bool,
            'message': str,
            'entries_created': int,
            'recommendations': list (if failed)
        }
    """
    # Validate prerequisites first
    is_valid, validation_errors, recommendations = validate_timetable_run(timetable_run)
    if not is_valid:
        return {
            'success': False,
            'message': 'Validation failed. Please fix the following issues:',
            'errors': validation_errors,
            'entries_created': 0,
            'recommendations': recommendations if recommendations else validation_errors
        }
    
    try:
        with transaction.atomic():
            # Delete existing entries if regenerating
            TimetableEntry.objects.filter(timetable=timetable_run).delete()
            
            # Get all units to schedule
            units_to_schedule = get_units_to_schedule(timetable_run)
            
            if not units_to_schedule:
                # Determine the reason for no units
                if timetable_run.course:
                    # Check if course has active students
                    active_students = Student.objects.filter(
                        college=timetable_run.college,
                        course=timetable_run.course,
                        status='active'
                    ).count()
                    
                    if active_students == 0:
                        return {
                            'success': False,
                            'message': 'No units found to schedule.',
                            'errors': [f"Course '{timetable_run.course.name}' has no active students."],
                            'entries_created': 0,
                            'recommendations': [
                                f"Enroll active students to course '{timetable_run.course.name}' before generating timetable",
                                f"Or deactivate course '{timetable_run.course.name}' if it's no longer needed"
                            ]
                        }
                    else:
                        # Has students but no units
                        return {
                            'success': False,
                            'message': 'No units found to schedule.',
                            'errors': [f"Course '{timetable_run.course.name}' has enrolled students but no units assigned for semester {timetable_run.semester}."],
                            'entries_created': 0,
                            'recommendations': [
                                f"Assign units to course '{timetable_run.course.name}' for semester {timetable_run.semester} before generating timetable"
                            ]
                        }
                else:
                    # General timetable - check if any courses have students
                    courses_with_students = CollegeCourse.objects.filter(
                        college=timetable_run.college,
                        students__status='active'
                    ).distinct().count()
                    
                    if courses_with_students == 0:
                        return {
                            'success': False,
                            'message': 'No units found to schedule.',
                            'errors': ['No eligible courses found for timetable generation. All courses have zero active students.'],
                            'entries_created': 0,
                            'recommendations': [
                                'Enroll active students to courses before generating timetable',
                                'No eligible courses found for timetable generation'
                            ]
                        }
                    else:
                        return {
                            'success': False,
                            'message': 'No units found to schedule.',
                            'errors': ['No units found for courses with active students for the specified semester.'],
                            'entries_created': 0,
                            'recommendations': [
                                f'Assign units to courses with active students for semester {timetable_run.semester}',
                                'Ensure units have assigned lecturers'
                            ]
                        }
            
            # Get available resources
            days = list(TimetableDay.objects.all().order_by('order_index'))
            time_slots = list(TimeSlot.objects.all().order_by('start_time'))
            classrooms = list(Classroom.objects.filter(college=timetable_run.college))
            
            if not days or not time_slots or not classrooms:
                recommendations = []
                if not days:
                    recommendations.append('Add timetable days (Monday, Tuesday, etc.)')
                if not time_slots:
                    recommendations.append('Add more time slots')
                if not classrooms:
                    recommendations.append('Add more classrooms')
                
                return {
                    'success': False,
                    'message': 'Insufficient resources for timetable generation.',
                    'errors': ['Missing required resources.'],
                    'entries_created': 0,
                    'recommendations': recommendations
                }
            
            # Distribute units evenly across days
            units_by_day = distribute_units_across_days(units_to_schedule, days)
            
            # Generate entries
            entries_created = 0
            lecturer_load = {}  # Track lecturer assignments per day
            classroom_usage = {}  # Track classroom usage per day/time_slot
            
            for day, day_units in units_by_day.items():
                for unit_info in day_units:
                    unit = unit_info['unit']
                    course = unit_info['course']
                    lecturer = unit.assigned_lecturer
                    
                    if not lecturer:
                        continue  # Skip units without lecturers
                    
                    # Find available time slot and classroom
                    assignment = find_available_slot(
                        day=day,
                        time_slots=time_slots,
                        classrooms=classrooms,
                        lecturer=lecturer,
                        course=course,
                        lecturer_load=lecturer_load,
                        classroom_usage=classroom_usage,
                        timetable_run=timetable_run
                    )
                    
                    if not assignment:
                        # Generation failed - not enough resources
                        recommendations = analyze_failure_reasons(
                            units_to_schedule, days, time_slots, classrooms, lecturer_load
                        )
                        return {
                            'success': False,
                            'message': 'Failed to generate timetable. Insufficient resources or conflicts detected.',
                            'errors': ['Could not assign all units without conflicts.'],
                            'entries_created': entries_created,
                            'recommendations': recommendations
                        }
                    
                    # Create entry
                    entry = TimetableEntry.objects.create(
                        timetable=timetable_run,
                        day=day,
                        time_slot=assignment['time_slot'],
                        course=course,
                        unit=unit,
                        lecturer=lecturer,
                        classroom=assignment['classroom']
                    )
                    entries_created += 1
                    
                    # Update tracking
                    key = f"{day.id}_{assignment['time_slot'].id}"
                    lecturer_load.setdefault(lecturer.id, {}).setdefault(day.id, []).append(assignment['time_slot'].id)
                    classroom_usage.setdefault(day.id, {}).setdefault(assignment['time_slot'].id, assignment['classroom'].id)
            
            # Mark timetable as generated
            timetable_run.status = 'generated'
            timetable_run.generated_at = timezone.now()
            timetable_run.save()
            
            return {
                'success': True,
                'message': f'Timetable generated successfully. Created {entries_created} entries.',
                'entries_created': entries_created,
                'recommendations': []
            }
    
    except Exception as e:
        return {
            'success': False,
            'message': f'Generation failed: {str(e)}',
            'errors': [str(e)],
            'entries_created': 0,
            'recommendations': ['Please check the error message and try again.']
        }


def get_units_to_schedule(timetable_run):
    """
    Get all units that need to be scheduled for this timetable run.
    Only includes courses with active students (≥1 active student).
    Only includes courses that have at least one unit assigned.
    
    Returns:
        list: [{'unit': CollegeUnit, 'course': CollegeCourse}, ...]
    """
    units = []
    
    if timetable_run.course:
        # Course-specific timetable
        # Verify course has active students
        active_students_count = Student.objects.filter(
            college=timetable_run.college,
            course=timetable_run.course,
            status='active'
        ).count()
        
        if active_students_count == 0:
            # Course has no active students - return empty list
            return units
        
        # Get units for this course
        course_units = CollegeCourseUnit.objects.filter(
            course=timetable_run.course,
            college=timetable_run.college,
            semester=timetable_run.semester
        ).select_related('unit', 'course')
        
        # Verify course has units
        if course_units.count() == 0:
            # Course has students but no units - return empty list
            return units
        
        for course_unit in course_units:
            if course_unit.unit.assigned_lecturer:  # Only schedule units with lecturers
                units.append({
                    'unit': course_unit.unit,
                    'course': timetable_run.course
                })
    else:
        # General timetable - only courses with active students
        # Get courses that have at least one active student
        courses_with_students = CollegeCourse.objects.filter(
            college=timetable_run.college,
            students__status='active'
        ).distinct()
        
        for course in courses_with_students:
            # Double-check active students count for this course
            active_students_count = Student.objects.filter(
                college=timetable_run.college,
                course=course,
                status='active'
            ).count()
            
            if active_students_count == 0:
                # Skip courses without active students
                continue
            
            # Get units for this course
            course_units = CollegeCourseUnit.objects.filter(
                course=course,
                college=timetable_run.college,
                semester=timetable_run.semester
            ).select_related('unit', 'course')
            
            # Skip courses without units
            if course_units.count() == 0:
                continue
            
            for course_unit in course_units:
                if course_unit.unit.assigned_lecturer:  # Only schedule units with lecturers
                    units.append({
                        'unit': course_unit.unit,
                        'course': course
                    })
    
    return units


def distribute_units_across_days(units, days):
    """
    Distribute units evenly across available days.
    
    Args:
        units: List of unit info dicts
        days: List of TimetableDay objects
    
    Returns:
        dict: {TimetableDay: [unit_info, ...], ...}
    """
    if not days:
        return {}
    
    distribution = {day: [] for day in days}
    
    # Simple round-robin distribution
    for i, unit_info in enumerate(units):
        day_index = i % len(days)
        distribution[days[day_index]].append(unit_info)
    
    return distribution


def find_available_slot(day, time_slots, classrooms, lecturer, course, lecturer_load, classroom_usage, timetable_run):
    """
    Find an available time slot and classroom for a unit.
    Prevents:
    - Lecturer double booking
    - Classroom clashes
    - Same course overlapping
    
    Returns:
        dict: {'time_slot': TimeSlot, 'classroom': Classroom} or None
    """
    # Get lecturer's existing assignments for this day
    lecturer_slots = lecturer_load.get(lecturer.id, {}).get(day.id, [])
    
    # Try each time slot
    for time_slot in time_slots:
        # Skip if lecturer already booked at this time
        if time_slot.id in lecturer_slots:
            continue
        
        # Check for same course overlapping (prevent same course at same time)
        existing_entry = TimetableEntry.objects.filter(
            timetable=timetable_run,
            day=day,
            time_slot=time_slot,
            course=course
        ).first()
        
        if existing_entry:
            continue  # Same course already scheduled at this time
        
        # Try to find available classroom
        used_classrooms = classroom_usage.get(day.id, {}).get(time_slot.id, None)
        
        for classroom in classrooms:
            # Skip if classroom already used at this time
            if used_classrooms == classroom.id:
                continue
            
            # Check for classroom conflict in database
            existing_classroom_entry = TimetableEntry.objects.filter(
                timetable=timetable_run,
                day=day,
                time_slot=time_slot,
                classroom=classroom
            ).first()
            
            if existing_classroom_entry:
                continue  # Classroom already booked
            
            # Found available slot!
            return {
                'time_slot': time_slot,
                'classroom': classroom
            }
    
    return None  # No available slot found


def analyze_failure_reasons(units_to_schedule, days, time_slots, classrooms, lecturer_load):
    """
    Analyze why generation failed and provide recommendations.
    
    Returns:
        list: Recommendation messages
    """
    recommendations = []
    
    total_slots = len(days) * len(time_slots)
    total_units = len(units_to_schedule)
    
    if total_units > total_slots:
        recommendations.append(f"Too many units ({total_units}) for available time slots ({total_slots}). Add more time slots or reduce units.")
    
    if total_units > len(days) * len(classrooms):
        recommendations.append(f"Too many units ({total_units}) for available classrooms ({len(classrooms)}). Add more classrooms.")
    
    # Check lecturer overload
    lecturer_assignments = {}
    for lecturer_id, days_dict in lecturer_load.items():
        total = sum(len(slots) for slots in days_dict.values())
        lecturer_assignments[lecturer_id] = total
    
    overloaded_lecturers = [lid for lid, count in lecturer_assignments.items() if count > total_slots * 0.3]
    if overloaded_lecturers:
        lecturer_names = CustomUser.objects.filter(id__in=overloaded_lecturers).values_list('username', flat=True)
        recommendations.append(f"Lecturers overloaded: {', '.join(lecturer_names)}. Consider redistributing units or adding more lecturers.")
    
    if not recommendations:
        recommendations.append("Add more time slots")
        recommendations.append("Add more classrooms")
        recommendations.append("Consider scheduling some units across multiple weeks")
    
    return recommendations

