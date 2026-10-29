from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.urls import reverse


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Vendor(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Employee(models.Model):
    """Profile attached to a login user. Assets are assigned to employees."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee")
    employee_code = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["employee_code"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Asset(models.Model):
    IN_STOCK = "in_stock"
    ASSIGNED = "assigned"
    IN_REPAIR = "in_repair"
    RETIRED = "retired"
    STATUS_CHOICES = [
        (IN_STOCK, "In stock"),
        (ASSIGNED, "Assigned"),
        (IN_REPAIR, "In repair"),
        (RETIRED, "Retired"),
    ]

    name = models.CharField(max_length=150)
    model = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=80, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="assets")
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="assets")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=IN_STOCK)
    purchase_date = models.DateField(null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "serial_number"]

    def __str__(self):
        return f"{self.name} ({self.serial_number})"

    def get_absolute_url(self):
        return reverse("asset-detail", args=[self.pk])

    @property
    def under_warranty(self):
        return self.warranty_expiry is not None and self.warranty_expiry >= date.today()

    def current_assignment(self):
        """The open assignment (not returned yet), or None."""
        return self.assignments.filter(returned_date__isnull=True).first()

    def clean(self):
        if self.purchase_date and self.warranty_expiry and self.warranty_expiry < self.purchase_date:
            raise ValidationError("Warranty cannot end before the purchase date.")


class Assignment(models.Model):
    """An asset given to an employee. returned_date stays empty while they have it."""

    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="assignments")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="assignments")
    issued_date = models.DateField(default=date.today)
    returned_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-issued_date", "-id"]

    def __str__(self):
        return f"{self.asset.serial_number} -> {self.employee}"

    @property
    def is_active(self):
        return self.returned_date is None

    def clean(self):
        # Only check on create; later edits (like marking returned) are fine.
        if self.pk is None and self.asset_id and self.asset.status != Asset.IN_STOCK:
            raise ValidationError(f"{self.asset} is not in stock, so it cannot be assigned.")
        if self.returned_date and self.returned_date < self.issued_date:
            raise ValidationError("Returned date cannot be before the issued date.")

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new:
                self.asset.status = Asset.ASSIGNED
                self.asset.save(update_fields=["status"])

    def mark_returned(self, when=None):
        """Close the assignment and put the asset back in stock."""
        if not self.is_active:
            raise ValidationError("This asset was already returned.")
        with transaction.atomic():
            self.returned_date = when or date.today()
            self.save()
            # an asset that went to repair keeps that status
            if self.asset.status == Asset.ASSIGNED:
                self.asset.status = Asset.IN_STOCK
                self.asset.save(update_fields=["status"])


class ServiceTicket(models.Model):
    """A repair or support request raised against an asset."""

    LOW, MEDIUM, HIGH, URGENT = "low", "medium", "high", "urgent"
    PRIORITY_CHOICES = [(LOW, "Low"), (MEDIUM, "Medium"), (HIGH, "High"), (URGENT, "Urgent")]

    OPEN, IN_PROGRESS, RESOLVED, CLOSED = "open", "in_progress", "resolved", "closed"
    STATUS_CHOICES = [
        (OPEN, "Open"),
        (IN_PROGRESS, "In progress"),
        (RESOLVED, "Resolved"),
        (CLOSED, "Closed"),
    ]

    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="tickets")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tickets")
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=MEDIUM)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=OPEN)
    notes = models.TextField(blank=True, help_text="Work done / resolution notes (IT staff).")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.pk} {self.title}"

    def get_absolute_url(self):
        return reverse("ticket-detail", args=[self.pk])

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sync_asset_status()

    def sync_asset_status(self):
        """Keep the asset status in line with the ticket."""
        asset = self.asset
        if asset.status == Asset.RETIRED:
            return
        if self.status == self.IN_PROGRESS and asset.status != Asset.IN_REPAIR:
            asset.status = Asset.IN_REPAIR
            asset.save(update_fields=["status"])
        elif self.status in (self.RESOLVED, self.CLOSED) and asset.status == Asset.IN_REPAIR:
            # back to the person who has it, or back to the shelf
            has_owner = asset.current_assignment() is not None
            asset.status = Asset.ASSIGNED if has_owner else Asset.IN_STOCK
            asset.save(update_fields=["status"])


class Consumable(models.Model):
    """Things we count instead of track one by one: cables, toner, mice..."""

    name = models.CharField(max_length=150)
    sku = models.CharField("SKU", max_length=40, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="consumables")
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="consumables")
    quantity = models.PositiveIntegerField(default=0)  # changed only through StockMovement
    reorder_level = models.PositiveIntegerField(default=5)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_level


class StockMovement(models.Model):
    """Stock in/out for a consumable. Saving one updates Consumable.quantity."""

    IN, OUT = "IN", "OUT"
    TYPE_CHOICES = [(IN, "Stock in"), (OUT, "Stock out")]

    consumable = models.ForeignKey(Consumable, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=3, choices=TYPE_CHOICES)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.movement_type} {self.quantity} x {self.consumable.sku}"

    def clean(self):
        if self.pk is None and self.consumable_id and self.movement_type == self.OUT:
            if self.quantity and self.quantity > self.consumable.quantity:
                raise ValidationError(
                    f"Not enough stock: only {self.consumable.quantity} of {self.consumable.sku} left."
                )

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Stock movements cannot be edited.")
        with transaction.atomic():
            # lock the row so two requests can't both take the last items
            item = Consumable.objects.select_for_update().get(pk=self.consumable_id)
            if self.movement_type == self.IN:
                item.quantity += self.quantity
            elif self.quantity > item.quantity:
                raise ValidationError(f"Not enough stock: only {item.quantity} of {item.sku} left.")
            else:
                item.quantity -= self.quantity
            item.save(update_fields=["quantity"])
            super().save(*args, **kwargs)
