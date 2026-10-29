from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db.models import F
from django.db.models.deletion import ProtectedError
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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
from .permissions import IsITStaff, IsITStaffOrReadOnly, TicketPermission
from .roles import is_it_staff
from .serializers import (
    AssetSerializer,
    AssignmentSerializer,
    CategorySerializer,
    ConsumableSerializer,
    DepartmentSerializer,
    EmployeeSerializer,
    ServiceTicketSerializer,
    StockMovementSerializer,
    VendorSerializer,
)


class SafeDeleteMixin:
    """Return 409 instead of a server error when related rows block the delete."""

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "This record is used by other records, so it can't be deleted."},
                status=status.HTTP_409_CONFLICT,
            )


class CategoryViewSet(SafeDeleteMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsITStaffOrReadOnly]


class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = [IsITStaffOrReadOnly]


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsITStaffOrReadOnly]


class EmployeeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Employee.objects.select_related("user", "department")
    serializer_class = EmployeeSerializer
    permission_classes = [IsITStaff]


class AssetViewSet(SafeDeleteMixin, viewsets.ModelViewSet):
    serializer_class = AssetSerializer
    permission_classes = [IsITStaffOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "serial_number", "model"]
    ordering_fields = ["name", "purchase_date", "warranty_expiry"]

    def get_queryset(self):
        queryset = Asset.objects.select_related("category")
        if not is_it_staff(self.request.user):
            queryset = queryset.filter(
                assignments__employee__user=self.request.user,
                assignments__returned_date__isnull=True,
            )
        # simple filters: /api/assets/?status=in_stock&category=1
        status_value = self.request.query_params.get("status")
        category = self.request.query_params.get("category")
        if status_value:
            queryset = queryset.filter(status=status_value)
        if category:
            queryset = queryset.filter(category_id=category)
        return queryset

    @action(detail=False, url_path="warranty-expiring")
    def warranty_expiring(self, request):
        """Assets whose warranty ends in the next N days (default 60)."""
        try:
            days = int(request.query_params.get("days", 60))
        except ValueError:
            days = 60
        today = date.today()
        assets = (
            self.get_queryset()
            .exclude(status=Asset.RETIRED)
            .filter(warranty_expiry__gte=today, warranty_expiry__lte=today + timedelta(days=days))
            .order_by("warranty_expiry")
        )
        return Response(self.get_serializer(assets, many=True).data)


class AssignmentViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    serializer_class = AssignmentSerializer
    permission_classes = [IsITStaffOrReadOnly]

    def get_queryset(self):
        queryset = Assignment.objects.select_related("asset", "employee__user")
        if not is_it_staff(self.request.user):
            queryset = queryset.filter(employee__user=self.request.user)
        return queryset

    @action(detail=True, methods=["post"], url_path="return")
    def return_asset(self, request, pk=None):
        assignment = self.get_object()
        try:
            assignment.mark_returned()
        except ValidationError as error:
            return Response({"detail": error.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(assignment).data)


class ServiceTicketViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceTicketSerializer
    permission_classes = [TicketPermission]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "asset__serial_number"]

    def get_queryset(self):
        queryset = ServiceTicket.objects.select_related("asset", "raised_by")
        if not is_it_staff(self.request.user):
            queryset = queryset.filter(raised_by=self.request.user)
        for name in ("status", "priority"):
            value = self.request.query_params.get(name)
            if value:
                queryset = queryset.filter(**{name: value})
        return queryset

    def perform_create(self, serializer):
        if is_it_staff(self.request.user):
            serializer.save(raised_by=self.request.user)
        else:
            # employees can't set status or notes themselves
            serializer.save(raised_by=self.request.user, status=ServiceTicket.OPEN, notes="")


class ConsumableViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Consumable.objects.select_related("category")
    serializer_class = ConsumableSerializer
    permission_classes = [IsITStaff]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "sku"]

    @action(detail=False, url_path="low-stock")
    def low_stock(self, request):
        """Consumables at or below their reorder level."""
        items = self.get_queryset().filter(quantity__lte=F("reorder_level"))
        return Response(self.get_serializer(items, many=True).data)


class StockMovementViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                           viewsets.GenericViewSet):
    queryset = StockMovement.objects.select_related("consumable", "created_by")
    serializer_class = StockMovementSerializer
    permission_classes = [IsITStaff]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
