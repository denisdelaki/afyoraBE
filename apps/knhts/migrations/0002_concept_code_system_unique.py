from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('knhts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='knhtsconcept',
            name='code',
            field=models.CharField(max_length=100),
        ),
        migrations.AddConstraint(
            model_name='knhtsconcept',
            constraint=models.UniqueConstraint(
                fields=('code_system', 'code'),
                name='knhts_concept_system_code_uniq',
            ),
        ),
    ]
