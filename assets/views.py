from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, F, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .forms import (
    AssetForm,
    AssignmentForm,
    ConsumableForm,
    SignUpForm,
    StockMovementForm,
    TicketForm,
    TicketUpdateForm,
)
from .models import Asset, Assignment, Category, Consumable, ServiceTicket, StockMovement
from .roles import is_it_staff


class ITStaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only admins and IT Staff. Other logged in users get a 403 page."""

    def test_func(self):
        return is_it_staff(self.request.user)


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("dashboard")

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)  # log them in straight after signup
        return redirect(self.success_url)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "assets/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_staff_user"] = is_it_staff(user)
        if context["is_staff_user"]:
            counts = Asset.objects.values("status").annotate(total=Count("id"))
            by_status = {row["status"]: row["total"] for row in counts}
            context["status_counts"] = [
                (label, by_status.get(code, 0)) for code, label in Asset.STATUS_CHOICES
            ]
            context["low_stock"] = Consumable.objects.filter(quantity__lte=F("reorder_level"))
            soon = date.today() + timedelta(days=60)
            context["warranty_soon"] = (
                Asset.objects.exclude(status=Asset.RETIRED)
                .filter(warranty_expiry__gte=date.today(), warranty_expiry__lte=soon)
                .order_by("warranty_expiry")
            )
            context["open_tickets"] = ServiceTicket.objects.filter(
                status__in=[ServiceTicket.OPEN, ServiceTicket.IN_PROGRESS]
            ).select_related("asset")[:10]
        else:
            context["my_assets"] = Asset.objects.filter(
                assignments__employee__user=user, assignments__returned_date__isnull=True
            )
            context["my_tickets"] = ServiceTicket.objects.filter(raised_by=user)[:10]
        return context


# ---------- Assets ----------

class AssetQuerysetMixin:
    """IT staff see every asset, employees only the ones they currently hold."""

    def get_queryset(self):
        queryset = Asset.objects.select_related("category", "vendor")
        if not is_it_staff(self.request.user):
            queryset = queryset.filter(
                assignments__employee__user=self.request.user,
                assignments__returned_date__isnull=True,
            )
        return queryset


class AssetListView(LoginRequiredMixin, AssetQuerysetMixin, ListView):
    template_name = "assets/asset_list.html"
    context_object_name = "assets"
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "")
        category = self.request.GET.get("category", "")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(serial_number__icontains=search) | Q(model__icontains=search)
            )
        if status:
            queryset = queryset.filter(status=status)
        if category:
            queryset = queryset.filter(category_id=category)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.all()
        context["status_choices"] = Asset.STATUS_CHOICES
        context["q"] = self.request.GET.get("q", "")
        context["selected_status"] = self.request.GET.get("status", "")
        context["selected_category"] = self.request.GET.get("category", "")
        return context


class AssetDetailView(LoginRequiredMixin, AssetQuerysetMixin, DetailView):
    template_name = "assets/asset_detail.html"
    context_object_name = "asset"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["assignments"] = self.object.assignments.select_related("employee__user")
        context["tickets"] = self.object.tickets.all()
        return context


class AssetCreateView(ITStaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Asset
    form_class = AssetForm
    template_name = "assets/form.html"
    success_message = "Asset added."
    extra_context = {"title": "Add asset"}


class AssetUpdateView(ITStaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Asset
    form_class = AssetForm
    template_name = "assets/form.html"
    success_message = "Asset updated."
    extra_context = {"title": "Edit asset"}


class AssetDeleteView(ITStaffRequiredMixin, DeleteView):
    model = Asset
    template_name = "assets/confirm_delete.html"
    success_url = reverse_lazy("asset-list")

    def form_valid(self, form):
        # assets with assignments or tickets are PROTECTed, so deleting can fail
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, "This asset has assignments or tickets, so it can't be deleted.")
            return redirect("asset-detail", pk=self.object.pk)
        messages.success(self.request, "Asset deleted.")
        return response


# ---------- Assignments ----------

class AssignmentListView(LoginRequiredMixin, ListView):
    template_name = "assets/assignment_list.html"
    context_object_name = "assignments"
    paginate_by = 10

    def get_queryset(self):
        queryset = Assignment.objects.select_related("asset", "employee__user")
        if not is_it_staff(self.request.user):
            queryset = queryset.filter(employee__user=self.request.user)
        if self.request.GET.get("active"):
            queryset = queryset.filter(returned_date__isnull=True)
        return queryset


class AssignmentCreateView(ITStaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Assignment
    form_class = AssignmentForm
    template_name = "assets/form.html"
    success_url = reverse_lazy("assignment-list")
    success_message = "Asset assigned."
    extra_context = {"title": "Assign asset"}


class AssignmentReturnView(ITStaffRequiredMixin, View):
    """POST only: mark an assignment as returned."""

    http_method_names = ["post"]

    def post(self, request, pk):
        assignment = get_object_or_404(Assignment, pk=pk)
        try:
            assignment.mark_returned()
            messages.success(request, f"{assignment.asset} returned to stock.")
        except ValidationError as error:
            messages.error(request, error.message)
        return redirect("assignment-list")


# ---------- Tickets ----------

class TicketQuerysetMixin:
    def get_queryset(self):
        queryset = ServiceTicket.objects.select_related("asset", "raised_by")
        if not is_it_staff(self.request.user):
            queryset = queryset.filter(raised_by=self.request.user)
        return queryset


class TicketListView(LoginRequiredMixin, TicketQuerysetMixin, ListView):
    template_name = "assets/ticket_list.html"
    context_object_name = "tickets"
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "")
        priority = self.request.GET.get("priority", "")
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(asset__serial_number__icontains=search))
        if status:
            queryset = queryset.filter(status=status)
        if priority:
            queryset = queryset.filter(priority=priority)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = ServiceTicket.STATUS_CHOICES
        context["priority_choices"] = ServiceTicket.PRIORITY_CHOICES
        context["q"] = self.request.GET.get("q", "")
        context["selected_status"] = self.request.GET.get("status", "")
        context["selected_priority"] = self.request.GET.get("priority", "")
        return context


class TicketDetailView(LoginRequiredMixin, TicketQuerysetMixin, DetailView):
    template_name = "assets/ticket_detail.html"
    context_object_name = "ticket"


class TicketCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = ServiceTicket
    form_class = TicketForm
    template_name = "assets/form.html"
    success_url = reverse_lazy("ticket-list")
    success_message = "Ticket raised."
    extra_context = {"title": "Raise a ticket"}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user  # limits the asset choices
        return kwargs

    def form_valid(self, form):
        form.instance.raised_by = self.request.user
        return super().form_valid(form)


class TicketUpdateView(ITStaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = ServiceTicket
    form_class = TicketUpdateForm
    template_name = "assets/form.html"
    success_message = "Ticket updated."
    extra_context = {"title": "Update ticket"}


# ---------- Consumables ----------

class ConsumableListView(ITStaffRequiredMixin, ListView):
    template_name = "assets/consumable_list.html"
    context_object_name = "consumables"
    paginate_by = 10

    def get_queryset(self):
        queryset = Consumable.objects.select_related("category")
        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        if self.request.GET.get("low"):
            queryset = queryset.filter(quantity__lte=F("reorder_level"))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        context["low_only"] = bool(self.request.GET.get("low"))
        return context


class ConsumableCreateView(ITStaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Consumable
    form_class = ConsumableForm
    template_name = "assets/form.html"
    success_url = reverse_lazy("consumable-list")
    success_message = "Item added. Use stock in to add quantity."
    extra_context = {"title": "Add consumable"}


class StockMovementListView(ITStaffRequiredMixin, ListView):
    template_name = "assets/movement_list.html"
    context_object_name = "movements"
    paginate_by = 15
    queryset = StockMovement.objects.select_related("consumable", "created_by")


class StockMovementCreateView(ITStaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = StockMovement
    form_class = StockMovementForm
    template_name = "assets/form.html"
    success_url = reverse_lazy("movement-list")
    success_message = "Stock updated."
    extra_context = {"title": "Stock in / out"}

    def get_initial(self):
        # the list page links here with ?consumable=<id>
        return {"consumable": self.request.GET.get("consumable")}

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)
