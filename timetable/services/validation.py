"""
Validation service for timetable generation
Validates prerequisites before generating a timetable
"""
from django.db.models import Q, Count
from education.models import College, CollegeCourse, CollegeUnit, CollegeCourseUnit, CustomUser, Student
from timetable.models import TimetableDay, TimeSlot, Classroom


class ValidationError(Exception):
    """Custom exception for validation errors"""
    def __init__(self, message, errors=None):
        self.message = message
        self.errors = errors or []
        super().__init__(self.message)


def validate_timetable_prerequisites(college, course=None, academic_year=None, semester=None):
    """
    Validate all prerequisites before generating a timetable.
    Includes student-aware validation: only courses with active students are eligible.
    Returns a tuple (is_valid, errors_list, recommendations_list)
    
    Args:
        college: College instance
        course: CollegeCourse instance (optional, for course-specific timetable)
        academic_year: Academic year string (optional)
        semester: Semester number (optional)
    
    Returns:
        tuple: (is_valid: bool, errors: list of error messages, recommendations: list of recommendation messages)
    """
    errors = []
    recommendations = []
    
    # 1. Validate days exist
    days_count = TimetableDay.objects.count()
    if days_count == 0:
        errors.append("No timetable days configured. Please add days (Monday, Tuesday, etc.) in the admin panel.")
    
    # 2. Validate time slots exist
    time_slots_count = TimeSlot.objects.count()
    if time_slots_count == 0:
        errors.append("No time slots configured. Please add time slots (e.g., 08:00-09:00) in the admin panel.")
    
    # 3. Validate classrooms exist for this college
    classrooms_count = Classroom.objects.filter(college=college).count()
    if classrooms_count == 0:
        errors.append(f"No classrooms configured for {college.name}. Please add classrooms in the admin panel.")
    
    # 4. Validate lecturers exist
    lecturers_count = CustomUser.objects.filter(college=college, role='lecturer').count()
    if lecturers_count == 0:
        errors.append(f"No lecturers found for {college.name}. Please add lecturers first.")
    
    # 5. Student-aware validation: Check for active students
    active_students_count = Student.objects.filter(college=college, status='active').count()
    if active_students_count == 0:
        errors.append(f"No active students found for {college.name}. Timetable generation requires at least one active student.")
        recommendations.append("Enroll active students before generating timetable")
        return False, errors, recommendations
    
    # 6. Validate courses with active students
    if course:
        # Validate specific course exists
        if not CollegeCourse.objects.filter(id=course.id, college=college).exists():
            errors.append(f"Course '{course.name}' not found for {college.name}.")
            return False, errors, recommendations
        
        # Check if course has active students
        active_students_in_course = Student.objects.filter(
            college=college,
            course=course,
            status='active'
        ).count()
        
        if active_students_in_course == 0:
            errors.append(f"Course '{course.name}' has no active students assigned.")
            recommendations.append(f"Deactivate course '{course.name}' or enroll active students")
            return False, errors, recommendations
        
        # Check if course has units
        course_units = CollegeCourseUnit.objects.filter(course=course, college=college)
        if semester:
            course_units = course_units.filter(semester=semester)
        
        if course_units.count() == 0:
            errors.append(f"Course '{course.name}' has enrolled students but no units assigned.")
            recommendations.append(f"Assign units to course '{course.name}' before generating timetable")
            return False, errors, recommendations
        
        # Validate each unit has a lecturer
        units_without_lecturers = []
        for course_unit in course_units:
            unit = course_unit.unit
            if not unit.assigned_lecturer:
                units_without_lecturers.append(unit.code)
        
        if units_without_lecturers:
            errors.append(
                f"The following units do not have assigned lecturers: {', '.join(units_without_lecturers)}. "
                f"Please assign lecturers to these units first."
            )
    else:
        # For general timetable, check all courses
        # Get courses with active students
        courses_with_students = CollegeCourse.objects.filter(
            college=college,
            students__status='active'
        ).distinct()
        
        if courses_with_students.count() == 0:
            errors.append(f"No eligible courses found for timetable generation. All courses have zero active students.")
            recommendations.append("Enroll active students to courses before generating timetable")
            return False, errors, recommendations
        
        courses_without_units = []
        courses_without_students = []
        units_without_lecturers = []
        eligible_courses = []
        
        # Check each course that has active students
        for course_obj in courses_with_students:
            active_students_count = Student.objects.filter(
                college=college,
                course=course_obj,
                status='active'
            ).count()
            
            if active_students_count == 0:
                courses_without_students.append(course_obj.name)
                continue
            
            course_units = CollegeCourseUnit.objects.filter(course=course_obj, college=college)
            if semester:
                course_units = course_units.filter(semester=semester)
            
            if course_units.count() == 0:
                courses_without_units.append(course_obj.name)
            else:
                # Check for units without lecturers
                has_units_without_lecturers = False
                for course_unit in course_units:
                    unit = course_unit.unit
                    if not unit.assigned_lecturer:
                        units_without_lecturers.append(f"{unit.code} ({course_obj.name})")
                        has_units_without_lecturers = True
                
                if not has_units_without_lecturers:
                    eligible_courses.append(course_obj.name)
        
        # Report errors for courses with students but no units
        if courses_without_units:
            for course_name in courses_without_units:
                errors.append(f"Course '{course_name}' has enrolled students but no units assigned.")
                recommendations.append(f"Assign units to course '{course_name}' before generating timetable")
        
        # Report courses without students (these will be excluded, but warn if they exist)
        all_courses = CollegeCourse.objects.filter(college=college)
        courses_without_any_students = [
            c.name for c in all_courses 
            if c not in courses_with_students
        ]
        if courses_without_any_students:
            recommendations.append(
                f"The following courses have no active students and will be excluded: {', '.join(courses_without_any_students[:5])}"
            )
        
        if units_without_lecturers:
            errors.append(
                f"The following units do not have assigned lecturers: {', '.join(units_without_lecturers[:10])}. "
                f"Please assign lecturers to these units first."
            )
        
        # If no eligible courses after filtering
        if not eligible_courses and not courses_without_units:
            errors.append("No eligible courses found for timetable generation.")
            recommendations.append("Ensure courses have both active students and assigned units with lecturers")
    
    return len(errors) == 0, errors, recommendations


def validate_timetable_run(timetable_run):
    """
    Validate a TimetableRun instance before generation.
    
    Args:
        timetable_run: TimetableRun instance
    
    Returns:
        tuple: (is_valid: bool, errors: list of error messages, recommendations: list of recommendation messages)
    """
    return validate_timetable_prerequisites(
        college=timetable_run.college,
        course=timetable_run.course,
        academic_year=timetable_run.academic_year,
        semester=timetable_run.semester
    )

