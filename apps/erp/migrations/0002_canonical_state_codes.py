"""
Store customers' state codes in the same scheme as the tenant's own state.

The customer form offered CT/OR/TG/UT/DD; the tenant's state uses
CG/OD/TS/UK/DN. Comparing the two decides CGST+SGST vs IGST, so a seller and a
customer in the same state could be taxed as interstate.
"""
from django.db import migrations

ALIASES = {"CT": "CG", "OR": "OD", "TG": "TS", "UT": "UK", "DD": "DN"}


def forwards(apps, schema_editor):
    Customer = apps.get_model("erp", "Customer")
    for old, new in ALIASES.items():
        Customer.objects.filter(state_code=old).update(state_code=new)


class Migration(migrations.Migration):

    dependencies = [("erp", "0001_initial")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
