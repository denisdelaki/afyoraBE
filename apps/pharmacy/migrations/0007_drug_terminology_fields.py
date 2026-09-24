from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0006_drugpurchaseorder_drugpurchaseorderitem_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='drug',
            name='drug_code',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='drug',
            name='drug_system',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='drug',
            name='is_coded',
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name='drug',
            index=models.Index(fields=['facility', 'drug_code'], name='pharmacy_dr_facilit_0c279b_idx'),
        ),
    ]