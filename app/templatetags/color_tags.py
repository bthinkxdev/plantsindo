import json
from django import template
import webcolors
import re
register = template.Library()

@register.filter
def to_json(value):
    if value is None:
        return '[]'
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return '[]'

@register.filter
def image_urls_json(queryset_or_list):
    if not queryset_or_list:
        return '[]'
    try:
        urls = []
        for item in queryset_or_list:
            if hasattr(item, 'image') and getattr(item.image, 'url', None):
                urls.append(item.image.url)
            elif hasattr(item, 'url'):
                urls.append(item.url)
        return json.dumps(urls)
    except (TypeError, ValueError):
        return '[]'
EXTENDED_COLORS = {'olive green': '#6B8E23', 'dark olive green': '#556B2F', 'light olive green': '#A4D65E', 'navy green': '#35530a', 'forest': '#228B22', 'light forest': '#32CD32'}

@register.filter
def color_to_hex(color_name):
    if not color_name:
        return '#FFFFFF'
    color_str = str(color_name).strip()
    if color_str.startswith('#'):
        if re.match('^#[0-9A-Fa-f]{6}$', color_str) or re.match('^#[0-9A-Fa-f]{3}$', color_str):
            return color_str
    color_lower = color_str.lower()
    if color_lower in EXTENDED_COLORS:
        return EXTENDED_COLORS[color_lower]
    try:
        hex_code = webcolors.name_to_hex(color_lower)
        return hex_code
    except ValueError:
        pass
    color_no_spaces = color_lower.replace(' ', '')
    try:
        hex_code = webcolors.name_to_hex(color_no_spaces)
        return hex_code
    except ValueError:
        pass
    color_underscored = color_lower.replace(' ', '_')
    try:
        hex_code = webcolors.name_to_hex(color_underscored)
        return hex_code
    except ValueError:
        pass
    return '#FFFFFF'
