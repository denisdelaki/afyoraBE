from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0006_alter_mpesaconfig_passkey'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='mpesa_transaction',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='payment',
                to='billing.mpesatransaction',
            ),
        ),
    ]