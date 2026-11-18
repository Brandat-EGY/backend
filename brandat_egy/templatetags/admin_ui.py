from django import template

register = template.Library()


@register.simple_tag
def page_query(request, page):
    params = request.GET.copy()
    if page <= 0:
        params.pop("p", None)
    else:
        params["p"] = page
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"
