from django import forms
from .models import TimetableDay, TimeSlot, Classroom
from education.models import College


class TimetableDayForm(forms.ModelForm):
    class Meta:
        model = TimetableDay
        fields = ['name', 'order_index']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g., Monday'}),
            'order_index': forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
        }


class TimeSlotForm(forms.ModelForm):
    class Meta:
        model = TimeSlot
        fields = ['start_time', 'end_time']
        widgets = {
            'start_time': forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
        }


class ClassroomForm(forms.ModelForm):
    class Meta:
        model = Classroom
        fields = ['name', 'capacity']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g., Room 101, Lab A'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
        }

