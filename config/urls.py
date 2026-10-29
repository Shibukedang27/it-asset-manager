from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from assets.views import SignUpView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/signup/", SignUpView.as_view(), name="signup"),
    path("api/", include("assets.api_urls")),
    path("api-auth/", include("rest_framework.urls")),  # login for the browsable API
    path("", include("assets.urls")),
]
