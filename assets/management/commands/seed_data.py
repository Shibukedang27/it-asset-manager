from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from assets.models import (
    Asset,
    Assignment,
    Category,
    Consumable,
    Department,
    Employee,
    ServiceTicket,
    StockMovement,
    Vendor,
)
from assets.roles import EMPLOYEE_GROUP, IT_STAFF_GROUP

DEMO_PASSWORD = "demo12345"  # demo accounts only


class Command(BaseCommand):
    help = "Create sample data for trying the app (safe to run more than once)."

    def handle(self, *args, **options):
        if Asset.objects.exists():
            self.stdout.write("Data already there, nothing to do.")
            return

        categories = {n: Category.objects.create(name=n) for n in ["Laptop", "Desktop", "Monitor", "Networking", "Printer", "Accessories"]}
        vendors = {n: Vendor.objects.create(name=n, email=f"sales@{n.lower().split()[0]}.example.com")
                   for n in ["Ameerpet Computers", "Hitech Traders", "Sri Sai Networks"]}
        departments = {n: Department.objects.create(name=n) for n in ["Engineering", "HR", "Accounts", "Support"]}

        # users: one admin, one IT staff member and a few employees
        User.objects.create_superuser("admin", "admin@example.com", DEMO_PASSWORD)
        staff = self.make_user("itstaff", "Ravi", "Kumar", "E001", departments["Support"], IT_STAFF_GROUP)
        people = [
            self.make_user("anita", "Anita", "Reddy", "E002", departments["Engineering"], EMPLOYEE_GROUP),
            self.make_user("suresh", "Suresh", "Babu", "E003", departments["Accounts"], EMPLOYEE_GROUP),
            self.make_user("meena", "Meena", "Rao", "E004", departments["HR"], EMPLOYEE_GROUP),
        ]

        today = date.today()
        rows = [
            ("Dell Latitude 5440", "Latitude 5440", "DL5440-001", "Laptop", "Ameerpet Computers", 400, 300),
            ("Dell Latitude 5440", "Latitude 5440", "DL5440-002", "Laptop", "Ameerpet Computers", 400, 300),
            ("HP ProBook 450", "ProBook 450 G9", "HP450-001", "Laptop", "Hitech Traders", 700, 20),
            ("HP ProBook 450", "ProBook 450 G9", "HP450-002", "Laptop", "Hitech Traders", 700, 40),
            ("Lenovo ThinkCentre", "M70q", "LT-M70-001", "Desktop", "Hitech Traders", 500, 200),
            ("Dell 24 inch Monitor", "P2422H", "DM-P24-001", "Monitor", "Ameerpet Computers", 300, 200),
            ("Dell 24 inch Monitor", "P2422H", "DM-P24-002", "Monitor", "Ameerpet Computers", 300, 45),
            ("TP-Link 24 port switch", "TL-SG1024", "TPL-SW-001", "Networking", "Sri Sai Networks", 200, 100),
            ("Epson L3250 printer", "L3250", "EP-L3250-001", "Printer", "Sri Sai Networks", 900, 10),
            ("Old HP desktop", "Compaq 6200", "HP-OLD-001", "Desktop", "Hitech Traders", 2000, -500),
        ]
        assets = []
        for name, model, serial, cat, vendor, bought_days_ago, warranty_in in rows:
            assets.append(Asset.objects.create(
                name=name, model=model, serial_number=serial,
                category=categories[cat], vendor=vendors[vendor],
                purchase_date=today - timedelta(days=bought_days_ago),
                warranty_expiry=today + timedelta(days=warranty_in),
            ))
        assets[-1].status = Asset.RETIRED
        assets[-1].save()

        # hand out a few assets
        for asset, person in zip([assets[0], assets[2], assets[3], assets[5]], [people[0], people[1], people[2], people[0]]):
            Assignment.objects.create(asset=asset, employee=person.employee)

        ServiceTicket.objects.create(
            asset=assets[0], raised_by=people[0], title="Laptop battery drains fast",
            description="Battery lasts about 40 minutes now.", priority=ServiceTicket.HIGH)
        ServiceTicket.objects.create(
            asset=assets[2], raised_by=people[1], title="Keyboard keys not working",
            priority=ServiceTicket.MEDIUM, status=ServiceTicket.IN_PROGRESS, notes="Ordered a new keyboard.")

        items = [
            ("HDMI cable 2m", "HDMI-2M", "Accessories", 25, 10),
            ("Cat6 patch cable 1m", "CAT6-1M", "Networking", 40, 15),
            ("Wireless mouse", "MOUSE-WL", "Accessories", 12, 5),
            ("Epson 003 ink bottle", "INK-E003", "Printer", 6, 4),
            ("USB-C charger 65W", "CHG-65W", "Accessories", 8, 5),
        ]
        for name, sku, cat, qty, reorder in items:
            item = Consumable.objects.create(name=name, sku=sku, category=categories[cat],
                                             vendor=vendors["Hitech Traders"], reorder_level=reorder)
            StockMovement.objects.create(consumable=item, movement_type=StockMovement.IN,
                                         quantity=qty, note="Opening stock", created_by=staff)
        # use up some stock so ink and chargers show as low
        for sku, used in [("INK-E003", 3), ("CHG-65W", 3)]:
            StockMovement.objects.create(consumable=Consumable.objects.get(sku=sku),
                                         movement_type=StockMovement.OUT, quantity=used,
                                         note="Issued to staff", created_by=staff)

        self.stdout.write(self.style.SUCCESS("Sample data created."))
        self.stdout.write(f"Logins (password {DEMO_PASSWORD}): admin, itstaff, anita, suresh, meena")

    def make_user(self, username, first, last, code, department, group_name):
        user = User.objects.create_user(username, f"{username}@example.com", DEMO_PASSWORD,
                                        first_name=first, last_name=last)
        user.groups.add(Group.objects.get(name=group_name))
        Employee.objects.create(user=user, employee_code=code, department=department)
        return user
