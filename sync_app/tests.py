from django.test import SimpleTestCase

from sync_app.prompts import fill_placeholders, split_generated_content


class PromptHelpersTests(SimpleTestCase):
    def test_fill_placeholders_leaves_other_braces(self):
        text = fill_placeholders(
            "Product {product_name} | {Accessory Type} | {seo_keywords}",
            {"product_name": "دسته DualSense", "seo_keywords": "خرید دسته"},
        )
        self.assertEqual(text, "Product دسته DualSense | {Accessory Type} | خرید دسته")

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
