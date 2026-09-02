from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from sync_app.models import ProductSync, PromptTemplate
from sync_app.prompts import (
    build_generation_prompt,
    fill_placeholders,
    format_variations_for_prompt,
    select_injection_keywords,
    split_generated_content,
)


class PromptHelpersTests(SimpleTestCase):
    def test_fill_placeholders_leaves_other_braces(self):
        text = fill_placeholders(
            "Product {product_name} | {Accessory Type} | {seo_keywords} | {gpu_model}",
            {"product_name": "دسته DualSense", "seo_keywords": "خرید دسته", "gpu_model": "RTX 4050"},
        )
        self.assertEqual(text, "Product دسته DualSense | {Accessory Type} | خرید دسته | RTX 4050")

    def test_split_marked_sections(self):
        raw = """
[Short Description]
نوع محصول دسته بازی | سازگاری PS5 | نوع اتصال بی‌سیم

[Main Description]
<h2>نقد و بررسی</h2>
<p>متن اصلی</p>
"""
        short, main = split_generated_content(raw)
        self.assertIn("PS5", short)
        self.assertIn("<h2>نقد و بررسی</h2>", main)
        self.assertNotIn("[Main Description]", main)

    def test_split_pipe_line_without_markers(self):
        short, main = split_generated_content(
            "نوع محصول هدست | سازگاری Xbox\n<h2>بررسی</h2>"
        )
        self.assertIn("هدست", short)
        self.assertIn("<h2>بررسی</h2>", main)

    def test_select_closest_keywords(self):
        product = type("P", (), {
            "title": "لپ تاپ گیمینگ ایسوس TUF A15 RTX 4050",
            "original_short_desc": "پردازنده Ryzen 7 رم 16 گیگابایت",
            "original_desc": "",
            "source_category_label": "لپ تاپ گیمینگ",
            "target_category_label": "",
            "attributes": [{"name": "GPU", "options": ["RTX 4050"]}],
        })()
        selected = select_injection_keywords(
            product,
            [
                ("لپ تاپ گیمینگ", 2),
                ("ایسوس تاف", 2),
                ("دسته بازی PS5", 3),
                ("خرید آنلاین", 3),
                ("هدست استریم", 1),
            ],
            limit=4,
        )
        self.assertIn("لپ تاپ گیمینگ", selected)
        self.assertNotIn("دسته بازی PS5", selected)
        self.assertNotIn("هدست استریم", selected)

    def test_variable_prompt_lists_combos_without_prices(self):
        product = type("P", (), {
            "title": "لپ‌تاپ گیمینگ ایسوس",
            "product_type": "variable",
            "original_short_desc": "",
            "original_desc": "",
            "source_permalink": "",
            "attributes": [
                {"name": "رنگ", "variation": True, "options": ["نقره‌ای", "مشکی"]},
                {"name": "GPU", "variation": False, "options": ["RTX 4060"]},
            ],
            "variations_data": [
                {
                    "sku": "ASUS-SLV-512",
                    "regular_price": "58900000",
                    "sale_price": "55900000",
                    "attributes": [
                        {"name": "رنگ", "option": "نقره‌ای"},
                        {"name": "حافظه SSD", "option": "512GB"},
                    ],
                },
                {
                    "sku": "ASUS-BLK-1TB",
                    "regular_price": "64900000",
                    "attributes": [
                        {"name": "رنگ", "option": "مشکی"},
                        {"name": "حافظه SSD", "option": "1TB"},
                    ],
                },
            ],
        })()
        brief = format_variations_for_prompt(product)
        self.assertIn("نقره‌ای", brief)
        self.assertIn("512GB", brief)
        self.assertIn("مشکی", brief)
        self.assertIn("2", brief)
        self.assertNotIn("58900000", brief)
        self.assertNotIn("55900000", brief)
        prompt = build_generation_prompt("Write copy for {product_name}. {variations}", product, "لپ تاپ")
        self.assertIn("VARIATIONS", prompt)
        self.assertIn("ASUS-SLV-512", prompt)
        self.assertIn("every listed configuration", prompt.lower())
        self.assertNotIn("58900000", prompt)


class FetchRequiresPromptTests(TestCase):
    def test_fetch_without_prompt_is_rejected(self):
        response = self.client.post(
            reverse("sync_app:fetch_products"),
            {"category_id": "12", "limit": "5"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("قالب پرامپت", response.content.decode())


class GenerateRequiresAiSettingsTests(TestCase):
    def setUp(self):
        self.prompt = PromptTemplate.objects.create(title="لپ تاپ", prompt="Write copy.")
        self.product = ProductSync.objects.create(
            source_id=101,
            title="محصول تست",
            original_slug="test-product",
        )

    def test_generate_without_api_key_stays_fetched(self):
        response = self.client.post(
            reverse("sync_app:regenerate_ai", args=[self.product.pk]),
            {"from_list": "1", "prompt_template_id": str(self.prompt.pk)},
        )
        self.product.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.product.status, ProductSync.Status.FETCHED)
        self.assertIn("OpenRouter", response["HX-Trigger"])

    def test_fetch_without_api_key_is_rejected(self):
        response = self.client.post(
            reverse("sync_app:fetch_products"),
            {
                "category_id": "12",
                "limit": "5",
                "prompt_template_id": str(self.prompt.pk),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("OpenRouter", response["HX-Trigger"])
