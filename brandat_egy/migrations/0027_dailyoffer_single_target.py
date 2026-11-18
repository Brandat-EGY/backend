from django.db import migrations, models


def restore_single_target(apps, schema_editor):
    DailyOffer = apps.get_model("brandat_egy", "DailyOffer")
    for offer in DailyOffer.objects.all():
        variant_ids = list(offer.variants.values_list("pk", flat=True))
        box_ids = list(offer.boxes.values_list("pk", flat=True))
        targets = [("variant", pk) for pk in variant_ids]
        targets.extend(("box", pk) for pk in box_ids)
        if not targets:
            offer.delete()
            continue
        kind, pk = targets[0]
        offer.variant_id = pk if kind == "variant" else None
        offer.box_id = pk if kind == "box" else None
        offer.save(update_fields=["variant_id", "box_id"])
        for extra_kind, extra_pk in targets[1:]:
            DailyOffer.objects.create(
                price=offer.price,
                starts_at=offer.starts_at,
                ends_at=offer.ends_at,
                is_active=offer.is_active,
                variant_id=extra_pk if extra_kind == "variant" else None,
                box_id=extra_pk if extra_kind == "box" else None,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("brandat_egy", "0026_dailyoffer_many_targets"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dailyoffer",
            name="variants",
            field=models.ManyToManyField(
                blank=True,
                related_name="+",
                to="brandat_egy.productvariant",
                verbose_name="Product options",
            ),
        ),
        migrations.AlterField(
            model_name="dailyoffer",
            name="boxes",
            field=models.ManyToManyField(
                blank=True,
                related_name="+",
                to="brandat_egy.box",
                verbose_name="Boxes",
            ),
        ),
        migrations.AddField(
            model_name="dailyoffer",
            name="variant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="daily_offers",
                to="brandat_egy.productvariant",
                verbose_name="Offer variant",
            ),
        ),
        migrations.AddField(
            model_name="dailyoffer",
            name="box",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="daily_offers",
                to="brandat_egy.box",
                verbose_name="Box",
            ),
        ),
        migrations.RunPython(restore_single_target, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="dailyoffer",
            name="variants",
        ),
        migrations.RemoveField(
            model_name="dailyoffer",
            name="boxes",
        ),
        migrations.AddConstraint(
            model_name="dailyoffer",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(variant__isnull=False, box__isnull=True)
                    | models.Q(variant__isnull=True, box__isnull=False)
                ),
                name="daily_offer_exactly_one_target",
            ),
        ),
    ]
