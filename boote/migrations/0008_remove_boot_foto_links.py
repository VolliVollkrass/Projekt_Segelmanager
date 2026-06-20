from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('boote', '0007_boot_abschluss_felder'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='boot',
            name='foto_upload_link',
        ),
        migrations.RemoveField(
            model_name='boot',
            name='foto_download_link',
        ),
    ]
