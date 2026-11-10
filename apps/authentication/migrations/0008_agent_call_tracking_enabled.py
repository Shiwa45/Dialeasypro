from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0007_default_working_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='agent',
            name='call_tracking_enabled',
            field=models.BooleanField(default=True, help_text="Track this agent's phone calls when the company has call tracking on."),
        ),
    ]
