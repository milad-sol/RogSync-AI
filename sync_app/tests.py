from django.test import SimpleTestCase

from sync_app.prompts import fill_placeholders, select_injection_keywords, split_generated_content


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
