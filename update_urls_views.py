import re

# Update urls.py
with open('sync_app/urls.py', 'r', encoding='utf-8') as f:
    urls_content = f.read()

urls_content = urls_content.replace(
    'path("settings/", views.api_settings_view, name="api_settings"),',
    'path("settings/", views.api_settings_view, name="api_settings"),\n    path("settings/ai/", views.ai_settings_view, name="ai_settings"),'
)

with open('sync_app/urls.py', 'w', encoding='utf-8') as f:
    f.write(urls_content)

# Update views.py
with open('sync_app/views.py', 'r', encoding='utf-8') as f:
    views_content = f.read()

views_content = views_content.replace(
    'from .models import ApiSettings, ProductSync, PromptTemplate',
    'from .models import AiSettings, ApiSettings, ProductSync, PromptTemplate'
)

# prompt_create_view update
old_prompt_create = """    PromptTemplate.objects.create(
        title=request.POST.get("title", "").strip(),
        main_desc_prompt=request.POST.get("main_desc_prompt", "").strip(),
        short_desc_prompt=request.POST.get("short_desc_prompt", "").strip(),
        is_active=bool(request.POST.get("is_active")),
    )"""
new_prompt_create = """    PromptTemplate.objects.create(
        title=request.POST.get("title", "").strip(),
        main_desc_prompt=request.POST.get("main_desc_prompt", "").strip(),
        short_desc_prompt=request.POST.get("short_desc_prompt", "").strip(),
        target_keywords=request.POST.get("target_keywords", "").strip(),
        is_active=bool(request.POST.get("is_active")),
    )"""
views_content = views_content.replace(old_prompt_create, new_prompt_create)

# Remove openrouter fields from api_settings_view
views_content = re.sub(r'        settings_obj\.openrouter_api_key = .*?\n', '', views_content)
views_content = re.sub(r'        settings_obj\.openrouter_model = .*?\n', '', views_content)

# Add ai_settings_view
ai_settings_view = """
def ai_settings_view(request):
    \"\"\"Display and save AI/OpenRouter credentials.\"\"\"
    settings_obj = AiSettings.load()
    saved = False

    if request.method == "POST":
        settings_obj.openrouter_api_key = request.POST.get("openrouter_api_key", "").strip()
        settings_obj.openrouter_model = request.POST.get("openrouter_model", "").strip() or "openai/gpt-4o"
        settings_obj.global_keywords = request.POST.get("global_keywords", "").strip()
        settings_obj.save()
        saved = True

    return render(request, "sync_app/ai_settings.html", {
        "settings": settings_obj,
        "saved": saved,
    })
"""

# Insert ai_settings_view before "# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n#  HTMX Action Endpoints"
views_content = views_content.replace(
    '# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n#  HTMX Action Endpoints',
    ai_settings_view + '\n# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n#  HTMX Action Endpoints'
)

with open('sync_app/views.py', 'w', encoding='utf-8') as f:
    f.write(views_content)

print("Updated urls.py and views.py successfully.")
