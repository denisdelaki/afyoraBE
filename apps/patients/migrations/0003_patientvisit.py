from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('patients', '0002_patient_age'),
    ]

    operations = [
        migrations.CreateModel(
            name='PatientVisit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('visit_date', models.DateField()),
                ('served_by', models.CharField(max_length=150)),
                ('diagnosis', models.CharField(blank=True, max_length=255)),
                ('prescription', models.CharField(blank=True, max_length=255)),
                ('what_happened', models.TextField(blank=True)),
                ('amount_billed', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('facility', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='patient_visits', to='core.facility')),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='visits', to='patients.patient')),
            ],
            options={
                'ordering': ['-visit_date', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='patientvisit',
            index=models.Index(fields=['facility', 'patient', 'visit_date'], name='patients_pa_facilit_4f8db3_idx'),
        ),
        migrations.AddIndex(
            model_name='patientvisit',
            index=models.Index(fields=['facility', 'visit_date'], name='patients_pa_facilit_0cb6e2_idx'),
        ),
    ]
