from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0005_tenant_agent_web_access'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='call_tracking_enabled',
            field=models.BooleanField(default=False, verbose_name='Track all phone calls from the mobile app'),
        ),
    ]
