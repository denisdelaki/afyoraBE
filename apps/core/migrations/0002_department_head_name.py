from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='department',
            name='head_name',
            field=models.CharField(blank=True, max_length=150),
        ),
    ]
