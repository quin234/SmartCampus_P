from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from education.models import College, CollegeCourse, CollegeUnit, CustomUser


# Reference Tables

class TimetableDay(models.Model):
    """Days of the week for timetable scheduling"""
    name = models.CharField(max_length=20, unique=True, help_text="Day name (e.g., Monday, Tuesday)")
    order_index = models.IntegerField(unique=True, help_text="Order for sorting days (1=Monday, 2=Tuesday, etc.)")
    
    class Meta:
        db_table = 'timetable_days'
        ordering = ['order_index']
        verbose_name = 'Timetable Day'
        verbose_name_plural = 'Timetable Days'
    
    def __str__(self):
        return self.name


class TimeSlot(models.Model):
    """Time slots for timetable scheduling"""
    start_time = models.TimeField(help_text="Start time (e.g., 08:00)")
    end_time = models.TimeField(help_text="End time (e.g., 09:00)")
    
    class Meta:
        db_table = 'timetable_time_slots'
        ordering = ['start_time']
        unique_together = [['start_time', 'end_time']]
        verbose_name = 'Time Slot'
        verbose_name_plural = 'Time Slots'
    
    def __str__(self):
        return f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"
    
    def get_duration(self):
        """Calculate duration in minutes"""
        from datetime import datetime, timedelta
        start = datetime.combine(datetime.today(), self.start_time)
        end = datetime.combine(datetime.today(), self.end_time)
        if end < start:
            # Handle case where end time is next day
            end += timedelta(days=1)
        duration = end - start
        return int(duration.total_seconds() / 60)
    
    def get_duration_display(self):
        """Get duration as a human-readable string"""
        minutes = self.get_duration()
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0:
            return f"{hours}h {mins}m" if mins > 0 else f"{hours}h"
        return f"{mins}m"


class Classroom(models.Model):
    """Classrooms/venues for timetable scheduling"""
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='classrooms')
    name = models.CharField(max_length=100, help_text="Classroom name or number (e.g., Room 101, Lab A)")
    capacity = models.IntegerField(validators=[MinValueValidator(1)], help_text="Maximum capacity of the classroom")
    
    class Meta:
        db_table = 'timetable_classrooms'
        ordering = ['name']
        unique_together = [['college', 'name']]
        verbose_name = 'Classroom'
        verbose_name_plural = 'Classrooms'
    
    def __str__(self):
        return f"{self.college.name} - {self.name} (Capacity: {self.capacity})"


# Timetable Lifecycle Models

class TimetableRun(models.Model):
    """Timetable generation run - tracks the lifecycle of a timetable"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('generated', 'Generated'),
        ('published', 'Published'),
    ]
    
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='timetable_runs')
    course = models.ForeignKey(CollegeCourse, on_delete=models.CASCADE, null=True, blank=True, related_name='timetable_runs', help_text="Leave empty for general timetable applicable to all courses")
    academic_year = models.CharField(max_length=20, help_text="Academic year (e.g., 2024/2025)")
    semester = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)], help_text="Semester number")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', help_text="Current status of the timetable")
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='created_timetable_runs')
    created_at = models.DateTimeField(auto_now_add=True, help_text="When the timetable run was created")
    generated_at = models.DateTimeField(null=True, blank=True, help_text="When the timetable was generated")
    published_at = models.DateTimeField(null=True, blank=True, help_text="When the timetable was published")
    notes = models.TextField(blank=True, help_text="Optional notes or description")
    
    class Meta:
        db_table = 'timetable_runs'
        ordering = ['-created_at']
        unique_together = [['college', 'course', 'academic_year', 'semester']]
        indexes = [
            models.Index(fields=['college', 'status']),
            models.Index(fields=['college', 'academic_year', 'semester']),
            models.Index(fields=['college', 'course']),
        ]
        verbose_name = 'Timetable Run'
        verbose_name_plural = 'Timetable Runs'
    
    @property
    def user(self):
        """Backward compatibility property: maps to created_by"""
        return self.created_by
    
    def __str__(self):
        course_name = self.course.name if self.course else "General"
        return f"{self.college.name} - {course_name} - {self.academic_year} Sem {self.semester} ({self.get_status_display()})"


class TimetableEntry(models.Model):
    """Individual timetable entry - represents a scheduled class"""
    timetable = models.ForeignKey(TimetableRun, on_delete=models.CASCADE, related_name='entries', help_text="The timetable run this entry belongs to")
    day = models.ForeignKey(TimetableDay, on_delete=models.CASCADE, related_name='timetable_entries', help_text="Day of the week")
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, related_name='timetable_entries', help_text="Time slot for this class")
    course = models.ForeignKey(CollegeCourse, on_delete=models.CASCADE, related_name='timetable_entries', help_text="Course this entry is for")
    unit = models.ForeignKey(CollegeUnit, on_delete=models.CASCADE, related_name='timetable_entries', help_text="Unit being taught")
    lecturer = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='timetable_entries', limit_choices_to={'role': 'lecturer'}, help_text="Lecturer assigned to teach this class")
    classroom = models.ForeignKey(Classroom, on_delete=models.SET_NULL, null=True, blank=True, related_name='timetable_entries', help_text="Classroom/venue for this class")
    
    class Meta:
        db_table = 'timetable_entries'
        ordering = ['day__order_index', 'time_slot__start_time']
        unique_together = [
            ['timetable', 'day', 'time_slot', 'classroom'],  # Prevent double booking of classroom
            ['timetable', 'day', 'time_slot', 'lecturer'],  # Prevent double booking of lecturer
        ]
        indexes = [
            models.Index(fields=['day', 'time_slot']),  # As specified in requirements
            models.Index(fields=['timetable', 'day', 'time_slot']),
            models.Index(fields=['timetable', 'course']),
            models.Index(fields=['timetable', 'lecturer']),
            models.Index(fields=['timetable', 'classroom']),
        ]
        verbose_name = 'Timetable Entry'
        verbose_name_plural = 'Timetable Entries'
    
    def __str__(self):
        return f"{self.day.name} {self.time_slot} - {self.unit.code} ({self.course.name})"


# Legacy model for backward compatibility (can be removed later if not needed)
class TimetableGeneration(models.Model):
    """Model to track timetable generation requests and status (legacy)"""
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='timetable_generations')
    course = models.ForeignKey(CollegeCourse, on_delete=models.CASCADE, null=True, blank=True, related_name='timetable_generations')
    academic_year = models.CharField(max_length=20, blank=True, null=True)
    semester = models.IntegerField(null=True, blank=True)
    generated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='generated_timetables')
    generated_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('generated', 'Generated'),
        ('deployed', 'Deployed'),
        ('failed', 'Failed'),
    ], default='pending')
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'timetable_generations'
        ordering = ['-generated_at']
    
    def __str__(self):
        if self.course:
            return f"{self.college.name} - {self.course.name} Timetable Generation"
        return f"{self.college.name} - General Timetable Generation"
