import django.db.models.deletion
from django.db import migrations, models

import apps.core.constants as constants


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
        ("plans", "0002_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantEntitlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "feature_key",
                    models.CharField(
                        choices=constants.FeatureKey.CHOICES,
                        db_index=True,
                        help_text="Feature identifier from FeatureKey constants.",
                        max_length=100,
                    ),
                ),
                (
                    "is_enabled",
                    models.BooleanField(
                        default=True,
                        help_text="True = grant this feature. False = explicitly revoke it.",
                    ),
                ),
                (
                    "module_key",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Which add-on module granted this (provenance, for bulk revoke).",
                        max_length=50,
                    ),
                ),
                (
                    "expires_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        help_text="When this entitlement lapses. Null = never expires.",
                    ),
                ),
                ("note", models.CharField(blank=True, default="", max_length=200)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entitlements",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tenant Entitlement",
                "verbose_name_plural": "Tenant Entitlements",
                "ordering": ["tenant", "feature_key"],
            },
        ),
        migrations.AddIndex(
            model_name="tenantentitlement",
            index=models.Index(fields=["tenant", "feature_key"], name="entl_tenant_feature_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="tenantentitlement",
            unique_together={("tenant", "feature_key")},
        ),
    ]
