from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("cases/", views.case_list, name="case_list"),
    path("cases/new/", views.case_create, name="case_create"),
    path("cases/export.csv", views.case_export, name="case_export"),
    path("cases/<int:case_id>/", views.case_detail, name="case_detail"),
    path("cases/<int:case_id>/evidence/", views.evidence_upload, name="evidence_upload"),
    path("evidence/<int:evidence_id>/download/", views.evidence_download, name="evidence_download"),
    path("audit/", views.audit_list, name="audit_list"),
]
