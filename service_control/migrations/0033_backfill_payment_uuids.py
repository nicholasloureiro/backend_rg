"""Backfill stable UUIDs onto every payment_details entry.

Existing entries pre-date the per-entry id and are addressed only by their
list index, which makes deletion/editing unsafe when entries are concurrently
appended. This migration walks every ServiceOrder and adds an `id` UUID to
each entry that doesn't already have one.
"""
import uuid

from django.db import migrations


def backfill_ids(apps, schema_editor):
    ServiceOrder = apps.get_model("service_control", "ServiceOrder")
    for order in ServiceOrder.objects.exclude(payment_details__isnull=True).iterator():
        details = order.payment_details
        if not isinstance(details, list):
            continue
        changed = False
        for entry in details:
            if isinstance(entry, dict) and not entry.get("id"):
                entry["id"] = str(uuid.uuid4())
                changed = True
        if changed:
            order.payment_details = details
            order.save(update_fields=["payment_details"])


def noop_reverse(apps, schema_editor):
    # UUIDs are additive metadata; don't strip them on rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("service_control", "0032_serviceorder_data_resgate_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_ids, noop_reverse),
    ]
