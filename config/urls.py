from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from workspace import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("admin/", admin.site.urls),
    path("", views.home, name="home"),
    path("studio/", views.studio, name="studio"),
    path("builder/", views.document_builder, name="builder"),
    # Put the fixed POST endpoint before the slug route, otherwise "process" is parsed as a tool slug.
    path("tools/process/", views.process_tool, name="process_tool"),
    path("tools/<slug:slug>/", views.tool_page, name="tool_page"),
    path("library/", views.library, name="library"),
    path("library/<int:pk>/download/", views.download_document, name="download_document"),
    path("library/<int:pk>/delete/", views.delete_document, name="delete_document"),
    path("assistant/", views.assistant, name="assistant"),
    path("history/", views.history, name="history"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/register/", views.register, name="register"),
]
