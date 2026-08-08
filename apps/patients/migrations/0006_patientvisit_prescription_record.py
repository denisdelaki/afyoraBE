from django.db import migrations, models
import django.db.models.deletion


def link_existing_prescription_ids(apps, schema_editor):
    PatientVisit = apps.get_model('patients', 'PatientVisit')
    Prescription = apps.get_model('pharmacy', 'Prescription')

    visits = PatientVisit.objects.filter(
        prescription__isnull=False,
        prescription_record__isnull=True,
    ).exclude(prescription='')

    for visit in visits.iterator():
        prescription = Prescription.objects.filter(
            facility_id=visit.facility_id,
            prescription_id=visit.prescription,
        ).first()
        if prescription is None:
            continue

        visit.prescription_record_id = prescription.id
        visit.save(update_fields=['prescription_record', 'updated_at'])


def unlink_existing_prescription_ids(apps, schema_editor):
    # Keep historical prescription text values untouched on reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0002_prescription'),
        ('patients', '0005_add_prescriptions_to_patientvisit'),
    ]

    operations = [
        migrations.AddField(
            model_name='patientvisit',
            name='prescription_record',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='visit_histories',
                to='pharmacy.prescription',
            ),
        ),
        migrations.RunPython(
            link_existing_prescription_ids,
            reverse_code=unlink_existing_prescription_ids,
        ),
    ]
