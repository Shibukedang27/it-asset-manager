from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("categories", api.CategoryViewSet, basename="category")
router.register("vendors", api.VendorViewSet, basename="vendor")
router.register("departments", api.DepartmentViewSet, basename="department")
router.register("employees", api.EmployeeViewSet, basename="employee")
router.register("assets", api.AssetViewSet, basename="asset")
router.register("assignments", api.AssignmentViewSet, basename="assignment")
router.register("tickets", api.ServiceTicketViewSet, basename="ticket")
router.register("consumables", api.ConsumableViewSet, basename="consumable")
router.register("stock-movements", api.StockMovementViewSet, basename="stockmovement")

urlpatterns = [
    path("token/", obtain_auth_token, name="api-token"),
    path("", include(router.urls)),
]
