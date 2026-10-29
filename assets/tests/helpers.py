from datetime import date, timedelta

from django.contrib.auth.models import Group, User

from assets.models import Asset, Category, Consumable, Employee
from assets.roles import EMPLOYEE_GROUP, IT_STAFF_GROUP

PASSWORD = "test-pass-123"


def make_user(username, group=EMPLOYEE_GROUP, code=None):
    """Create a user with an Employee profile in the given group."""
    user = User.objects.create_user(username, f"{username}@example.com", PASSWORD)
    user.groups.add(Group.objects.get(name=group))
    Employee.objects.create(user=user, employee_code=code or username.upper())
    return user


def make_staff(username="staff"):
    return make_user(username, IT_STAFF_GROUP)


def make_category(name="Laptop"):
    return Category.objects.get_or_create(name=name)[0]


def make_asset(serial="SN-001", **kwargs):
    kwargs.setdefault("name", "Test laptop")
    kwargs.setdefault("category", make_category())
    return Asset.objects.create(serial_number=serial, **kwargs)


def make_consumable(sku="CAB-1", quantity=0, reorder_level=5):
    """Quantity is set through the db directly because movements are tested separately."""
    item = Consumable.objects.create(name="Cable", sku=sku, category=make_category("Accessories"),
                                     reorder_level=reorder_level)
    Consumable.objects.filter(pk=item.pk).update(quantity=quantity)
    item.refresh_from_db()
    return item


def days_from_now(days):
    return date.today() + timedelta(days=days)
