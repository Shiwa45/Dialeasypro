"""
TeleCRM Backend — apps/plans/serializers.py
"""
from rest_framework import serializers
from apps.plans.models import Invoice, Plan, PlanFeature, Subscription
from apps.core.constants import FeatureKey


class PlanFeatureSerializer(serializers.ModelSerializer):
    feature_label = serializers.SerializerMethodField()

    class Meta:
        model = PlanFeature
        fields = ["feature_key", "feature_label", "is_enabled"]

    def get_feature_label(self, obj):
        return FeatureKey.LABELS.get(obj.feature_key, obj.feature_key)


class PlanSerializer(serializers.ModelSerializer):
    features = PlanFeatureSerializer(many=True, read_only=True)
    yearly_savings_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = Plan
        fields = [
            "id", "name", "slug", "description",
            "price_monthly", "price_yearly", "yearly_savings_percent",
            "max_agents", "max_leads", "max_leads_per_day",
            "max_whatsapp_bulk_per_day", "max_email_bulk_per_day",
            "max_sms_per_day", "storage_gb", "custom_fields_limit",
            "data_retention_days", "features",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    days_until_renewal = serializers.IntegerField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id", "plan", "plan_name", "status", "billing_cycle",
            "current_period_start", "current_period_end",
            "trial_end", "cancel_at_period_end", "days_until_renewal",
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            "id", "invoice_number", "invoice_date",
            "base_amount", "cgst_amount", "sgst_amount", "igst_amount", "total_amount",
            "payment_status", "billing_period_start", "billing_period_end", "paid_at",
        ]
