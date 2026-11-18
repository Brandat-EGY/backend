from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("brandat_egy", "0022_alter_boximage_options_alter_boxitem_options_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="review",
            name="order_item",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="review",
                to="brandat_egy.orderitem",
                verbose_name="Reviewed item",
            ),
        ),
        migrations.AddField(
            model_name="review",
            name="order_box",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="review",
                to="brandat_egy.orderbox",
                verbose_name="Reviewed box",
            ),
        ),
        migrations.AddConstraint(
            model_name="review",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    order_item__isnull=False,
                    order_box__isnull=True,
                )
                | models.Q(
                    order_item__isnull=True,
                    order_box__isnull=False,
                ),
                name="review_has_one_target",
            ),
        ),
    ]
