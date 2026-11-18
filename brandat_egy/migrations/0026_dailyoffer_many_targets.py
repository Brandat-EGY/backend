from django.db import migrations, models


def copy_targets(apps, schema_editor):
    DailyOffer = apps.get_model("brandat_egy", "DailyOffer")
    for offer in DailyOffer.objects.all().iterator():
        if offer.variant_id:
            offer.variants.add(offer.variant_id)
        if offer.box_id:
            offer.boxes.add(offer.box_id)


class Migration(migrations.Migration):

    dependencies = [
        ("brandat_egy", "0025_alter_boximage_unique_main_image_per_box_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dailyoffer",
            name="variant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="+",
                to="brandat_egy.productvariant",
                verbose_name="Offer variant",
            ),
        ),
        migrations.AlterField(
            model_name="dailyoffer",
            name="box",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="+",
                to="brandat_egy.box",
                verbose_name="Box",
            ),
        ),
        migrations.AddField(
            model_name="dailyoffer",
            name="variants",
            field=models.ManyToManyField(
                blank=True,
                related_name="daily_offers",
                to="brandat_egy.productvariant",
                verbose_name="Product options",
            ),
        ),
        migrations.AddField(
            model_name="dailyoffer",
            name="boxes",
            field=models.ManyToManyField(
                blank=True,
                related_name="daily_offers",
                to="brandat_egy.box",
                verbose_name="Boxes",
            ),
        ),
        migrations.RunPython(copy_targets, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="dailyoffer",
            name="daily_offer_exactly_one_target",
        ),
        migrations.RemoveField(
            model_name="dailyoffer",
            name="variant",
        ),
        migrations.RemoveField(
            model_name="dailyoffer",
            name="box",
        ),
    ]
