from django.db.models import F, TextField, Value
from django.db.models.functions import Lower, Replace


ARABIC_REPLACEMENTS = (
    ("أ", "ا"),
    ("إ", "ا"),
    ("آ", "ا"),
    ("ٱ", "ا"),
    ("ى", "ي"),
    ("ة", "ه"),
    ("ؤ", "و"),
    ("ئ", "ي"),
    ("ـ", ""),
    *(
        (chr(code), "")
        for code in range(0x064B, 0x0660)
    ),
    ("\u0670", ""),
)


def normalize_search_text(text):
    text = text.strip().lower()

    for old, new in ARABIC_REPLACEMENTS:
        text = text.replace(old, new)

    return " ".join(text.split())


def normalized_text_expression(field_name):
    expression = Lower(F(field_name))

    for old, new in ARABIC_REPLACEMENTS:
        expression = Replace(
            expression,
            Value(old),
            Value(new),
            output_field=TextField(),
        )

    return expression
