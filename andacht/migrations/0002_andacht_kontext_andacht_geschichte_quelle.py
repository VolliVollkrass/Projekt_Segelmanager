from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('andacht', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='andacht',
            name='kontext',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='andacht',
            name='geschichte_quelle',
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
