import json
from django.utils.safestring import mark_safe
from django import template
register = template.Library()

@register.filter
def price_inr(value):
    if value is None:
        return '₹ 0'
    try:
        n = int(float(value))
        s = str(n)
        if len(s) > 3:
            parts = []
            while s:
                parts.append(s[-3:])
                s = s[:-3]
            s = ','.join(reversed(parts))
        return f'₹ {s}'
    except (TypeError, ValueError):
        return '₹ 0'

@register.filter
def whatsapp_number(value):
    if not value:
        return ''
    digits = ''.join((c for c in str(value) if c.isdigit()))
    if len(digits) == 10:
        return '91' + digits
    return digits if digits else ''

@register.filter
def first(value):
    if value is None:
        return None
    try:
        return list(value)[0] if value else None
    except (TypeError, IndexError):
        return None

@register.filter
def to_json(value):
    if value is None:
        return mark_safe('[]')
    try:
        out = json.dumps(value)
        return mark_safe(out)
    except (TypeError, ValueError):
        return mark_safe('[]')
