from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="IdempotencyKey",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("scope", models.CharField(max_length=64)),
                ("key", models.CharField(max_length=255)),
                ("request_hash", models.CharField(max_length=64)),
                ("response_status", models.PositiveSmallIntegerField()),
                ("response_body", models.JSONField(default=dict)),
            ],
            options={"abstract": False},
        ),
        migrations.AddIndex(
            model_name="idempotencykey",
            index=models.Index(fields=["created_at"], name="idx_idempotency_created"),
        ),
        migrations.AddConstraint(
            model_name="idempotencykey",
            constraint=models.UniqueConstraint(
                fields=("scope", "key"), name="uniq_idempotency_scope_key"
            ),
        ),
    ]
