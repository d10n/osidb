# Generated by Django 3.2.15 on 2023-03-09 13:45

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("osidb", "0066_tracker__alerts"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="flaw",
            name="mitigated_by",
        ),
        migrations.RemoveField(
            model_name="flawhistory",
            name="mitigated_by",
        ),
    ]
