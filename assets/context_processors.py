from .roles import is_it_staff


def roles(request):
    """Makes is_staff_user available in every template (used by the navbar)."""
    return {"is_staff_user": is_it_staff(request.user)}
