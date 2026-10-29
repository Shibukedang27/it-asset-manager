"""Role helpers. Roles are plain Django Groups, so they can be managed in the admin."""

IT_STAFF_GROUP = "IT Staff"
EMPLOYEE_GROUP = "Employee"


def is_it_staff(user):
    """Admins (superusers) and members of the 'IT Staff' group manage everything."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name=IT_STAFF_GROUP).exists()
