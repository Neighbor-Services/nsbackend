from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0004_servicepackage'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ServicePackage',
        ),
    ]
