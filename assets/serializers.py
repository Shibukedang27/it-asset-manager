from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import (
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
from .roles import is_it_staff


class CleanOnCreateMixin:
    """Run the model's clean() so the API follows the same rules as forms and admin.
    Only used for create-only serializers (Assignment, StockMovement)."""

    def validate(self, attrs):
        try:
            self.Meta.model(**attrs).clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages)
        return attrs


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "description"]


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ["id", "name", "email", "phone"]


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name"]


class EmployeeSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    name = serializers.CharField(source="__str__", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)

    class Meta:
        model = Employee
        fields = ["id", "username", "name", "employee_code", "department", "department_name", "phone"]


class AssetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    under_warranty = serializers.BooleanField(read_only=True)

    class Meta:
        model = Asset
        fields = [
            "id", "name", "model", "serial_number", "category", "category_name", "vendor",
            "status", "purchase_date", "warranty_expiry", "under_warranty", "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate(self, attrs):
        # fall back to the saved values when a PATCH only sends one of the dates
        purchase = attrs.get("purchase_date", getattr(self.instance, "purchase_date", None))
        expiry = attrs.get("warranty_expiry", getattr(self.instance, "warranty_expiry", None))
        if purchase and expiry and expiry < purchase:
            raise serializers.ValidationError("Warranty cannot end before the purchase date.")
        return attrs


class AssignmentSerializer(CleanOnCreateMixin, serializers.ModelSerializer):
    asset_name = serializers.CharField(source="asset.__str__", read_only=True)
    employee_name = serializers.CharField(source="employee.__str__", read_only=True)

    class Meta:
        model = Assignment
        fields = [
            "id", "asset", "asset_name", "employee", "employee_name",
            "issued_date", "returned_date", "notes",
        ]
        read_only_fields = ["returned_date"]  # use the return endpoint


class ServiceTicketSerializer(serializers.ModelSerializer):
    raised_by = serializers.CharField(source="raised_by.username", read_only=True)
    asset_serial = serializers.CharField(source="asset.serial_number", read_only=True)

    class Meta:
        model = ServiceTicket
        fields = [
            "id", "asset", "asset_serial", "raised_by", "title", "description",
            "priority", "status", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_asset(self, asset):
        # employees can only raise tickets for assets they currently hold
        user = self.context["request"].user
        if not is_it_staff(user):
            holds_it = asset.assignments.filter(employee__user=user, returned_date__isnull=True).exists()
            if not holds_it:
                raise serializers.ValidationError("You can only raise tickets for assets assigned to you.")
        return asset


class ConsumableSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Consumable
        fields = ["id", "name", "sku", "category", "vendor", "quantity", "reorder_level", "is_low_stock"]
        read_only_fields = ["quantity"]  # changes only through stock movements


class StockMovementSerializer(CleanOnCreateMixin, serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", read_only=True, default=None)

    class Meta:
        model = StockMovement
        fields = ["id", "consumable", "movement_type", "quantity", "note", "created_by", "created_at"]
        read_only_fields = ["created_at"]
