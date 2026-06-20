from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('toern', '0016_toern_fotogalerie_logbuch'),
    ]

    operations = [
        # Toern: fotogalerie_link → foto_download_link + neues foto_upload_link
        migrations.RenameField(
            model_name='toern',
            old_name='fotogalerie_link',
            new_name='foto_download_link',
        ),
        migrations.AddField(
            model_name='toern',
            name='foto_upload_link',
            field=models.URLField(blank=True),
        ),
        # Teilnahme: gesegelte_meilen → individuelle_meilen (nullable)
        migrations.RenameField(
            model_name='teilnahme',
            old_name='gesegelte_meilen',
            new_name='individuelle_meilen',
        ),
        migrations.AlterField(
            model_name='teilnahme',
            name='individuelle_meilen',
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
    ]
