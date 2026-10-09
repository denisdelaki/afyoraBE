from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('patients', '0011_patientvital'),
    ]

    operations = [
        migrations.AddField(
            model_name='patientvital',
            name='ticket',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='vitals', to='patients.outpatientticket',
            ),
        ),
    ]