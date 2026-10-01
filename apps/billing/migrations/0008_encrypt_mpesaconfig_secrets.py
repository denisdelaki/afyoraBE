from django.db import migrations

import billing.fields


def encrypt_existing_secrets(apps, schema_editor):
    MpesaConfig = apps.get_model('billing', 'MpesaConfig')
    for config in MpesaConfig.objects.all().iterator():
        updates = {}
        if config.passkey:
            updates['passkey'] = billing.fields.encrypt_mpesa_secret(config.passkey)
        if config.consumer_secret:
            updates['consumer_secret'] = billing.fields.encrypt_mpesa_secret(config.consumer_secret)
        if updates:
            MpesaConfig.objects.filter(pk=config.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_payment_mpesa_transaction'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mpesaconfig',
            name='passkey',
            field=billing.fields.EncryptedTextField(blank=True, default='', max_length=1024),
        ),
        migrations.AlterField(
            model_name='mpesaconfig',
            name='consumer_secret',
            field=billing.fields.EncryptedTextField(blank=True, default='', max_length=1024),
        ),
        migrations.RunPython(encrypt_existing_secrets, migrations.RunPython.noop),
    ]