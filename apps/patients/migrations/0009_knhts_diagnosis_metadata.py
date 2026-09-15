from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0008_patient_national_id_or_birth_certificate_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='patientvisit',
            name='diagnosis_code',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddField(
            model_name='patientvisit',
            name='diagnosis_lookup_timestamp',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='patientvisit',
            name='diagnosis_system',
            field=models.CharField(blank=True, default='KNHTS', max_length=50),
        ),
        migrations.AddField(
            model_name='patientvisit',
            name='diagnosis_text',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='ehrrecord',
            name='diagnosis_code',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddField(
            model_name='ehrrecord',
            name='diagnosis_lookup_timestamp',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='ehrrecord',
            name='diagnosis_system',
            field=models.CharField(blank=True, default='KNHTS', max_length=50),
        ),
        migrations.AddField(
            model_name='ehrrecord',
            name='diagnosis_text',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]