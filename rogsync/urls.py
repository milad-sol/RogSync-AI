"""
URL configuration for RogSync AI.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("sync_app.urls")),
]
