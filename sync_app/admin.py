from django.contrib import admin

from .models import AiSettings, ApiSettings, ProductSync, PromptTemplate


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("title", "prompt")


@admin.register(ProductSync)
class ProductSyncAdmin(admin.ModelAdmin):
    list_display = ("source_id", "title", "target_sku", "prompt_template", "product_type", "status", "updated_at")
    list_filter = ("status", "product_type", "prompt_template")
    search_fields = ("title", "source_id", "target_sku")
    readonly_fields = ("source_id", "created_at", "updated_at")


@admin.register(ApiSettings)
class ApiSettingsAdmin(admin.ModelAdmin):
    """Singleton admin — prevents adding more than one instance."""

    def has_add_permission(self, request):
        return not ApiSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(AiSettings)
class AiSettingsAdmin(admin.ModelAdmin):
    """Singleton admin — prevents adding more than one instance."""

    def has_add_permission(self, request):
        return not AiSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
