from django.urls import path

from .views import ChangePasswordView, LoginView, RefreshView

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
]
