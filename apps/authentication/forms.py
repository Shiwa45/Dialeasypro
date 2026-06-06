"""
TeleCRM Backend — apps/authentication/forms.py

Django forms for the MVT tenant admin web interface.
Used in AgentCreateView, AgentUpdateView, ProfileView, and login.
"""
from django import forms
from django.core.validators import RegexValidator

from apps.authentication.models import Agent, Team
from apps.core.constants import AgentRole


class AgentLoginForm(forms.Form):
    """Login form for the tenant admin web UI."""

    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "admin@yourcompany.com",
                "autofocus": True,
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Enter your password"}
        )
    )
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class AgentCreateForm(forms.ModelForm):
    """
    Form for creating a new agent.
    Includes password fields — handled separately (not via ModelForm default).
    """

    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Minimum 8 characters"}
        ),
        help_text="Minimum 8 characters. Agent must change on first login.",
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Repeat password"}
        )
    )

    class Meta:
        model = Agent
        fields = [
            "email",
            "name",
            "phone",
            "employee_id",
            "role",
            "timezone",
            "shift_start",
            "shift_end",
        ]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "9876543210 (10-digit mobile)",
                }
            ),
            "employee_id": forms.TextInput(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "timezone": forms.Select(attrs={"class": "form-select"}),
            "shift_start": forms.TimeInput(
                attrs={"class": "form-control", "type": "time"}
            ),
            "shift_end": forms.TimeInput(
                attrs={"class": "form-control", "type": "time"}
            ),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email", "").lower()
        if Agent.objects.filter(email=email).exists():
            raise forms.ValidationError(
                "An agent with this email already exists in your team."
            )
        return email

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "")
        if phone:
            from apps.core.utils import normalize_indian_phone
            normalized = normalize_indian_phone(phone)
            if not normalized:
                raise forms.ValidationError(
                    "Invalid Indian mobile number. Enter a 10-digit number."
                )
            return normalized
        return phone

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("confirm_password")
        if password and confirm and password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned


class AgentUpdateForm(forms.ModelForm):
    """
    Edit existing agent details.
    Password change has its own dedicated flow.
    """

    class Meta:
        model = Agent
        fields = [
            "name",
            "phone",
            "employee_id",
            "role",
            "is_active",
            "timezone",
            "shift_start",
            "shift_end",
            "working_days",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "employee_id": forms.TextInput(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "timezone": forms.Select(attrs={"class": "form-select"}),
            "shift_start": forms.TimeInput(
                attrs={"class": "form-control", "type": "time"}
            ),
            "shift_end": forms.TimeInput(
                attrs={"class": "form-control", "type": "time"}
            ),
        }

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "")
        if phone:
            from apps.core.utils import normalize_indian_phone
            normalized = normalize_indian_phone(phone)
            if not normalized:
                raise forms.ValidationError("Invalid Indian mobile number.")
            return normalized
        return phone


class AgentProfileForm(forms.ModelForm):
    """Self-edit form for the agent's own profile page."""

    class Meta:
        model = Agent
        fields = [
            "name",
            "phone",
            "profile_photo",
            "timezone",
            "language_preference",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "profile_photo": forms.FileInput(attrs={"class": "form-control"}),
            "timezone": forms.Select(attrs={"class": "form-select"}),
            "language_preference": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "")
        if phone:
            from apps.core.utils import normalize_indian_phone
            normalized = normalize_indian_phone(phone)
            if not normalized:
                raise forms.ValidationError("Invalid Indian mobile number.")
            return normalized
        return phone


class PasswordChangeForm(forms.Form):
    """Standalone password-change form (separate from Django's built-in)."""

    old_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        label="Current Password",
    )
    new_password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        label="New Password",
        help_text="Minimum 8 characters.",
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        label="Confirm New Password",
    )

    def clean(self):
        cleaned = super().clean()
        new = cleaned.get("new_password")
        confirm = cleaned.get("confirm_password")
        if new and confirm and new != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned
