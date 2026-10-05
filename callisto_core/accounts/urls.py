from django.urls import re_path

from . import views

urlpatterns = [
    re_path(r"^signup/", views.SignupView.as_view(), name="signup"),
    re_path(r"^login/", view=views.LoginView.as_view(), name="login"),
    re_path(r"^logout/", view=views.LogoutView.as_view(), name="logout"),
    re_path(
        r"^change_password/",
        view=views.PasswordChangeView.as_view(),
        name="change_password",
    ),
    re_path(
        r"^forgot_password/$", view=views.PasswordResetView.as_view(), name="reset"
    ),
    re_path(
        r"^forgot_password/sent/$",
        view=views.PasswordForgetSentView.as_view(),
        name="password_reset_sent",
    ),
    re_path(
        r"^reset/confirm/(?P<uidb64>.+)/(?P<token>.+)/$",
        view=views.PasswordResetConfirmView.as_view(),
        name="reset_confirm",
    ),
    re_path(
        r"^activate/(?P<uidb64>.+)/(?P<token>.+)/$",
        view=views.AccountActivationView.as_view(),
        name="activate_account",
    ),
]
