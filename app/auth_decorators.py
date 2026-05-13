from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse

def login_required_for_action(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            next_url = request.get_full_path()
            login_url = f"{reverse('auth:login')}?next={next_url}"
            return redirect(login_url)
        return view_func(request, *args, **kwargs)
    return wrapper

class LoginRequiredForActionMixin:

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            next_url = request.get_full_path()
            login_url = f"{reverse('auth:login')}?next={next_url}"
            return redirect(login_url)
        return super().dispatch(request, *args, **kwargs)
