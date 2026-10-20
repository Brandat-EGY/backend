
from django.db.models import (
    Case,
    Exists,
    IntegerField,
    OuterRef,
    Q,
    Value,
    When,
    FloatField
)
from django.contrib.postgres.search import TrigramWordSimilarity
from django.db.models.functions import Coalesce, Greatest


from .models import ProductVariant
from .catalog_normalization import (
    normalize_search_text,
    normalized_text_expression,
)



FUZZY_NAME_THRESHOLD = 0.30
FUZZY_BRAND_THRESHOLD = 0.40


def fuzzy_word_score(term, field_name):
    return Coalesce(
        TrigramWordSimilarity(term, field_name),
        Value(0.0),
        output_field=FloatField(),
    )


def apply_product_search(queryset, search):
    search = search.strip()

    if not search:
        return queryset


    normalized_search = normalize_search_text(search)

    queryset = queryset.annotate(
        normalized_name_ar=normalized_text_expression(
            "name_ar"
        ),
        normalized_brand_ar=normalized_text_expression(
            "brand__name_ar"
        ),
        normalized_category_ar=normalized_text_expression(
            "category__name_ar"
        ),
        normalized_description_ar=normalized_text_expression(
            "description_ar"
        ),
    )



    terms = search.split()

    score = Value(
        0,
        output_field=IntegerField(),
    )

    for index, term in enumerate(terms):
        normalized_term = normalize_search_text(term)
        variant_match_name = f"_variant_match_{index}"

        variant_matches = (
            ProductVariant.objects.filter(
                product_id=OuterRef("pk"),
                is_active=True,
            )
            .annotate(
                normalized_shade_ar=normalized_text_expression(
                    "shade_ar"
                )
            )
            .filter(
                Q(sku__icontains=term)
                | Q(size__icontains=term)
                | Q(
                    normalized_shade_ar__contains=normalized_term
                )
                | Q(shade_en__icontains=term)
            )
        )

        queryset = queryset.annotate(
            **{
                variant_match_name: Exists(
                    variant_matches
                )
            }
        )


        fuzzy_name_key = f"_fuzzy_name_{index}"
        fuzzy_brand_key = f"_fuzzy_brand_{index}"

        use_fuzzy = (
            len(normalized_term) >= 4
            and normalized_term.isalpha()
        )


        if use_fuzzy:
            queryset = queryset.annotate(
                **{
                    fuzzy_name_key: Greatest(
                        fuzzy_word_score(
                            normalized_term,
                            "normalized_name_ar",
                        ),
                        fuzzy_word_score(
                            term,
                            "name_en",
                        ),
                        output_field=FloatField(),
                    ),
                    fuzzy_brand_key: Greatest(
                        fuzzy_word_score(
                            normalized_term,
                            "normalized_brand_ar",
                        ),
                        fuzzy_word_score(
                            term,
                            "brand__name_en",
                        ),
                        output_field=FloatField(),
                    ),
                }
            )


        name_match = (
            Q(normalized_name_ar__contains=normalized_term)
            | Q(name_en__icontains=term)
        )

        brand_match = (
            Q(normalized_brand_ar__contains=normalized_term)
            | Q(brand__name_en__icontains=term)
        )

        category_match = (
            Q(normalized_category_ar__contains=normalized_term)
            | Q(category__name_en__icontains=term)
        )

        description_match = (
            Q(normalized_description_ar__contains=normalized_term)
            | Q(description_en__icontains=term)
        )


        variant_match = Q(
            **{variant_match_name: True}
        )

        # Every search term must match at least one field.
       
        match_condition = (
            name_match
            | brand_match
            | category_match
            | description_match
            | variant_match
        )

        if use_fuzzy:
            match_condition |= (
                Q(**{
                    f"{fuzzy_name_key}__gte":
                        FUZZY_NAME_THRESHOLD
                })
                | Q(**{
                    f"{fuzzy_brand_key}__gte":
                        FUZZY_BRAND_THRESHOLD
                })
            )

        queryset = queryset.filter(match_condition)


        fuzzy_cases = []

        if use_fuzzy:
            fuzzy_cases = [
                When(
                    **{
                        f"{fuzzy_name_key}__gte":
                            FUZZY_NAME_THRESHOLD
                    },
                    then=Value(9),
                ),
                When(
                    **{
                        f"{fuzzy_brand_key}__gte":
                            FUZZY_BRAND_THRESHOLD
                    },
                    then=Value(6),
                ),
            ]


        term_score = Case(
            When(
                Q(normalized_name_ar__exact=normalized_term)
                | Q(name_en__iexact=term),
                then=Value(50),
            ),
            When(
                Q(normalized_name_ar__startswith=normalized_term)
                | Q(name_en__istartswith=term),
                then=Value(35),
            ),
            When(
                name_match,
                then=Value(25),
            ),
            When(
                brand_match,
                then=Value(15),
            ),
            When(
                category_match,
                then=Value(10),
            ),
            When(
                variant_match,
                then=Value(8),
            ),
            *fuzzy_cases,
            When(
                description_match,
                then=Value(2),
            ),
            default=Value(0),
            output_field=IntegerField(),
        )

        score = score + term_score

    # Give an additional boost to complete name matches.
    phrase_bonus = Case(
        When(
            Q(normalized_name_ar__exact=normalized_search)
            | Q(name_en__iexact=search),
            then=Value(100),
        ),
        When(
            Q(normalized_name_ar__startswith=normalized_search)
            | Q(name_en__istartswith=search),
            then=Value(50),
        ),
        default=Value(0),
        output_field=IntegerField(),
    )

    return queryset.annotate(
        search_score=score + phrase_bonus
    )
