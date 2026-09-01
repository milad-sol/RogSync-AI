with open('sync_app/admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    'from .models import ApiSettings, ProductSync, PromptTemplate',
    'from .models import AiSettings, ApiSettings, ProductSync, PromptTemplate'
)

new_admin = """
@admin.register(AiSettings)
class AiSettingsAdmin(admin.ModelAdmin):
    \"\"\"Singleton admin — prevents adding more than one instance.\"\"\"

    def has_add_permission(self, request):
        return not AiSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
"""
content += new_admin

with open('sync_app/admin.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated admin.py successfully.")
