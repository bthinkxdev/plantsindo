from urllib.parse import urlencode

def _sanitize_tag_value(value):
    if value is None:
        return None
    value = str(value).strip()
    if value == '':
        return None
    value = value.replace('&', '_')
    value = value.replace('=', '_')
    value = value.replace('/', '_')
    value = value.replace('#', '')
    value = value[:256]
    return value if value else None

def _sanitize_tag_key(key):
    if key is None:
        return None
    key = str(key).strip()
    if key == '':
        return None
    key = key.replace('&', '_').replace('=', '_').replace('/', '_')
    key = key[:128]
    return key

def build_safe_tags(tag_dict):
    if not tag_dict:
        return ''
    cleaned = {}
    for key, value in tag_dict.items():
        skey = _sanitize_tag_key(key)
        sval = _sanitize_tag_value(value)
        if skey and sval is not None:
            assert len(sval) <= 256, 'Tag value must be <= 256 chars'
            assert sval != '', 'Tag value cannot be empty'
            cleaned[skey] = sval
    return urlencode(cleaned) if cleaned else ''

def validate_tag_value(value):
    assert value is not None, 'Tag value cannot be None'
    s = str(value).strip()
    assert s != '', 'Tag value cannot be empty'
    assert len(s) <= 256, 'Tag value must be <= 256 chars'
