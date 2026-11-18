
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from .image_storage import delete_unused_image_file


@transaction.atomic
def create_image(
    *,
    owner_model,
    owner_id,
    image_model,
    owner_field,
    serializer,
):
    owner = get_object_or_404(
        owner_model.objects.select_for_update(),
        pk=owner_id,
    )

    images = image_model.objects.filter(
        **{owner_field: owner}
    )

    make_main = (
        not images.exists()
        or serializer.validated_data.get(
            "is_main", False
        )
    )

    if make_main:
        images.filter(
            is_main=True
        ).update(is_main=False)

    return serializer.save(
        **{
            owner_field: owner,
            "is_main": make_main,
        }
    )


@transaction.atomic
def set_main_image(
    *,
    owner_model,
    owner_id,
    image_model,
    owner_field,
    image_id,
):
    owner = get_object_or_404(
        owner_model.objects.select_for_update(),
        pk=owner_id,
    )

    images = image_model.objects.filter(
        **{owner_field: owner}
    )

    image = get_object_or_404(
        images,
        pk=image_id,
    )

    images.filter(
        is_main=True
    ).exclude(
        pk=image.pk
    ).update(is_main=False)

    if not image.is_main:
        image.is_main = True
        image.save(update_fields=["is_main"])

    return image


@transaction.atomic
def delete_image(
    *,
    owner_model,
    owner_id,
    image_model,
    owner_field,
    image_id,
    published_field,
):
    owner = get_object_or_404(
        owner_model.objects.select_for_update(),
        pk=owner_id,
    )

    images = image_model.objects.filter(
        **{owner_field: owner}
    )

    image = get_object_or_404(
        images,
        pk=image_id,
    )

    remaining = images.exclude(pk=image.pk)

    if (
        getattr(owner, published_field)
        and not remaining.exists()
    ):
        raise ValidationError({
            "image": (
                "Cannot delete the last image "
                "of a published item."
            )
        })

    filename = image.image.name
    storage = image.image.storage

    image.delete()

    remaining = image_model.objects.filter(
        **{owner_field: owner}
    )

    main_image = (
        remaining.filter(is_main=True)
        .order_by("pk")
        .first()
        or remaining.order_by("pk").first()
    )

    if main_image is not None:
        remaining.filter(
            is_main=True
        ).exclude(
            pk=main_image.pk
        ).update(is_main=False)

        if not main_image.is_main:
            remaining.filter(
                pk=main_image.pk
            ).update(is_main=True)

    transaction.on_commit(
        lambda filename=filename, storage=storage:
            delete_unused_image_file(
                filename=filename,
                storage=storage,
            )
    )
