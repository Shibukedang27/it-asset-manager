from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from assets.models import Asset, Assignment, ServiceTicket, StockMovement

from .helpers import PASSWORD, days_from_now, make_asset, make_category, make_consumable, make_staff, make_user


class TokenAndAuthTests(APITestCase):
    def test_anonymous_gets_401_or_403(self):
        response = self.client.get("/api/assets/")
        self.assertIn(response.status_code, (401, 403))

    def test_get_token_and_use_it(self):
        make_staff("staff")
        response = self.client.post("/api/token/", {"username": "staff", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
        self.assertEqual(self.client.get("/api/assets/").status_code, 200)

    def test_bad_password_gets_no_token(self):
        make_staff("staff")
        response = self.client.post("/api/token/", {"username": "staff", "password": "wrong"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Token.objects.count(), 0)


class AssetApiTests(APITestCase):
    def setUp(self):
        self.staff = make_staff()
        self.anita = make_user("anita")
        self.laptop = make_asset("LAP-1", name="Dell laptop", warranty_expiry=days_from_now(20))
        self.monitor = make_asset("MON-1", name="LG monitor", warranty_expiry=days_from_now(300))
        Assignment.objects.create(asset=self.laptop, employee=self.anita.employee)

    def test_staff_lists_all_and_pagination_shape(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get("/api/assets/")
        self.assertEqual(response.data["count"], 2)
        self.assertIn("results", response.data)

    def test_search_and_status_filter(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/assets/", {"search": "lg"}).data["count"], 1)
        self.assertEqual(self.client.get("/api/assets/", {"status": "assigned"}).data["count"], 1)

    def test_employee_only_sees_own_assets_and_cannot_write(self):
        self.client.force_authenticate(self.anita)
        response = self.client.get("/api/assets/")
        self.assertEqual([a["serial_number"] for a in response.data["results"]], ["LAP-1"])
        self.assertEqual(self.client.get(f"/api/assets/{self.monitor.pk}/").status_code, 404)
        create = self.client.post("/api/assets/", {"name": "x", "serial_number": "X", "category": self.laptop.category_id})
        self.assertEqual(create.status_code, 403)

    def test_staff_creates_asset(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post("/api/assets/", {
            "name": "New", "serial_number": "NEW-1", "category": make_category().pk,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "in_stock")

    def test_duplicate_serial_is_rejected(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post("/api/assets/", {
            "name": "Copy", "serial_number": "LAP-1", "category": make_category().pk,
        })
        self.assertEqual(response.status_code, 400)

    def test_warranty_before_purchase_is_rejected(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post("/api/assets/", {
            "name": "Odd", "serial_number": "ODD-1", "category": make_category().pk,
            "purchase_date": str(days_from_now(0)), "warranty_expiry": str(days_from_now(-3)),
        })
        self.assertEqual(response.status_code, 400)

    def test_warranty_expiring_endpoint(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get("/api/assets/warranty-expiring/", {"days": 30})
        self.assertEqual([a["serial_number"] for a in response.data], ["LAP-1"])

    def test_delete_asset_with_history_gives_409(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.delete(f"/api/assets/{self.laptop.pk}/").status_code, 409)
        self.assertEqual(self.client.delete(f"/api/assets/{self.monitor.pk}/").status_code, 204)


class AssignmentApiTests(APITestCase):
    def setUp(self):
        self.staff = make_staff()
        self.anita = make_user("anita")
        self.asset = make_asset()
        self.client.force_authenticate(self.staff)

    def test_assign_and_return(self):
        response = self.client.post("/api/assignments/", {
            "asset": self.asset.pk, "employee": self.anita.employee.pk,
        })
        self.assertEqual(response.status_code, 201)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.ASSIGNED)

        done = self.client.post(f"/api/assignments/{response.data['id']}/return/")
        self.assertEqual(done.status_code, 200)
        self.assertIsNotNone(done.data["returned_date"])
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.IN_STOCK)

    def test_cannot_assign_asset_twice(self):
        data = {"asset": self.asset.pk, "employee": self.anita.employee.pk}
        self.client.post("/api/assignments/", data)
        self.assertEqual(self.client.post("/api/assignments/", data).status_code, 400)

    def test_return_twice_gives_400(self):
        assignment = Assignment.objects.create(asset=self.asset, employee=self.anita.employee)
        self.client.post(f"/api/assignments/{assignment.pk}/return/")
        self.assertEqual(self.client.post(f"/api/assignments/{assignment.pk}/return/").status_code, 400)

    def test_employee_sees_only_own_and_cannot_assign(self):
        Assignment.objects.create(asset=self.asset, employee=self.anita.employee)
        other = make_user("suresh")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get("/api/assignments/").data["count"], 0)
        response = self.client.post("/api/assignments/", {"asset": self.asset.pk, "employee": other.employee.pk})
        self.assertEqual(response.status_code, 403)


class TicketApiTests(APITestCase):
    def setUp(self):
        self.staff = make_staff()
        self.anita = make_user("anita")
        self.suresh = make_user("suresh")
        self.asset = make_asset()
        Assignment.objects.create(asset=self.asset, employee=self.anita.employee)
        self.other_asset = make_asset("SN-2")

    def test_employee_raises_ticket_and_cannot_set_status(self):
        self.client.force_authenticate(self.anita)
        response = self.client.post("/api/tickets/", {
            "asset": self.asset.pk, "title": "Broken hinge", "status": "closed", "notes": "hacked",
        })
        self.assertEqual(response.status_code, 201)
        ticket = ServiceTicket.objects.get()
        self.assertEqual(ticket.raised_by, self.anita)
        self.assertEqual(ticket.status, ServiceTicket.OPEN)
        self.assertEqual(ticket.notes, "")

    def test_employee_cannot_raise_ticket_for_someone_elses_asset(self):
        self.client.force_authenticate(self.anita)
        response = self.client.post("/api/tickets/", {"asset": self.other_asset.pk, "title": "Not mine"})
        self.assertEqual(response.status_code, 400)

    def test_employee_cannot_update_or_delete(self):
        ticket = ServiceTicket.objects.create(asset=self.asset, raised_by=self.anita, title="T")
        self.client.force_authenticate(self.anita)
        self.assertEqual(self.client.patch(f"/api/tickets/{ticket.pk}/", {"status": "closed"}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/tickets/{ticket.pk}/").status_code, 403)

    def test_employee_sees_only_own_tickets(self):
        ServiceTicket.objects.create(asset=self.asset, raised_by=self.anita, title="Mine")
        ServiceTicket.objects.create(asset=self.other_asset, raised_by=self.suresh, title="Theirs")
        self.client.force_authenticate(self.anita)
        titles = [t["title"] for t in self.client.get("/api/tickets/").data["results"]]
        self.assertEqual(titles, ["Mine"])

    def test_staff_updates_status_and_asset_follows(self):
        ticket = ServiceTicket.objects.create(asset=self.asset, raised_by=self.anita, title="T")
        self.client.force_authenticate(self.staff)
        response = self.client.patch(f"/api/tickets/{ticket.pk}/", {"status": "in_progress"})
        self.assertEqual(response.status_code, 200)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.IN_REPAIR)

    def test_filter_by_priority(self):
        ServiceTicket.objects.create(asset=self.asset, raised_by=self.anita, title="A", priority="urgent")
        ServiceTicket.objects.create(asset=self.asset, raised_by=self.anita, title="B", priority="low")
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/tickets/", {"priority": "urgent"}).data["count"], 1)


class ConsumableApiTests(APITestCase):
    def setUp(self):
        self.staff = make_staff()
        self.client.force_authenticate(self.staff)

    def test_low_stock_endpoint(self):
        make_consumable("LOW", quantity=1, reorder_level=5)
        make_consumable("FINE", quantity=40, reorder_level=5)
        response = self.client.get("/api/consumables/low-stock/")
        self.assertEqual([c["sku"] for c in response.data], ["LOW"])

    def test_quantity_cannot_be_set_directly(self):
        response = self.client.post("/api/consumables/", {
            "name": "Mouse", "sku": "MS-1", "category": make_category("Accessories").pk, "quantity": 99,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["quantity"], 0)

    def test_stock_movements_change_quantity(self):
        item = make_consumable(quantity=5)
        self.client.post("/api/stock-movements/", {"consumable": item.pk, "movement_type": "IN", "quantity": 5})
        self.client.post("/api/stock-movements/", {"consumable": item.pk, "movement_type": "OUT", "quantity": 3})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 7)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_negative_stock_is_rejected(self):
        item = make_consumable(quantity=2)
        response = self.client.post("/api/stock-movements/", {
            "consumable": item.pk, "movement_type": "OUT", "quantity": 5,
        })
        self.assertEqual(response.status_code, 400)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_zero_quantity_is_rejected(self):
        item = make_consumable(quantity=2)
        response = self.client.post("/api/stock-movements/", {
            "consumable": item.pk, "movement_type": "IN", "quantity": 0,
        })
        self.assertEqual(response.status_code, 400)

    def test_movements_cannot_be_edited_or_deleted(self):
        item = make_consumable(quantity=2)
        movement = StockMovement.objects.create(consumable=item, movement_type="IN", quantity=1)
        self.assertEqual(self.client.patch(f"/api/stock-movements/{movement.pk}/", {"quantity": 9}).status_code, 405)
        self.assertEqual(self.client.delete(f"/api/stock-movements/{movement.pk}/").status_code, 405)

    def test_employee_has_no_access(self):
        self.client.force_authenticate(make_user("anita"))
        self.assertEqual(self.client.get("/api/consumables/").status_code, 403)
        self.assertEqual(self.client.get("/api/stock-movements/").status_code, 403)
        self.assertEqual(self.client.get("/api/employees/").status_code, 403)
