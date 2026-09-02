from django.db import migrations, models


def copy_prompt_fields(apps, schema_editor):
    PromptTemplate = apps.get_model("sync_app", "PromptTemplate")
    for row in PromptTemplate.objects.all():
        parts = []
        main = (row.main_desc_prompt or "").strip()
        short = (row.short_desc_prompt or "").strip()
        if main:
            parts.append(main)
        if short and short not in main:
            parts.append(short)
        row.prompt = "\n\n".join(parts).strip()
        row.save(update_fields=["prompt"])


class Migration(migrations.Migration):

    dependencies = [
        ("sync_app", "0006_productsync_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="prompttemplate",
            name="prompt",
            field=models.TextField(
                default="",
                help_text="یک پرامپت واحد که هم توضیح کوتاه و هم محتوای اصلی را تولید می‌کند. از {product_name} و {seo_keywords} استفاده کنید.",
                verbose_name="پرامپت",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="productsync",
            name="source_permalink",
            field=models.URLField(blank=True, default="", max_length=500, verbose_name="لینک محصول منبع"),
        ),
        migrations.RunPython(copy_prompt_fields, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="prompttemplate",
            name="main_desc_prompt",
        ),
        migrations.RemoveField(
            model_name="prompttemplate",
            name="short_desc_prompt",
        ),
    ]
