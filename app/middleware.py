from django.conf import settings
from django.db import connection

class EnsureGuestSessionMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(request, 'user', None) or not request.user.is_authenticated:
            if not request.session.session_key:
                request.session.create()
        return self.get_response(request)

class DebugTraceMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'DEBUG_TRACE', False):
            connection.force_debug_cursor = True
        try:
            return self.get_response(request)
        finally:
            if getattr(settings, 'DEBUG_TRACE', False):
                connection.force_debug_cursor = False
