from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from assets.models import Asset, Assignment, Employee, ServiceTicket, StockMovement

from .helpers import PASSWORD, make_asset, make_consumable, make_staff, make_user


class LoginRequiredTests(TestCase):
    def test_anonymous_is_sent_to_login(self):
        for name in ["dashboard", "asset-list", "ticket-list", "assignment-list", "consumable-list"]:
            response = self.client.get(reverse(name))
            self.assertRedirects(response, f"{reverse('login')}?next={reverse(name)}")


class AuthTests(TestCase):
    def test_login_and_logout(self):
        make_user("anita")
        self.assertTrue(self.client.login(username="anita", password=PASSWORD))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_signup_creates_employee_in_employee_group(self):
        response = self.client.post(reverse("signup"), {
            "username": "newbie", "first_name": "New", "last_name": "Hire", "email": "n@example.com",
            "employee_code": "E900", "password1": "a-good-pass-123", "password2": "a-good-pass-123",
        })
        self.assertRedirects(response, reverse("dashboard"))
        user = User.objects.get(username="newbie")
        self.assertTrue(user.groups.filter(name="Employee").exists())
        self.assertEqual(Employee.objects.get(user=user).employee_code, "E900")

    def test_signup_rejects_duplicate_employee_code(self):
        make_user("anita", code="E1")
        response = self.client.post(reverse("signup"), {
            "username": "other", "first_name": "O", "last_name": "T", "email": "o@example.com",
            "employee_code": "E1", "password1": "a-good-pass-123", "password2": "a-good-pass-123",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="other").exists())


class AssetViewTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.laptop = make_asset("LAP-1", name="Dell laptop")
        self.monitor = make_asset("MON-1", name="LG monitor")

    def test_staff_sees_all_assets(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("asset-list"))
        self.assertContains(response, "Dell laptop")
        self.assertContains(response, "LG monitor")

    def test_search(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("asset-list"), {"q": "dell"})
        self.assertContains(response, "Dell laptop")
        self.assertNotContains(response, "LG monitor")

    def test_status_filter(self):
        self.monitor.status = Asset.IN_REPAIR
        self.monitor.save()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("asset-list"), {"status": Asset.IN_REPAIR})
        self.assertContains(response, "LG monitor")
        self.assertNotContains(response, "Dell laptop")

    def test_pagination(self):
        for i in range(12):
            make_asset(f"BULK-{i}", name=f"Bulk {i}")
        self.client.force_login(self.staff)
        response = self.client.get(reverse("asset-list"))
        self.assertEqual(len(response.context["assets"]), 10)
        response = self.client.get(reverse("asset-list"), {"page": 2})
        self.assertEqual(len(response.context["assets"]), 4)

    def test_staff_can_create_update_delete(self):
        self.client.force_login(self.staff)
        category = self.laptop.category
        response = self.client.post(reverse("asset-create"), {
            "name": "New PC", "serial_number": "PC-9", "category": category.pk, "status": "in_stock",
        })
        asset = Asset.objects.get(serial_number="PC-9")
        self.assertRedirects(response, reverse("asset-detail", args=[asset.pk]))

        self.client.post(reverse("asset-update", args=[asset.pk]), {
            "name": "Renamed PC", "serial_number": "PC-9", "category": category.pk, "status": "in_stock",
        })
        asset.refresh_from_db()
        self.assertEqual(asset.name, "Renamed PC")

        self.client.post(reverse("asset-delete", args=[asset.pk]))
        self.assertFalse(Asset.objects.filter(pk=asset.pk).exists())

    def test_cannot_delete_asset_with_history(self):
        employee = make_user("anita").employee
        Assignment.objects.create(asset=self.laptop, employee=employee)
        self.client.force_login(self.staff)
        self.client.post(reverse("asset-delete", args=[self.laptop.pk]))
        self.assertTrue(Asset.objects.filter(pk=self.laptop.pk).exists())

    def test_employee_only_sees_own_assets(self):
        anita = make_user("anita")
        Assignment.objects.create(asset=self.laptop, employee=anita.employee)
        self.client.force_login(anita)
        response = self.client.get(reverse("asset-list"))
        self.assertContains(response, "Dell laptop")
        self.assertNotContains(response, "LG monitor")
        self.assertEqual(self.client.get(reverse("asset-detail", args=[self.monitor.pk])).status_code, 404)

    def test_employee_cannot_manage_assets(self):
        self.client.force_login(make_user("anita"))
        self.assertEqual(self.client.get(reverse("asset-create")).status_code, 403)
        self.assertEqual(self.client.post(reverse("asset-delete", args=[self.laptop.pk])).status_code, 403)
        self.assertTrue(Asset.objects.filter(pk=self.laptop.pk).exists())


class AssignmentViewTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.anita = make_user("anita")
        self.asset = make_asset()
        self.client.force_login(self.staff)

    def test_assign_then_return(self):
        self.client.post(reverse("assignment-create"), {
            "asset": self.asset.pk, "employee": self.anita.employee.pk, "issued_date": "2026-10-01",
        })
        assignment = Assignment.objects.get()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.ASSIGNED)

        self.client.post(reverse("assignment-return", args=[assignment.pk]))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.IN_STOCK)

    def test_return_needs_post(self):
        assignment = Assignment.objects.create(asset=self.asset, employee=self.anita.employee)
        self.assertEqual(self.client.get(reverse("assignment-return", args=[assignment.pk])).status_code, 405)

    def test_employee_cannot_assign(self):
        self.client.force_login(self.anita)
        self.assertEqual(self.client.get(reverse("assignment-create")).status_code, 403)


class TicketViewTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.anita = make_user("anita")
        self.suresh = make_user("suresh")
        self.asset = make_asset()
        Assignment.objects.create(asset=self.asset, employee=self.anita.employee)
        self.other_asset = make_asset("SN-002", name="Someone else's PC")

    def test_employee_raises_ticket_for_own_asset(self):
        self.client.force_login(self.anita)
        response = self.client.post(reverse("ticket-create"), {
            "asset": self.asset.pk, "title": "Screen flickers", "priority": "high",
        })
        self.assertRedirects(response, reverse("ticket-list"))
        ticket = ServiceTicket.objects.get()
        self.assertEqual(ticket.raised_by, self.anita)
        self.assertEqual(ticket.status, ServiceTicket.OPEN)

    def test_employee_cannot_raise_ticket_for_other_asset(self):
        self.client.force_login(self.anita)
        response = self.client.post(reverse("ticket-create"), {
            "asset": self.other_asset.pk, "title": "Nope", "priority": "low",
        })
        self.assertEqual(response.status_code, 200)  # form shown again with an error
        self.assertEqual(ServiceTicket.objects.count(), 0)

    def test_employee_only_sees_own_tickets(self):
        ServiceTicket.objects.create(asset=self.asset, raised_by=self.anita, title="Mine")
        theirs = ServiceTicket.objects.create(asset=self.other_asset, raised_by=self.suresh, title="Theirs")
        self.client.force_login(self.anita)
        response = self.client.get(reverse("ticket-list"))
        self.assertContains(response, "Mine")
        self.assertNotContains(response, "Theirs")
        self.assertEqual(self.client.get(reverse("ticket-detail", args=[theirs.pk])).status_code, 404)

    def test_ticket_filter_by_status(self):
        ServiceTicket.objects.create(asset=self.asset, raised_by=self.anita, title="Fresh")
        ServiceTicket.objects.create(asset=self.asset, raised_by=self.anita, title="Done", status="closed")
        self.client.force_login(self.staff)
        response = self.client.get(reverse("ticket-list"), {"status": "closed"})
        self.assertContains(response, "Done")
        self.assertNotContains(response, "Fresh")

    def test_staff_updates_ticket_and_asset_goes_to_repair(self):
        ticket = ServiceTicket.objects.create(asset=self.asset, raised_by=self.anita, title="Fan noise")
        self.client.force_login(self.staff)
        self.client.post(reverse("ticket-update", args=[ticket.pk]), {
            "status": "in_progress", "priority": "medium", "notes": "Cleaning the fan",
        })
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.IN_REPAIR)

    def test_employee_cannot_update_ticket(self):
        ticket = ServiceTicket.objects.create(asset=self.asset, raised_by=self.anita, title="Fan noise")
        self.client.force_login(self.anita)
        self.assertEqual(self.client.get(reverse("ticket-update", args=[ticket.pk])).status_code, 403)


class DashboardAndStockViewTests(TestCase):
    def setUp(self):
        self.staff = make_staff()

    def test_dashboard_lists_low_stock_only(self):
        make_consumable("LOW-1", quantity=2, reorder_level=5)
        ok_item = make_consumable("OK-1", quantity=50, reorder_level=5)
        ok_item.name = "Plenty of these"
        ok_item.save()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual([c.sku for c in response.context["low_stock"]], ["LOW-1"])

    def test_stock_movement_form_updates_quantity(self):
        item = make_consumable(quantity=5)
        self.client.force_login(self.staff)
        self.client.post(reverse("movement-create"), {
            "consumable": item.pk, "movement_type": "IN", "quantity": 10,
        })
        item.refresh_from_db()
        self.assertEqual(item.quantity, 15)
        self.assertEqual(StockMovement.objects.get().created_by, self.staff)

    def test_stock_out_more_than_available_is_rejected(self):
        item = make_consumable(quantity=3)
        self.client.force_login(self.staff)
        response = self.client.post(reverse("movement-create"), {
            "consumable": item.pk, "movement_type": "OUT", "quantity": 4,
        })
        self.assertContains(response, "Not enough stock")
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

    def test_employee_cannot_open_stock_pages(self):
        self.client.force_login(make_user("anita"))
        self.assertEqual(self.client.get(reverse("consumable-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("movement-create")).status_code, 403)
