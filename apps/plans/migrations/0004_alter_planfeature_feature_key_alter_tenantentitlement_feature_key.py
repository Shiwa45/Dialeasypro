import apps.core.constants
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0003_tenantentitlement"),
    ]

    operations = [
        migrations.AlterField(
            model_name="planfeature",
            name="feature_key",
            field=models.CharField(
                choices=apps.core.constants.FeatureKey.CHOICES,
                help_text="Feature identifier from FeatureKey constants.",
                max_length=100,
            ),
        ),
        migrations.AlterField(
            model_name="tenantentitlement",
            name="feature_key",
            field=models.CharField(
                choices=apps.core.constants.FeatureKey.CHOICES,
                db_index=True,
                help_text="Feature identifier from FeatureKey constants.",
                max_length=100,
            ),
        ),
    ]
