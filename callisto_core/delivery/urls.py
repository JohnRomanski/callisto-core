from django.urls import re_path, reverse_lazy
from django.views.generic import base as django_views

from callisto_core.reporting import views as reporting_views

from . import views as delivery_views

urlpatterns = [
    # record flow
    re_path(
        r"^$",
        django_views.RedirectView.as_view(url=reverse_lazy("report_new")),
        name="report_index",
    ),
    re_path(
        r"^new/$",
        delivery_views.ReportCreateView.as_view(success_url="report_update"),
        name="report_new",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/wizard/step/(?P<step>.+)/$",
        delivery_views.EncryptedWizardView.as_view(),
        name="report_update",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/wizard/step/done/$",
        delivery_views.WizardReviewView.as_view(),
        name="report_view",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/review/pdf/view/$",
        delivery_views.ViewPDFView.as_view(),
        name="report_pdf_view",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/review/pdf/download/$",
        delivery_views.DownloadPDFView.as_view(),
        name="report_pdf_download",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/delete/$",
        delivery_views.ReportDeleteView.as_view(
            back_url="dashboard", success_url=reverse_lazy("dashboard_report_deleted")
        ),
        name="report_delete",
    ),
    # # /end record flow
    # # review and submission flow
    re_path(
        r"^uuid/(?P<uuid>.+)/reporting/confirmation/$",
        reporting_views.ReportingSchoolEmailFormView.as_view(
            back_url="dashboard",
            next_url="reporting_prep",
            success_url="email_confirmation_response",
        ),
        name="reporting_email_confirmation",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/reporting/confirmation/uidb64/(?P<uidb64>.+)/token/(?P<token>.+)/$",
        reporting_views.ReportingSchoolEmailConfirmationView.as_view(
            back_url="dashboard", next_url="reporting_prep"
        ),
        name="reporting_email_confirmation",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/reporting/prep/$",
        reporting_views.ReportingPrepView.as_view(
            back_url="dashboard", reporting_success_url="reporting_matching_enter"
        ),
        name="reporting_prep",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/reporting/matching/$",
        reporting_views.ReportingMatchingView.as_view(
            back_url="reporting_prep", reporting_success_url="reporting_end_step"
        ),
        name="reporting_matching_enter",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/reporting/end/$",
        reporting_views.ReportingConfirmationView.as_view(
            back_url="reporting_matching_enter", success_url=reverse_lazy("dashboard")
        ),
        name="reporting_end_step",
    ),
    # /reporting
    # resubmit
    re_path(
        r"^uuid/(?P<uuid>.+)/resubmit/prep/$",
        reporting_views.ResubmitPrepView.as_view(
            back_url="dashboard", reporting_success_url="resubmit_end_step"
        ),
        name="resubmit_prep",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/resubmit/end/$",
        reporting_views.ResubmitConfirmationView.as_view(
            back_url="resubmit_prep", success_url=reverse_lazy("dashboard")
        ),
        name="resubmit_end_step",
    ),
    # /resubmit
    # matching
    re_path(
        r"^uuid/(?P<uuid>.+)/matching/confirmation/$",
        reporting_views.MatchingSchoolEmailFormView.as_view(
            back_url="dashboard",
            next_url="matching_prep",
            success_url="email_confirmation_response",
        ),
        name="matching_email_confirmation",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/matching/confirmation/uidb64/(?P<uidb64>.+)/token/(?P<token>.+)/$",
        reporting_views.MatchingSchoolEmailConfirmationView.as_view(
            back_url="dashboard", next_url="matching_prep"
        ),
        name="matching_email_confirmation",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/matching/prep/$",
        reporting_views.MatchingPrepView.as_view(
            back_url="dashboard", reporting_success_url="matching_enter"
        ),
        name="matching_prep",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/matching/enter/$",
        reporting_views.MatchingEnterView.as_view(
            back_url="matching_prep", success_url=reverse_lazy("dashboard")
        ),
        name="matching_enter",
    ),
    re_path(
        r"^uuid/(?P<uuid>.+)/matching/withdraw/$",
        reporting_views.MatchingWithdrawView.as_view(
            back_url="matching_prep",
            success_url=reverse_lazy("dashboard_matching_withdrawn"),
        ),
        name="matching_withdraw",
    ),
    # # / matching
    # dashboard views
    re_path(r"^dashboard/$", delivery_views.DashboardView.as_view(), name="dashboard"),
    re_path(
        r"^dashboard/report_deleted/$",
        delivery_views.DashboardReportDeletedView.as_view(),
        name="dashboard_report_deleted",
    ),
    re_path(
        r"^dashboard/matching_withdrawn/$",
        delivery_views.DashboardMatchingWithdrawnView.as_view(),
        name="dashboard_matching_withdrawn",
    ),
    re_path(
        r"^dashboard/confirmation/$",
        django_views.TemplateView.as_view(
            template_name="callisto_core/accounts/school_email_sent.html"
        ),
        name="email_confirmation_response",
    ),
    # / dashboard views
]
