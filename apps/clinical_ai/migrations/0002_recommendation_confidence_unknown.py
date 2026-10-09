from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clinical_ai', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clinicalairecommendation',
            name='confidence',
            field=models.CharField(
                choices=[
                    ('low', 'Low'),
                    ('medium', 'Medium'),
                    ('high', 'High'),
                    ('unknown', 'Unknown'),
                ],
                default='medium',
                max_length=10,
            ),
        ),
    ]
