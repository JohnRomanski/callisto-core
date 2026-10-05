"""

docs / reference:
    - https://docs.djangoproject.com/en/1.11/topics/http/urls/

"""

from decorator_include import decorator_include

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, re_path, reverse_lazy
from django.views.generic import base as django_views

from callisto_core.accounts import views as account_views

urlpatterns = [
    # includes
    re_path(r"^account/", include("callisto_core.accounts.urls")),
    re_path(
        r"^reports/", decorator_include(login_required, "callisto_core.delivery.urls")
    ),
    # login / signup
    re_path(r"^$", django_views.RedirectView.as_view(url=reverse_lazy("signup"))),
    re_path(
        r"^signup/$", django_views.RedirectView.as_view(url=reverse_lazy("signup"))
    ),
    # LogoutView only accepts POST; a redirect would turn it into a GET
    re_path(r"^logout/$", account_views.LogoutView.as_view()),
    re_path(r"^login/$", django_views.RedirectView.as_view(url=reverse_lazy("login"))),
    # admin
    re_path(r"^nested_admin/", include("nested_admin.urls")),
    re_path(r"^admin/", admin.site.urls),
]
