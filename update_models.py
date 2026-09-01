with open('sync_app/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add target_keywords to PromptTemplate
old_pt_fields = """    is_active = models.BooleanField(
        default=False,
        verbose_name="فعال",
        help_text="فقط یک قالب می‌تواند فعال باشد",
    )"""

new_pt_fields = """    is_active = models.BooleanField(
        default=False,
        verbose_name="فعال",
        help_text="فقط یک قالب می‌تواند فعال باشد",
    )
    target_keywords = models.TextField(
        blank=True,
        default="",
        verbose_name="کلمات کلیدی هدف (قالب)",
        help_text="این کلمات کلیدی در تمام محصولات این قالب اعمال می‌شوند",
    )"""

content = content.replace(old_pt_fields, new_pt_fields)

# 2. Remove OpenRouter fields from ApiSettings
openrouter_fields = """    # ── OpenRouter ─────────────────────────
    openrouter_api_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="کلید API اوپن‌روتر",
    )
    openrouter_model = models.CharField(
        max_length=100,
        blank=True,
        default="openai/gpt-4o",
        verbose_name="مدل AI",
        help_text="مثال: openai/gpt-4o, anthropic/claude-3.5-sonnet",
    )

"""
content = content.replace(openrouter_fields, "")

# 3. Add AiSettings Model
ai_settings_model = """
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AiSettings (Singleton)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class AiSettings(models.Model):
    \"\"\"
    Singleton model for storing AI and OpenRouter configurations.
    \"\"\"

    openrouter_api_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="کلید API اوپن‌روتر",
    )
    openrouter_model = models.CharField(
        max_length=100,
        blank=True,
        default="openai/gpt-4o",
        verbose_name="مدل AI",
        help_text="مثال: openai/gpt-4o, anthropic/claude-3.5-sonnet",
    )
    global_keywords = models.TextField(
        blank=True,
        default="",
        verbose_name="کلمات کلیدی سراسری",
        help_text="کلمات کلیدی که روی تمام محصولات اعمال می‌شوند",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تنظیمات هوش مصنوعی"
        verbose_name_plural = "تنظیمات هوش مصنوعی"

    def __str__(self):
        return "تنظیمات هوش مصنوعی"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
"""

content += ai_settings_model

with open('sync_app/models.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated models.py successfully.")
