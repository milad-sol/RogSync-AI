"""
RogSync AI — sync_app URL Configuration
"""
from django.urls import path

from . import views

app_name = "sync_app"

urlpatterns = [
    # Dashboard
    path("", views.dashboard_view, name="dashboard"),

    # Products
    path("products/", views.product_list_view, name="product_list"),
    path("products/<int:pk>/review/", views.product_review_view, name="product_review"),

    # Prompt Templates
    path("prompts/", views.prompt_list_view, name="prompt_list"),
    path("prompts/create/", views.prompt_create_view, name="prompt_create"),
    path("prompts/<int:pk>/activate/", views.prompt_activate_view, name="prompt_activate"),
    path("prompts/<int:pk>/delete/", views.prompt_delete_view, name="prompt_delete"),

    # API Settings
    path("settings/", views.api_settings_view, name="api_settings"),
    path("settings/ai/", views.ai_settings_view, name="ai_settings"),

    # HTMX action endpoints
    path("products/<int:pk>/approve/", views.approve_product_view, name="approve_product"),
    path("products/<int:pk>/regenerate/", views.regenerate_ai_view, name="regenerate_ai"),
    path("products/<int:pk>/update-fields/", views.update_product_fields_view, name="update_fields"),
    path("fetch-products/", views.fetch_products_view, name="fetch_products"),
]
