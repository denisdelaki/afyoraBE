from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Employee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('employee_id', models.CharField(max_length=20)),
                ('name', models.CharField(max_length=255)),
                ('role', models.CharField(max_length=100)),
                ('department', models.CharField(blank=True, max_length=100)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('join_date', models.DateField()),
                ('salary', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('status', models.CharField(choices=[('Active', 'Active'), ('Inactive', 'Inactive'), ('Terminated', 'Terminated')], default='Active', max_length=20)),
                ('shift', models.CharField(choices=[('Morning', 'Morning'), ('Evening', 'Evening'), ('Night', 'Night')], default='Morning', max_length=20)),
                ('facility', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='employees', to='core.facility')),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('facility', 'employee_id')},
            },
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['facility', 'employee_id'], name='employees_e_facilit_f95be2_idx'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['facility', 'email'], name='employees_e_facilit_a8ce11_idx'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['facility', 'name'], name='employees_e_facilit_bf768a_idx'),
        ),
    ]
