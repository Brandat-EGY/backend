from uuid import uuid4


def generate_variant_sku():
    return f"BE-V-{uuid4().hex.upper()}"
