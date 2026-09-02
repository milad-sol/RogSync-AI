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
    path("prompts/<int:pk>/update/", views.prompt_update_view, name="prompt_update"),
    path("prompts/<int:pk>/activate/", views.prompt_activate_view, name="prompt_activate"),
    path("prompts/<int:pk>/delete/", views.prompt_delete_view, name="prompt_delete"),

    # API Settings
    path("settings/", views.api_settings_view, name="api_settings"),
    path("settings/ai/", views.ai_settings_view, name="ai_settings"),

    # Keywords Management
    path("keywords/", views.keyword_list_view, name="keyword_list"),
    path("keywords/create/", views.keyword_create_view, name="keyword_create"),
    path("keywords/<int:pk>/toggle/", views.keyword_toggle_view, name="keyword_toggle"),
    path("keywords/<int:pk>/delete/", views.keyword_delete_view, name="keyword_delete"),

    # HTMX action endpoints
    path("products/<int:pk>/approve/", views.approve_product_view, name="approve_product"),
    path("products/<int:pk>/regenerate/", views.regenerate_ai_view, name="regenerate_ai"),
    path("products/<int:pk>/row/", views.product_row_view, name="product_row"),
    path("products/<int:pk>/update-fields/", views.update_product_fields_view, name="update_fields"),
    path("products/<int:pk>/update-content/", views.update_product_content_view, name="update_content"),
    path("products/<int:pk>/images/", views.update_product_images_view, name="update_images"),
    path("extract/", views.extract_products_view, name="extract_products"),
    path("fetch-products/", views.fetch_products_view, name="fetch_products"),
]
