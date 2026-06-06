"""
TeleCRM Backend — apps/leads/forms.py

Django ModelForms for lead management in the tenant admin web UI.
"""
from django import forms
from django.utils import timezone

from apps.core.constants import FollowUpType, LeadPriority, LeadSource, LeadStatus
from apps.leads.models import FollowUp, Lead, LeadNote


class LeadForm(forms.ModelForm):
    """Create or edit a lead."""

    class Meta:
        model = Lead
        fields = [
            "name", "phone", "alternate_phone", "email",
            "city", "state", "pincode",
            "source", "status", "priority",
            "assigned_to",
            "budget", "requirement",
            "deal_value", "expected_close_date",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Lead name"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "10-digit mobile"}),
            "alternate_phone": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control", "maxlength": "100"}),
            "pincode": forms.TextInput(attrs={"class": "form-control", "maxlength": "6"}),
            "source": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "assigned_to": forms.Select(attrs={"class": "form-select"}),
            "budget": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Budget in ₹"}),
            "requirement": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "deal_value": forms.NumberInput(attrs={"class": "form-control"}),
            "expected_close_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "")
        if phone:
            from apps.core.utils import normalize_indian_phone
            normalized = normalize_indian_phone(phone)
            if not normalized:
                raise forms.ValidationError("Invalid Indian mobile number. Enter 10 digits.")
            # Duplicate check (exclude self on update)
            qs = Lead.objects.filter(phone=normalized, is_deleted=False)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("A lead with this phone number already exists.")
            return normalized
        return phone

    def clean_alternate_phone(self):
        phone = self.cleaned_data.get("alternate_phone", "")
        if phone:
            from apps.core.utils import normalize_indian_phone
            normalized = normalize_indian_phone(phone)
            if not normalized:
                raise forms.ValidationError("Invalid alternate phone number.")
            return normalized
        return phone

    def clean_pincode(self):
        pincode = self.cleaned_data.get("pincode", "")
        if pincode and not pincode.isdigit():
            raise forms.ValidationError("Pincode must be numeric.")
        return pincode


class FollowUpForm(forms.ModelForm):
    """Schedule a follow-up for a lead."""

    class Meta:
        model = FollowUp
        fields = ["followup_type", "scheduled_at", "notes", "assigned_to"]
        widgets = {
            "followup_type": forms.Select(attrs={"class": "form-select"}),
            "scheduled_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "assigned_to": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_scheduled_at(self):
        scheduled_at = self.cleaned_data.get("scheduled_at")
        if scheduled_at and scheduled_at < timezone.now():
            raise forms.ValidationError("Follow-up time must be in the future.")
        return scheduled_at


class LeadNoteForm(forms.ModelForm):
    """Add a note to a lead."""

    class Meta:
        model = LeadNote
        fields = ["content", "is_pinned", "attachment"]
        widgets = {
            "content": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Add your note here..."}
            ),
            "is_pinned": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "attachment": forms.FileInput(attrs={"class": "form-control"}),
        }


class LeadQuickStatusForm(forms.Form):
    """Quick status update (used via HTMX from kanban / lead detail)."""
    status = forms.ChoiceField(choices=LeadStatus.CHOICES, widget=forms.Select(attrs={"class": "form-select"}))
    note = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional note"}))


class LeadImportForm(forms.Form):
    """CSV/XLSX import form."""

    file = forms.FileField(
        label="Upload File (CSV or XLSX)",
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".csv,.xlsx"}),
    )
    duplicate_action = forms.ChoiceField(
        choices=[
            ("skip", "Skip duplicates"),
            ("update", "Update existing leads"),
            ("create_new", "Allow duplicates"),
        ],
        initial="skip",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    source = forms.ChoiceField(
        choices=LeadSource.CHOICES,
        initial=LeadSource.MANUAL,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    assigned_to = forms.IntegerField(
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Default agent to assign imported leads to.",
    )
