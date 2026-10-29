from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("assets/", views.AssetListView.as_view(), name="asset-list"),
    path("assets/add/", views.AssetCreateView.as_view(), name="asset-create"),
    path("assets/<int:pk>/", views.AssetDetailView.as_view(), name="asset-detail"),
    path("assets/<int:pk>/edit/", views.AssetUpdateView.as_view(), name="asset-update"),
    path("assets/<int:pk>/delete/", views.AssetDeleteView.as_view(), name="asset-delete"),
    path("assignments/", views.AssignmentListView.as_view(), name="assignment-list"),
    path("assignments/add/", views.AssignmentCreateView.as_view(), name="assignment-create"),
    path("assignments/<int:pk>/return/", views.AssignmentReturnView.as_view(), name="assignment-return"),
    path("tickets/", views.TicketListView.as_view(), name="ticket-list"),
    path("tickets/add/", views.TicketCreateView.as_view(), name="ticket-create"),
    path("tickets/<int:pk>/", views.TicketDetailView.as_view(), name="ticket-detail"),
    path("tickets/<int:pk>/edit/", views.TicketUpdateView.as_view(), name="ticket-update"),
    path("consumables/", views.ConsumableListView.as_view(), name="consumable-list"),
    path("consumables/add/", views.ConsumableCreateView.as_view(), name="consumable-create"),
    path("stock/", views.StockMovementListView.as_view(), name="movement-list"),
    path("stock/add/", views.StockMovementCreateView.as_view(), name="movement-create"),
]
