"""TeleCRM Backend — apps/superadmin/decorators.py"""
from functools import wraps
from django.http import HttpResponseForbidden

def superadmin_only(view_func):
    """Decorator: allow only Django superusers."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not (request.user and request.user.is_authenticated and request.user.is_superuser):
            return HttpResponseForbidden("Super admin access required.")
        return view_func(request, *args, **kwargs)
    return wrapper
