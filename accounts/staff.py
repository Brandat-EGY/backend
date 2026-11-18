from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission

STORE_STAFF_GROUP = "موظف المتجر"

STORE_STAFF_PERMISSIONS = (
    "brandat_egy.view_order",
    "brandat_egy.view_product",
    "brandat_egy.add_product",
    "brandat_egy.change_product",
    "brandat_egy.delete_product",
    "brandat_egy.view_productvariant",
    "brandat_egy.add_productvariant",
    "brandat_egy.change_productvariant",
    "brandat_egy.delete_productvariant",
    "brandat_egy.view_productimage",
    "brandat_egy.add_productimage",
    "brandat_egy.change_productimage",
    "brandat_egy.delete_productimage",
    "brandat_egy.view_box",
    "brandat_egy.add_box",
    "brandat_egy.change_box",
    "brandat_egy.delete_box",
    "brandat_egy.view_boxitem",
    "brandat_egy.add_boxitem",
    "brandat_egy.change_boxitem",
    "brandat_egy.delete_boxitem",
    "brandat_egy.view_boximage",
    "brandat_egy.add_boximage",
    "brandat_egy.change_boximage",
    "brandat_egy.delete_boximage",
    "brandat_egy.view_category",
    "brandat_egy.add_category",
    "brandat_egy.change_category",
    "brandat_egy.view_brand",
    "brandat_egy.add_brand",
    "brandat_egy.change_brand",
)


def store_staff_group():
    group, _created = Group.objects.get_or_create(name=STORE_STAFF_GROUP)
    wanted = []
    for label in STORE_STAFF_PERMISSIONS:
        app_label, codename = label.split(".", 1)
        permission = Permission.objects.filter(
            content_type__app_label=app_label,
            codename=codename,
        ).first()
        if permission is not None:
            wanted.append(permission)
    group.permissions.set(wanted)
    return group
