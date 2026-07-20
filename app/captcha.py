import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

_VERIFY_URLS = {
    'turnstile': 'https://challenges.cloudflare.com/turnstile/v0/siteverify',
    'hcaptcha': 'https://api.hcaptcha.com/siteverify',
}


class CaptchaError(Exception):
    pass


def captcha_required() -> bool:
    return bool(getattr(settings, 'CAPTCHA_SECRET', '').strip())


def extract_captcha_token(request) -> str:
    if request is None:
        return ''
    for key in ('captcha_token', 'cf-turnstile-response', 'h-captcha-response'):
        value = ''
        if hasattr(request, 'POST'):
            value = (request.POST.get(key) or '').strip()
        if not value and hasattr(request, 'data'):
            value = (request.data.get(key) or '').strip()
        if value:
            return value
    return ''


def verify_captcha(token: str, *, remote_ip: str | None = None) -> None:
    secret = getattr(settings, 'CAPTCHA_SECRET', '').strip()
    if not secret:
        return

    token = (token or '').strip()
    if not token:
        raise CaptchaError('Captcha verification is required.')

    provider = (getattr(settings, 'CAPTCHA_PROVIDER', 'turnstile') or 'turnstile').strip().lower()
    verify_url = _VERIFY_URLS.get(provider, _VERIFY_URLS['turnstile'])
    payload = {'secret': secret, 'response': token}
    if remote_ip:
        payload['remoteip'] = remote_ip

    body = urllib.parse.urlencode(payload).encode('utf-8')
    request = urllib.request.Request(
        verify_url,
        data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.exception('Captcha verification request failed')
        raise CaptchaError('Captcha verification is temporarily unavailable.') from exc

    if not data.get('success'):
        raise CaptchaError('Captcha verification failed. Please try again.')
