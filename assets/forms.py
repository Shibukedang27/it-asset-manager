from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, User

from .models import Asset, Assignment, Consumable, Department, Employee, ServiceTicket, StockMovement
from .roles import EMPLOYEE_GROUP, is_it_staff


class BootstrapMixin:
    """Add bootstrap css classes to every field widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "form-select"
            else:
                widget.attrs["class"] = "form-control"


class DateInput(forms.DateInput):
    input_type = "date"


class SignUpForm(BootstrapMixin, UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    employee_code = forms.CharField(max_length=20)
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def clean_employee_code(self):
        code = self.cleaned_data["employee_code"]
        if Employee.objects.filter(employee_code=code).exists():
            raise forms.ValidationError("This employee code is already used.")
        return code

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            # every new signup is a normal employee
            user.groups.add(Group.objects.get(name=EMPLOYEE_GROUP))
            Employee.objects.create(
                user=user,
                employee_code=self.cleaned_data["employee_code"],
                department=self.cleaned_data["department"],
            )
        return user


class AssetForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Asset
        fields = [
            "name", "model", "serial_number", "category", "vendor",
            "status", "purchase_date", "warranty_expiry",
        ]
        widgets = {"purchase_date": DateInput(), "warranty_expiry": DateInput()}


class AssignmentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ["asset", "employee", "issued_date", "notes"]
        widgets = {"issued_date": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # only things on the shelf can be handed out
        self.fields["asset"].queryset = Asset.objects.filter(status=Asset.IN_STOCK)


class TicketForm(BootstrapMixin, forms.ModelForm):
    """Used to raise a ticket. Employees can only pick assets they hold."""

    class Meta:
        model = ServiceTicket
        fields = ["asset", "title", "description", "priority"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and not is_it_staff(user):
            self.fields["asset"].queryset = Asset.objects.filter(
                assignments__employee__user=user, assignments__returned_date__isnull=True
            )


class TicketUpdateForm(BootstrapMixin, forms.ModelForm):
    """IT staff use this to change status, priority and notes."""

    class Meta:
        model = ServiceTicket
        fields = ["status", "priority", "notes"]


class ConsumableForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Consumable
        fields = ["name", "sku", "category", "vendor", "reorder_level"]


class StockMovementForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ["consumable", "movement_type", "quantity", "note"]
