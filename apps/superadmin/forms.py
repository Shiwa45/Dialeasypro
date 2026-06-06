"""TeleCRM Backend — apps/superadmin/forms.py"""
from django import forms
from apps.tenants.models import Tenant

class TenantSuspendForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Reason for suspension (visible in internal notes).",
    )

class GlobalSettingsForm(forms.Form):
    key = forms.CharField(max_length=100)
    value = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))
    description = forms.CharField(max_length=500, required=False)
