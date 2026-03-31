from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailverificationtoken",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("email_verification", "Email Verification"),
                    ("password_reset", "Password Reset"),
                    ("admin_invite", "Admin Invite"),
                ],
                default="email_verification",
                max_length=32,
            ),
        ),
    ]
