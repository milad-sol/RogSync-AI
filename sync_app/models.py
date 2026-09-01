"""
RogSync AI — Database Models

Three core models:
  • PromptTemplate  — Reusable AI prompt configurations
  • ProductSync     — Tracks each product through the sync pipeline
  • ApiSettings     — Singleton storage for API credentials
"""
from django.db import models


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PromptTemplate
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class PromptTemplate(models.Model):
    """Stores prompt instructions used by the AI rewrite pipeline."""

    title = models.CharField(
        max_length=200,
        verbose_name="عنوان قالب",
    )
    main_desc_prompt = models.TextField(
        verbose_name="پرامپت توضیحات اصلی",
        help_text="دستورالعمل بازنویسی توضیحات اصلی محصول",
    )
    short_desc_prompt = models.TextField(
        verbose_name="پرامپت توضیحات کوتاه",
        help_text="دستورالعمل بازنویسی توضیحات کوتاه محصول",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="فعال",
        help_text="فقط یک قالب می‌تواند فعال باشد",
    )
    target_keywords = models.TextField(
        blank=True,
        default="",
        verbose_name="کلمات کلیدی هدف (قالب)",
        help_text="این کلمات کلیدی در تمام محصولات این قالب اعمال می‌شوند",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "قالب پرامپت"
        verbose_name_plural = "قالب‌های پرامپت"
        ordering = ["-is_active", "-updated_at"]

    def __str__(self):
        return f"{self.title} {'✓' if self.is_active else ''}"

    def save(self, *args, **kwargs):
        # Enforce single-active constraint: deactivate others when this one is activated
        if self.is_active:
            PromptTemplate.objects.filter(is_active=True).exclude(pk=self.pk).update(
                is_active=False
            )
        super().save(*args, **kwargs)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ProductSync
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class ProductSync(models.Model):
    """Represents a single product flowing through the sync pipeline."""

    # ── Status choices ──────────────────────
    class Status(models.TextChoices):
        FETCHED = "fetched", "دریافت شده"
        AI_PROCESSING = "ai_processing", "در حال پردازش AI"
        READY_FOR_REVIEW = "ready_for_review", "آماده بررسی"
        APPROVED = "approved", "تأیید شده"
        SYNCED = "synced", "همگام‌سازی شده"

    # ── Product type choices ────────────────
    class ProductType(models.TextChoices):
        SIMPLE = "simple", "ساده"
        VARIABLE = "variable", "متغیر"

    # ── Source identification ───────────────
    source_id = models.IntegerField(
        unique=True,
        verbose_name="شناسه منبع",
    )
    title = models.CharField(
        max_length=500,
        verbose_name="عنوان محصول",
    )

    # ── Slugs ──────────────────────────────
    original_slug = models.SlugField(
        max_length=500,
        allow_unicode=True,
        verbose_name="اسلاگ اصلی",
    )
    target_slug = models.SlugField(
        max_length=500,
        allow_unicode=True,
        blank=True,
        verbose_name="اسلاگ مقصد",
        help_text="پیش‌فرض: اسلاگ اصلی. قابل ویرایش قبل از ارسال.",
    )

    # ── Type & Keywords ────────────────────
    product_type = models.CharField(
        max_length=20,
        choices=ProductType.choices,
        default=ProductType.SIMPLE,
        verbose_name="نوع محصول",
    )
    target_keywords = models.TextField(
        blank=True,
        default="",
        verbose_name="کلمات کلیدی هدف",
        help_text="کلمات کلیدی جدا شده با کاما",
    )

    # ── Descriptions (HTML) ────────────────
    original_desc = models.TextField(
        blank=True,
        default="",
        verbose_name="توضیحات اصلی",
    )
    generated_desc = models.TextField(
        blank=True,
        default="",
        verbose_name="توضیحات تولید شده",
    )
    original_short_desc = models.TextField(
        blank=True,
        default="",
        verbose_name="توضیحات کوتاه اصلی",
    )
    generated_short_desc = models.TextField(
        blank=True,
        default="",
        verbose_name="توضیحات کوتاه تولید شده",
    )

    # ── Structured data (JSON) ─────────────
    attributes = models.JSONField(
        default=list,
        blank=True,
        verbose_name="ویژگی‌ها",
    )
    images_data = models.JSONField(
        default=list,
        blank=True,
        verbose_name="تصاویر",
        help_text='فرمت: [{"src": "url", "alt": "text"}]',
    )
    variations_data = models.JSONField(
        default=list,
        blank=True,
        verbose_name="تنوع‌ها",
        help_text="داده‌های تنوع محصول متغیر (قیمت، موجودی، …)",
    )

    # ── Pipeline status ────────────────────
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.FETCHED,
        db_index=True,
        verbose_name="وضعیت",
    )

    # ── Timestamps ─────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "محصول همگام‌سازی"
        verbose_name_plural = "محصولات همگام‌سازی"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"[{self.source_id}] {self.title}"

    def save(self, *args, **kwargs):
        # Default target_slug to original_slug if not set
        if not self.target_slug:
            self.target_slug = self.original_slug
        super().save(*args, **kwargs)

    # ── Convenience properties ─────────────
    @property
    def status_badge_classes(self):
        """Return Tailwind classes for status badges (light theme)."""
        return {
            self.Status.FETCHED: "bg-sky-50 text-sky-700 ring-sky-600/20",
            self.Status.AI_PROCESSING: "bg-amber-50 text-amber-700 ring-amber-600/20",
            self.Status.READY_FOR_REVIEW: "bg-violet-50 text-violet-700 ring-violet-600/20",
            self.Status.APPROVED: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
            self.Status.SYNCED: "bg-teal-50 text-teal-700 ring-teal-600/20",
        }.get(self.status, "bg-gray-50 text-gray-700 ring-gray-600/20")

    @property
    def keywords_list(self):
        """Return keywords as a Python list."""
        if not self.target_keywords:
            return []
        return [kw.strip() for kw in self.target_keywords.split(",") if kw.strip()]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ApiSettings (Singleton)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class ApiSettings(models.Model):
    """
    Singleton model for storing API credentials.
    Only one row should ever exist — enforced by overriding save().
    """

    # ── Source WooCommerce ─────────────────
    wc_source_url = models.URLField(
        blank=True,
        default="",
        verbose_name="آدرس سایت منبع",
        help_text="مثال: https://source-store.com",
    )
    wc_source_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Consumer Key منبع",
    )
    wc_source_secret = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Consumer Secret منبع",
    )

    # ── Target WooCommerce ─────────────────
    wc_target_url = models.URLField(
        blank=True,
        default="",
        verbose_name="آدرس سایت مقصد",
        help_text="مثال: https://target-store.com",
    )
    wc_target_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Consumer Key مقصد",
    )
    wc_target_secret = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Consumer Secret مقصد",
    )

    # ── Timestamps ─────────────────────────
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تنظیمات API"
        verbose_name_plural = "تنظیمات API"

    def __str__(self):
        return "تنظیمات API"

    def save(self, *args, **kwargs):
        # Enforce singleton: always use pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Load or create the singleton settings instance."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AiSettings (Singleton)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class AiSettings(models.Model):
    """
    Singleton model for storing AI and OpenRouter configurations.
    """

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
