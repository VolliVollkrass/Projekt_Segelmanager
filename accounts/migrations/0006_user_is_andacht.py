from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_manueller_seemeileneintrag'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_andacht',
            field=models.BooleanField(default=False),
        ),
    ]
