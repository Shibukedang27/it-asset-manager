from django.contrib import admin

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


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone")
    search_fields = ("name", "email")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_code", "user", "department", "phone")
    list_filter = ("department",)
    search_fields = ("employee_code", "user__username", "user__first_name", "user__last_name")


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("name", "serial_number", "model", "category", "status", "warranty_expiry")
    list_filter = ("status", "category", "vendor")
    search_fields = ("name", "serial_number", "model")
    date_hierarchy = "purchase_date"


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("asset", "employee", "issued_date", "returned_date")
    list_filter = ("issued_date", "returned_date")
    search_fields = ("asset__serial_number", "asset__name", "employee__user__username")


@admin.register(ServiceTicket)
class ServiceTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "asset", "raised_by", "priority", "status", "created_at")
    list_filter = ("status", "priority")
    search_fields = ("title", "asset__serial_number", "raised_by__username")


@admin.register(Consumable)
class ConsumableAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "quantity", "reorder_level")
    list_filter = ("category", "vendor")
    search_fields = ("name", "sku")
    readonly_fields = ("quantity",)  # use stock movements to change it


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("consumable", "movement_type", "quantity", "created_by", "created_at")
    list_filter = ("movement_type",)
    search_fields = ("consumable__name", "consumable__sku")

    def has_change_permission(self, request, obj=None):
        return False  # history should not be edited

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        super().save_model(request, obj, form, change)
