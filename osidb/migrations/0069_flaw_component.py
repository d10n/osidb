# Generated by Django 3.2.15 on 2023-03-14 15:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("osidb", "0068_flaw_mitigation"),
    ]

    operations = [
        migrations.AddField(
            model_name="flaw",
            name="component",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]