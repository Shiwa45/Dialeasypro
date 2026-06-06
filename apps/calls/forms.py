"""
TeleCRM Backend — apps/calls/forms.py

Django forms for call management in the tenant admin web UI.
"""
from django import forms
from django.utils import timezone

from apps.calls.models import CallDisposition, CallLog


class ManualCallLogForm(forms.ModelForm):
    """
    Form for manually logging a call that was made outside the CRM
    (e.g., mobile call not routed through Exotel/MCUBE).
    """

    class Meta:
        model = CallLog
        fields = [
            "lead",
            "direction",
            "phone_number",
            "started_at",
            "duration_seconds",
            "is_connected",
            "disposition",
            "notes",
        ]
        widgets = {
            "lead": forms.Select(attrs={"class": "form-select"}),
            "direction": forms.Select(attrs={"class": "form-select"}),
            "phone_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "10-digit mobile number"}
            ),
            "started_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "duration_seconds": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Duration in seconds"}
            ),
            "is_connected": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "disposition": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Call notes..."}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active dispositions
        self.fields["disposition"].queryset = CallDisposition.objects.filter(
            is_active=True
        ).order_by("sort_order")
        self.fields["disposition"].required = False
        self.fields["lead"].required = False
        # Default started_at to now
        if not self.initial.get("started_at"):
            self.initial["started_at"] = timezone.now().strftime("%Y-%m-%dT%H:%M")

    def clean_phone_number(self):
        phone = self.cleaned_data.get("phone_number", "")
        if phone:
            from apps.core.utils import normalize_indian_phone
            normalized = normalize_indian_phone(phone)
            if not normalized:
                raise forms.ValidationError("Invalid Indian mobile number.")
            return normalized
        return phone

    def clean(self):
        cleaned = super().clean()
        # If duration is provided but is_connected is not checked, auto-set
        duration = cleaned.get("duration_seconds", 0)
        if duration and duration > 0:
            cleaned["is_connected"] = True
        return cleaned


class CallDispositionForm(forms.ModelForm):
    """Create/edit a call disposition option (admin only)."""

    class Meta:
        model = CallDisposition
        fields = [
            "name", "slug", "is_positive", "is_active",
            "sort_order", "auto_followup_hours",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "is_positive": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
            "auto_followup_hours": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 24 = 1 day (leave blank to disable)"}
            ),
        }

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "")
        if not slug:
            from django.utils.text import slugify
            slug = slugify(self.cleaned_data.get("name", ""))
        return slug
