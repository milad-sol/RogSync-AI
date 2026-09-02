from django.core.management.base import BaseCommand

from sync_app.content import embed_images_after_paragraphs
from sync_app.models import GlobalKeyword, ProductSync, PromptTemplate


DEMO_SOURCE_ID = 888001
DEMO_VARIABLE_SOURCE_ID = 888002


class Command(BaseCommand):
    help = "Create a demo product with injected keywords and in-post gallery images."

    def handle(self, *args, **options):
        prompt, _ = PromptTemplate.objects.get_or_create(
            title="قالب دمو بازنویسی",
            defaults={
                "prompt": (
                    "برای محصول {product_name} با کلمات کلیدی {seo_keywords} محتوا بساز.\n\n"
                    "[Short Description]\n"
                    "یک خط معرفی کوتاه محصول.\n\n"
                    "[Main Description]\n"
                    "نقد و بررسی HTML محصول."
                ),
                "target_keywords": "گوشی سامسونگ, گلکسی",
                "is_active": True,
            },
        )
        if not PromptTemplate.objects.filter(is_active=True).exists():
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
                "prompt_template": prompt,
                "status": ProductSync.Status.READY_FOR_REVIEW,
            },
        )

        action = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(
            f"Demo product {action}: /products/{product.pk}/review/"
        ))

        laptop_prompt = PromptTemplate.objects.filter(title="لپ تاپ").first() or prompt
        variable_images = [
            {"src": "https://picsum.photos/id/180/900/700", "alt": "لپ‌تاپ گیمینگ نقره‌ای"},
            {"src": "https://picsum.photos/id/201/900/700", "alt": "لپ‌تاپ گیمینگ مشکی"},
        ]
        variable_product, var_created = ProductSync.objects.update_or_create(
            source_id=DEMO_VARIABLE_SOURCE_ID,
            defaults={
                "title": "لپ‌تاپ گیمینگ ایسوس — نسخه دمو متغیر",
                "original_slug": "asus-gaming-laptop-variable-demo",
                "target_slug": "asus-gaming-laptop-variable-demo",
                "product_type": ProductSync.ProductType.VARIABLE,
                "target_keywords": "لپ تاپ گیمینگ, ایسوس, RTX 4060",
                "original_desc": "<p>لپ‌تاپ گیمینگ ایسوس با چند تنوع رنگ و حافظه.</p>",
                "original_short_desc": "<p>لپ‌تاپ گیمینگ متغیر.</p>",
                "generated_desc": "<p>لپ‌تاپ گیمینگ ایسوس با پردازنده قوی و کارت RTX 4060 برای بازی و کار سنگین.</p>",
                "generated_short_desc": "<p>لپ‌تاپ گیمینگ ایسوس با تنوع رنگ و حافظه.</p>",
                "images_data": variable_images,
                "attributes": [
                    {"id": 1, "name": "رنگ", "variation": True, "visible": True, "options": ["نقره‌ای", "مشکی"]},
                    {"id": 2, "name": "حافظه SSD", "variation": True, "visible": True, "options": ["512GB", "1TB"]},
                    {"id": 3, "name": "GPU", "variation": False, "visible": True, "options": ["RTX 4060"]},
                ],
                "variations_data": [
                    {
                        "id": 91001,
                        "sku": "ASUS-SLV-512",
                        "regular_price": "58900000",
                        "sale_price": "55900000",
                        "stock_status": "instock",
                        "stock_quantity": 6,
                        "image": {"src": variable_images[0]["src"]},
                        "attributes": [
                            {"name": "رنگ", "option": "نقره‌ای"},
                            {"name": "حافظه SSD", "option": "512GB"},
                        ],
                    },
                    {
                        "id": 91002,
                        "sku": "ASUS-SLV-1TB",
                        "regular_price": "64900000",
                        "sale_price": "",
                        "stock_status": "instock",
                        "stock_quantity": 3,
                        "image": {"src": variable_images[0]["src"]},
                        "attributes": [
                            {"name": "رنگ", "option": "نقره‌ای"},
                            {"name": "حافظه SSD", "option": "1TB"},
                        ],
                    },
                    {
                        "id": 91003,
                        "sku": "ASUS-BLK-512",
                        "regular_price": "58900000",
                        "sale_price": "54900000",
                        "stock_status": "outofstock",
                        "stock_quantity": 0,
                        "image": {"src": variable_images[1]["src"]},
                        "attributes": [
                            {"name": "رنگ", "option": "مشکی"},
                            {"name": "حافظه SSD", "option": "512GB"},
                        ],
                    },
                    {
                        "id": 91004,
                        "sku": "ASUS-BLK-1TB",
                        "regular_price": "64900000",
                        "sale_price": "",
                        "stock_status": "onbackorder",
                        "stock_quantity": None,
                        "image": {"src": variable_images[1]["src"]},
                        "attributes": [
                            {"name": "رنگ", "option": "مشکی"},
                            {"name": "حافظه SSD", "option": "1TB"},
                        ],
                    },
                ],
                "source_categories": [{"id": 22, "name": "لپ‌تاپ", "slug": "laptop"}],
                "target_categories": [],
                "prompt_template": laptop_prompt,
                "status": ProductSync.Status.READY_FOR_REVIEW,
            },
        )
        var_action = "created" if var_created else "updated"
        self.stdout.write(self.style.SUCCESS(
            f"Variable demo {var_action}: /products/{variable_product.pk}/review/"
        ))
