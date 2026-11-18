from django.db import migrations, models


def confirm_existing_pending_orders(apps, schema_editor):
    Order = apps.get_model("brandat_egy", "Order")
    Order.objects.filter(status="pending").update(status="confirmed")


class Migration(migrations.Migration):

    dependencies = [
        ("brandat_egy", "0023_review_order_box"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("confirmed", "Confirmed"),
                    ("preparing", "Preparing"),
                    ("shipped", "Shipped"),
                    ("delivered", "Delivered"),
                    ("cancelled", "Cancelled"),
                    ("pending", "Pending"),
                    ("paid", "Paid"),
                ],
                default="confirmed",
                max_length=20,
                verbose_name="Order status",
            ),
        ),
        migrations.RunPython(
            confirm_existing_pending_orders,
            migrations.RunPython.noop,
        ),
    ]
