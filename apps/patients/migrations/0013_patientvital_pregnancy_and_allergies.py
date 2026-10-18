from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('patients', '0012_patientvital_ticket'),
    ]

    operations = [
        migrations.AddField(
            model_name='patientvital',
            name='allergies',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='patientvital',
            name='is_pregnant',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='patientvital',
            name='pregnancy_months',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='patientvital',
            name='last_menstrual_period',
            field=models.DateField(blank=True, null=True),
        ),
    ]