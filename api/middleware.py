from django.http import HttpResponseForbidden


class SuperuserAdminOnlyMiddleware:
    """Allow Django admin pages only for users with role=superuser."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin/'):
            user = getattr(request, 'user', None)

            # Let unauthenticated users reach the admin login page.
            if user and user.is_authenticated and getattr(user, 'role', None) != 'superuser':
                return HttpResponseForbidden('Admin access is restricted to superuser role.')

        return self.get_response(request)
