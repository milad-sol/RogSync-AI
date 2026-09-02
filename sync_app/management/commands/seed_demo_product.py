from django.core.management.base import BaseCommand

from sync_app.content import embed_images_after_paragraphs
from sync_app.models import GlobalKeyword, ProductSync, PromptTemplate


DEMO_SOURCE_ID = 888001


class Command(BaseCommand):
    help = "Create a demo product with injected keywords and in-post gallery images."

    def handle(self, *args, **options):
        PromptTemplate.objects.get_or_create(
            title="قالب دمو بازنویسی",
            defaults={
                "main_desc_prompt": "توضیحات محصول را بازنویسی کن، یکتا و مناسب سئو.",
                "short_desc_prompt": "توضیح کوتاه را کمی ویرایش کن.",
                "target_keywords": "گوشی سامسونگ, گلکسی",
                "is_active": True,
            },
        )
        if not PromptTemplate.objects.filter(is_active=True).exists():
            prompt = PromptTemplate.objects.first()
            if prompt:
                prompt.is_active = True
                prompt.save(update_fields=["is_active"])

        GlobalKeyword.objects.get_or_create(
            word="خرید آنلاین",
            defaults={"priority": GlobalKeyword.Priority.HIGH, "is_active": True},
        )
        GlobalKeyword.objects.get_or_create(
            word="گارانتی اصل",
            defaults={"priority": GlobalKeyword.Priority.MEDIUM, "is_active": True},
        )

        images = [
            {"src": "https://picsum.photos/id/1015/900/700", "alt": "تصویر شاخص گوشی سامسونگ گلکسی"},
            {"src": "https://picsum.photos/id/1016/900/700", "alt": "نمای جلو گوشی گلکسی برای خرید آنلاین"},
            {"src": "https://picsum.photos/id/1018/900/700", "alt": "دوربین گوشی سامسونگ گلکسی"},
            {"src": "https://picsum.photos/id/1019/900/700", "alt": "جعبه و گارانتی اصل محصول"},
            {"src": "https://picsum.photos/id/1025/900/700", "alt": "قیمت مناسب گوشی سامسونگ در استفاده روزمره"},
        ]

        generated_desc = """
<p>گوشی سامسونگ گلکسی برای کسانی طراحی شده که می‌خواهند یک دستگاه سریع، خوش‌ساخت و با قیمت مناسب داشته باشند.</p>
<p>در خرید آنلاین این مدل، مشخصات نمایشگر، باتری و دوربین طوری انتخاب شده که استفاده روزانه بدون دردسر باشد.</p>
<p>گلکسی در این رده با بدنه مقاوم و نرم‌افزار پایدار، گزینه قابل اعتمادی برای کار و سرگرمی است.</p>
<p>اگر به گارانتی اصل اهمیت می‌دهید، این محصول با پشتیبانی رسمی عرضه می‌شود تا خیالتان از خدمات پس از فروش راحت باشد.</p>
<p>با گوشی سامسونگ می‌توانید بدون هزینه اضافه، تجربه‌ای نزدیک به پرچمدارها را با قیمت مناسب به دست بیاورید.</p>
""".strip()

        generated_desc = embed_images_after_paragraphs(generated_desc, images)

        product, created = ProductSync.objects.update_or_create(
            source_id=DEMO_SOURCE_ID,
            defaults={
                "title": "گوشی سامسونگ گلکسی — نسخه دمو بررسی",
                "original_slug": "samsung-galaxy-demo",
                "target_slug": "samsung-galaxy-demo",
                "product_type": ProductSync.ProductType.SIMPLE,
                "target_keywords": "گوشی سامسونگ, گلکسی, قیمت مناسب",
                "original_desc": "<p>توضیحات اصلی منبع بدون بازنویسی و بدون تزریق کلمات کلیدی.</p>",
                "original_short_desc": "<p>گوشی میان‌رده سامسونگ.</p>",
                "generated_desc": generated_desc,
                "generated_short_desc": "<p>گوشی سامسونگ گلکسی با قیمت مناسب برای خرید آنلاین و گارانتی اصل.</p>",
                "images_data": images,
                "source_categories": [{"id": 15, "name": "موبایل", "slug": "mobile"}],
                "target_categories": [],
                "status": ProductSync.Status.READY_FOR_REVIEW,
            },
        )

        action = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(
            f"Demo product {action}: /products/{product.pk}/review/"
        ))
