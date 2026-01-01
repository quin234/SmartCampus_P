from django.contrib import admin
from .models import (
    TimetableDay, TimeSlot, Classroom,
    TimetableRun, TimetableEntry,
    TimetableGeneration
)


@admin.register(TimetableDay)
class TimetableDayAdmin(admin.ModelAdmin):
    list_display = ['name', 'order_index']
    list_editable = ['order_index']
    ordering = ['order_index']
    search_fields = ['name']


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ['start_time', 'end_time', 'get_duration']
    ordering = ['start_time']
    search_fields = ['start_time', 'end_time']
    
    def get_duration(self, obj):
        """Calculate duration in minutes"""
        from datetime import datetime, timedelta
        start = datetime.combine(datetime.today(), obj.start_time)
        end = datetime.combine(datetime.today(), obj.end_time)
        if end < start:
            end += timedelta(days=1)
        duration = end - start
        return f"{duration.seconds // 60} minutes"
    get_duration.short_description = 'Duration'


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ['name', 'college', 'capacity']
    list_filter = ['college']
    search_fields = ['name', 'college__name']
    ordering = ['college', 'name']


@admin.register(TimetableRun)
class TimetableRunAdmin(admin.ModelAdmin):
    list_display = ['college', 'course', 'academic_year', 'semester', 'status', 'created_by', 'created_at', 'generated_at', 'published_at']
    list_filter = ['status', 'academic_year', 'semester', 'college']
    search_fields = ['college__name', 'course__name', 'academic_year']
    readonly_fields = ['created_at', 'generated_at', 'published_at']
    date_hierarchy = 'created_at'
    raw_id_fields = ['college', 'course', 'created_by']


@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
    list_display = ['timetable', 'day', 'time_slot', 'course', 'unit', 'lecturer', 'classroom']
    list_filter = ['day', 'timetable__college', 'timetable__academic_year', 'timetable__semester', 'course']
    search_fields = ['unit__code', 'unit__name', 'course__name', 'lecturer__username', 'classroom__name']
    ordering = ['timetable', 'day__order_index', 'time_slot__start_time']
    raw_id_fields = ['timetable', 'day', 'time_slot', 'course', 'unit', 'lecturer', 'classroom']
    date_hierarchy = 'timetable__created_at'


@admin.register(TimetableGeneration)
class TimetableGenerationAdmin(admin.ModelAdmin):
    list_display = ['college', 'course', 'academic_year', 'semester', 'status', 'generated_by', 'generated_at']
    list_filter = ['status', 'academic_year', 'semester', 'college']
    search_fields = ['college__name', 'course__name', 'academic_year']
    readonly_fields = ['generated_at']
