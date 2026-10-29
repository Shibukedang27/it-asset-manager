from django.core.exceptions import ValidationError
from django.test import TestCase

from assets.models import Asset, Assignment, ServiceTicket, StockMovement

from .helpers import days_from_now, make_asset, make_consumable, make_user


class AssetTests(TestCase):
    def test_new_asset_is_in_stock(self):
        self.assertEqual(make_asset().status, Asset.IN_STOCK)

    def test_under_warranty(self):
        self.assertTrue(make_asset("A1", warranty_expiry=days_from_now(10)).under_warranty)
        self.assertFalse(make_asset("A2", warranty_expiry=days_from_now(-10)).under_warranty)
        self.assertFalse(make_asset("A3").under_warranty)

    def test_warranty_before_purchase_is_invalid(self):
        asset = make_asset(purchase_date=days_from_now(0), warranty_expiry=days_from_now(-5))
        with self.assertRaises(ValidationError):
            asset.clean()


class AssignmentTests(TestCase):
    def setUp(self):
        self.asset = make_asset()
        self.employee = make_user("anita").employee

    def test_assigning_sets_asset_status(self):
        Assignment.objects.create(asset=self.asset, employee=self.employee)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.ASSIGNED)

    def test_cannot_assign_asset_that_is_not_in_stock(self):
        Assignment.objects.create(asset=self.asset, employee=self.employee)
        self.asset.refresh_from_db()
        second = Assignment(asset=self.asset, employee=self.employee)
        with self.assertRaises(ValidationError):
            second.clean()

    def test_return_puts_asset_back_in_stock(self):
        assignment = Assignment.objects.create(asset=self.asset, employee=self.employee)
        assignment.mark_returned()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.IN_STOCK)
        self.assertFalse(assignment.is_active)

    def test_cannot_return_twice(self):
        assignment = Assignment.objects.create(asset=self.asset, employee=self.employee)
        assignment.mark_returned()
        with self.assertRaises(ValidationError):
            assignment.mark_returned()


class TicketTests(TestCase):
    def setUp(self):
        self.user = make_user("anita")
        self.asset = make_asset()
        Assignment.objects.create(asset=self.asset, employee=self.user.employee)

    def make_ticket(self, **kwargs):
        return ServiceTicket.objects.create(asset=self.asset, raised_by=self.user, title="Broken screen", **kwargs)

    def test_in_progress_moves_asset_to_repair(self):
        self.make_ticket(status=ServiceTicket.IN_PROGRESS)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.IN_REPAIR)

    def test_resolved_ticket_gives_asset_back_to_owner(self):
        ticket = self.make_ticket(status=ServiceTicket.IN_PROGRESS)
        ticket.status = ServiceTicket.RESOLVED
        ticket.save()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.ASSIGNED)

    def test_resolved_ticket_on_unassigned_asset_goes_to_stock(self):
        self.asset.assignments.get().mark_returned()
        self.asset.status = Asset.IN_REPAIR
        self.asset.save()
        ticket = self.make_ticket(status=ServiceTicket.RESOLVED)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.IN_STOCK)
        self.assertEqual(ticket.status, ServiceTicket.RESOLVED)


class StockMovementTests(TestCase):
    def test_stock_in_adds_quantity(self):
        item = make_consumable(quantity=5)
        StockMovement.objects.create(consumable=item, movement_type=StockMovement.IN, quantity=10)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 15)

    def test_stock_out_subtracts_quantity(self):
        item = make_consumable(quantity=5)
        StockMovement.objects.create(consumable=item, movement_type=StockMovement.OUT, quantity=2)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

    def test_cannot_go_negative(self):
        item = make_consumable(quantity=2)
        movement = StockMovement(consumable=item, movement_type=StockMovement.OUT, quantity=3)
        with self.assertRaises(ValidationError):
            movement.clean()
        with self.assertRaises(ValidationError):
            movement.save()
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_movement_cannot_be_edited(self):
        item = make_consumable(quantity=2)
        movement = StockMovement.objects.create(consumable=item, movement_type=StockMovement.IN, quantity=1)
        movement.quantity = 50
        with self.assertRaises(ValidationError):
            movement.save()

    def test_low_stock_flag(self):
        self.assertTrue(make_consumable("A", quantity=5, reorder_level=5).is_low_stock)
        self.assertFalse(make_consumable("B", quantity=6, reorder_level=5).is_low_stock)
