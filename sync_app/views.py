"""
RogSync AI — Views

Dashboard, product list/review, prompt templates, API settings,
and HTMX action endpoints.
"""
import json
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.views.decorators.http import require_POST

from .content import strip_keyword_marks
from .models import AiSettings, ApiSettings, ProductSync, PromptTemplate, GlobalKeyword
from .sku import assign_skus
from .tasks import (
    fetch_products_task,
    list_wc_categories,
    process_ai_rewrite_task,
    push_to_target_task,
)


def _attach_notify(response, title, icon="success"):
    """Attach a SweetAlert payload for HTMX via HX-Trigger."""
    response["HX-Trigger"] = json.dumps(
        {"notify": {"icon": icon, "title": title}},
        ensure_ascii=True,
    )
    return response


def hx_notify(title, icon="success", status=200, html=""):
    return _attach_notify(HttpResponse(html, status=status), title, icon)


AI_KEY_MISSING = (
    "کلید OpenRouter در تنظیمات هوش مصنوعی وارد نشده است. "
    "ابتدا کلید API را ذخیره کنید، سپس دوباره تولید محتوا را بزنید."
)


ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def _variation_missing_sku(product):
    for item in product.variations_data or []:
        if isinstance(item, dict) and not (item.get("sku") or "").strip():
            return True
    return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Dashboard
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def dashboard_view(request):
    """Overview dashboard with pipeline stats."""
    stats = {}
    for status_value, status_label in ProductSync.Status.choices:
        stats[status_value] = {
            "label": status_label,
            "count": ProductSync.objects.filter(status=status_value).count(),
        }
    total = ProductSync.objects.count()

    return render(request, "sync_app/dashboard.html", {
        "stats": stats,
        "total": total,
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Product List
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REVIEW_STATUS_CHOICES = [
    (value, label)
    for value, label in ProductSync.Status.choices
    if value != ProductSync.Status.SYNCED
]


def _apply_product_filters(products, request):
    search_query = request.GET.get("q", "")
    source_cat = request.GET.get("source_cat", "")
    if search_query:
        products = products.filter(
            Q(title__icontains=search_query) | Q(source_id__icontains=search_query)
        )
    if source_cat:
        try:
            source_cat_id = int(source_cat)
            matching_ids = []
            for product in ProductSync.objects.only("pk", "source_categories"):
                for item in product.source_categories or []:
                    if not isinstance(item, dict):
                        continue
                    try:
                        if int(item.get("id", -1)) == source_cat_id:
                            matching_ids.append(product.pk)
                            break
                    except (TypeError, ValueError):
                        continue
            products = products.filter(pk__in=matching_ids)
        except ValueError:
            source_cat = ""
    return products, search_query, source_cat


def product_list_view(request):
    """Review queue: every product that has not been sent yet."""
    status_filter = request.GET.get("status", "")

    swal_queue = []
    if not AiSettings.is_configured():
        stuck = ProductSync.objects.filter(status=ProductSync.Status.AI_PROCESSING)
        if stuck.exists():
            stuck.update(status=ProductSync.Status.FETCHED)
            swal_queue.append({"icon": "error", "title": AI_KEY_MISSING})

    products = ProductSync.objects.select_related("prompt_template").exclude(
        status=ProductSync.Status.SYNCED
    )
    if status_filter and status_filter != ProductSync.Status.SYNCED:
        products = products.filter(status=status_filter)
    products, search_query, source_cat = _apply_product_filters(products, request)
    products = products.order_by("-updated_at")

    return render(request, "sync_app/product_list.html", {
        "products": products,
        "status_filter": status_filter,
        "search_query": search_query,
        "source_cat": source_cat,
        "status_choices": REVIEW_STATUS_CHOICES,
        "source_category_options": _unique_source_categories(),
        "prompt_templates": PromptTemplate.objects.order_by("-is_active", "title"),
        "swal_queue": swal_queue,
        "sent_list": False,
    })


def sent_products_view(request):
    """Products that were approved and pushed to the destination store."""
    products = ProductSync.objects.select_related("prompt_template").filter(
        status=ProductSync.Status.SYNCED
    )
    products, search_query, source_cat = _apply_product_filters(products, request)
    products = products.order_by("-updated_at")
    swal_queue = []
    if request.GET.get("sent") == "1":
        swal_queue.append({"icon": "success", "title": "محصول به سایت مقصد ارسال شد."})

    return render(request, "sync_app/product_list.html", {
        "products": products,
        "status_filter": "",
        "search_query": search_query,
        "source_cat": source_cat,
        "status_choices": [],
        "source_category_options": _unique_source_categories(),
        "prompt_templates": PromptTemplate.objects.order_by("-is_active", "title"),
        "swal_queue": swal_queue,
        "sent_list": True,
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Product Review (Detail)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def product_review_view(request, pk):
    """Review and edit product content, featured image, and gallery."""
    product = get_object_or_404(ProductSync, pk=pk)
    unstuck_ai = False
    if (
        product.status == ProductSync.Status.AI_PROCESSING
        and not AiSettings.is_configured()
    ):
        product.status = ProductSync.Status.FETCHED
        product.save(update_fields=["status"])
        unstuck_ai = True
    if not (product.target_sku or "").strip() or _variation_missing_sku(product):
        assign_skus(product)
        product.save(update_fields=["target_sku", "variations_data", "updated_at"])
    target_category_options = []
    target_categories_error = ""
    try:
        target_category_options = list_wc_categories("target")
    except Exception:
        target_categories_error = "دسته‌بندی‌های سایت مقصد بارگذاری نشد. تنظیمات API مقصد را بررسی کنید."

    return render(request, "sync_app/product_review.html", {
        "product": product,
        "saved": request.GET.get("saved") == "1",
        "editable_desc": product.generated_desc or product.original_desc,
        "editable_short": product.generated_short_desc or product.original_short_desc,
        "can_approve": product.status in {
            ProductSync.Status.FETCHED,
            ProductSync.Status.READY_FOR_REVIEW,
            ProductSync.Status.APPROVED,
        },
        "target_category_options": target_category_options,
        "target_categories_error": target_categories_error,
        "selected_target_ids": product.target_category_id_set,
        "highlight_keywords": _highlight_keywords_payload(product),
        "prompt_templates": PromptTemplate.objects.order_by("-is_active", "title"),
        "swal_queue": [
            item for item in [
                {"icon": "success", "title": "تغییرات متن ذخیره شد."} if request.GET.get("saved") == "1" else None,
                {"icon": "success", "title": "تأیید شد — در حال ارسال به سایت مقصد…"} if request.GET.get("approved") == "1" else None,
                {"icon": "error", "title": AI_KEY_MISSING} if unstuck_ai else None,
                {"icon": "warning", "title": target_categories_error} if target_categories_error else None,
            ] if item
        ],
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Prompt Templates
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _keywords_from_request(request):
    """Resolve selected GlobalKeyword IDs into a comma-separated word list."""
    ids = [pk for pk in request.POST.getlist("keyword_ids") if str(pk).isdigit()]
    if not ids:
        return ""
    words = list(
        GlobalKeyword.objects.filter(pk__in=ids)
        .order_by("-priority", "word")
        .values_list("word", flat=True)
    )
    return ", ".join(words)


def _attach_selected_keyword_ids(prompts, keywords):
    word_to_id = {item.word: item.pk for item in keywords}
    for prompt in prompts:
        selected = []
        words = []
        for word in (prompt.target_keywords or "").split(","):
            word = word.strip()
            if not word:
                continue
            words.append(word)
            if word in word_to_id:
                selected.append(word_to_id[word])
        prompt.selected_keyword_ids = selected
        prompt.keyword_words = words
        prompt.excerpt = Truncator(strip_tags(prompt.prompt or "")).chars(170)


PROMPT_NOTIFY = {
    "created": "قالب پرامپت ساخته شد.",
    "updated": "قالب پرامپت ذخیره شد.",
    "activated": "قالب پرامپت فعال شد.",
    "deleted": "قالب پرامپت حذف شد.",
}


def _prompt_list_redirect(notify_key):
    return redirect(f"{reverse('sync_app:prompt_list')}?notify={notify_key}")


def prompt_list_view(request):
    """List all prompt templates."""
    prompts = list(PromptTemplate.objects.all().order_by("-is_active", "-updated_at"))
    keywords = list(GlobalKeyword.objects.all().order_by("-is_active", "-priority", "word"))
    _attach_selected_keyword_ids(prompts, keywords)
    notify_title = PROMPT_NOTIFY.get(request.GET.get("notify", ""))
    return render(request, "sync_app/prompt_list.html", {
        "prompts": prompts,
        "keywords": keywords,
        "swal_queue": [{"icon": "success", "title": notify_title}] if notify_title else [],
    })


@require_POST
def prompt_create_view(request):
    """Create a new prompt template."""
    PromptTemplate.objects.create(
        title=request.POST.get("title", "").strip(),
        prompt=request.POST.get("prompt", "").strip(),
        target_keywords=_keywords_from_request(request),
        is_active=bool(request.POST.get("is_active")),
    )
    return _prompt_list_redirect("created")


@require_POST
def prompt_update_view(request, pk):
    """Update an existing prompt template."""
    prompt = get_object_or_404(PromptTemplate, pk=pk)
    prompt.title = request.POST.get("title", "").strip() or prompt.title
    prompt.prompt = request.POST.get("prompt", "").strip()
    prompt.target_keywords = _keywords_from_request(request)
    prompt.save()
    return _prompt_list_redirect("updated")


@require_POST
def prompt_activate_view(request, pk):
    """Activate a prompt template (deactivates others via model's save)."""
    prompt = get_object_or_404(PromptTemplate, pk=pk)
    prompt.is_active = True
    prompt.save()
    return _prompt_list_redirect("activated")


@require_POST
def prompt_delete_view(request, pk):
    """Delete a prompt template."""
    prompt = get_object_or_404(PromptTemplate, pk=pk)
    prompt.delete()
    return _prompt_list_redirect("deleted")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  API Settings
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def api_settings_view(request):
    """Display and save API credentials."""
    settings_obj = ApiSettings.load()
    saved = False

    if request.method == "POST":
        settings_obj.wc_source_url = request.POST.get("wc_source_url", "").strip()
        settings_obj.wc_source_key = request.POST.get("wc_source_key", "").strip()
        settings_obj.wc_source_secret = request.POST.get("wc_source_secret", "").strip()
        settings_obj.wc_target_url = request.POST.get("wc_target_url", "").strip()
        settings_obj.wc_target_key = request.POST.get("wc_target_key", "").strip()
        settings_obj.wc_target_secret = request.POST.get("wc_target_secret", "").strip()
        settings_obj.save()
        saved = True

    return render(request, "sync_app/api_settings.html", {
        "settings": settings_obj,
        "swal_queue": [{"icon": "success", "title": "تنظیمات با موفقیت ذخیره شد."}] if saved else [],
    })



def ai_settings_view(request):
    """Display and save AI/OpenRouter credentials."""
    settings_obj = AiSettings.load()
    saved = False

    if request.method == "POST":
        settings_obj.openrouter_api_key = request.POST.get("openrouter_api_key", "").strip()
        settings_obj.openrouter_model = request.POST.get("openrouter_model", "").strip() or "openai/gpt-4o"
        settings_obj.save()
        saved = True

    return render(request, "sync_app/ai_settings.html", {
        "settings": settings_obj,
        "swal_queue": [{"icon": "success", "title": "تنظیمات با موفقیت ذخیره شد."}] if saved else [],
    })

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Keywords Management
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def keyword_list_view(request):
    """List and search global keywords."""
    search_query = request.GET.get("q", "")
    
    keywords = GlobalKeyword.objects.all()
    if search_query:
        keywords = keywords.filter(word__icontains=search_query)
        
    keywords = keywords.order_by("-priority", "-created_at")

    if request.headers.get("HX-Request"):
        return render(request, "sync_app/partials/keyword_rows.html", {
            "keywords": keywords,
        })
        
    return render(request, "sync_app/keywords_list.html", {
        "keywords": keywords,
        "search_query": search_query,
        "priority_choices": GlobalKeyword.Priority.choices,
    })


def _keyword_rows_response(request, title="", icon="success"):
    keywords = GlobalKeyword.objects.all().order_by("-priority", "-created_at")
    response = render(request, "sync_app/partials/keyword_rows.html", {
        "keywords": keywords,
    })
    if title:
        _attach_notify(response, title, icon)
    return response


@require_POST
def keyword_create_view(request):
    """Create a new global keyword."""
    word = request.POST.get("word", "").strip()
    priority = request.POST.get("priority", GlobalKeyword.Priority.MEDIUM)

    if not word:
        if request.headers.get("HX-Request"):
            return hx_notify("لطفاً کلمه کلیدی را وارد کنید.", icon="error", status=400)
        return redirect("sync_app:keyword_list")

    _, created = GlobalKeyword.objects.get_or_create(
        word=word,
        defaults={"priority": priority, "is_active": True},
    )
    title = "کلمه کلیدی اضافه شد." if created else "این کلمه کلیدی از قبل وجود دارد."
    icon = "success" if created else "info"

    if request.headers.get("HX-Request"):
        return _keyword_rows_response(request, title, icon)
    return redirect("sync_app:keyword_list")


@require_POST
def keyword_toggle_view(request, pk):
    """Toggle active status of a keyword."""
    keyword = get_object_or_404(GlobalKeyword, pk=pk)
    keyword.is_active = not keyword.is_active
    keyword.save()

    title = "کلمه کلیدی فعال شد." if keyword.is_active else "کلمه کلیدی غیرفعال شد."
    if request.headers.get("HX-Request"):
        return _keyword_rows_response(request, title)
    return redirect("sync_app:keyword_list")


@require_POST
def keyword_delete_view(request, pk):
    """Delete a keyword."""
    keyword = get_object_or_404(GlobalKeyword, pk=pk)
    keyword.delete()

    if request.headers.get("HX-Request"):
        return _keyword_rows_response(request, "کلمه کلیدی حذف شد.")
    return redirect("sync_app:keyword_list")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Product review helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _apply_content_fields(product, post_data):
    """Apply editable text fields from a POST payload onto the product."""
    title = post_data.get("title", "").strip()
    if title:
        product.title = title

    new_slug = post_data.get("target_slug", "").strip()
    if new_slug:
        product.target_slug = new_slug

    if "target_keywords" in post_data:
        product.target_keywords = post_data.get("target_keywords", "").strip()

    raw_prompt = post_data.get("prompt_template_id")
    if raw_prompt:
        try:
            product.prompt_template_id = int(raw_prompt)
        except (TypeError, ValueError):
            pass

    if "generated_desc" in post_data:
        product.generated_desc = strip_keyword_marks(post_data.get("generated_desc", ""))
    if "generated_short_desc" in post_data:
        product.generated_short_desc = strip_keyword_marks(post_data.get("generated_short_desc", ""))

    if post_data.get("categories_submitted") == "1":
        getlist = getattr(post_data, "getlist", None)
        raw_ids = getlist("target_category_ids") if getlist else post_data.get("target_category_ids") or []
        if isinstance(raw_ids, str):
            raw_ids = [raw_ids]
        selected = []
        for raw_id in raw_ids:
            try:
                cid = int(raw_id)
            except (TypeError, ValueError):
                continue
            name = post_data.get(f"target_category_name_{cid}", str(cid)).strip()
            selected.append({"id": cid, "name": name})
        product.target_categories = selected


def _highlight_keywords_payload(product):
    """Keywords to highlight in the review editor: product vs global."""
    global_rows = list(
        GlobalKeyword.objects.filter(is_active=True)
        .order_by("-priority")
        .values("word", "priority")
    )
    return {
        "product": product.keywords_list,
        "global": [
            {"word": row["word"], "priority": row["priority"]}
            for row in global_rows
            if row.get("word")
        ],
    }


def _unique_source_categories():
    """Build a sorted id/name list of source categories seen on synced products."""
    seen = {}
    for cats in ProductSync.objects.exclude(source_categories=[]).values_list("source_categories", flat=True):
        for item in cats or []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            try:
                cid = int(item["id"])
            except (TypeError, ValueError):
                continue
            if cid not in seen:
                seen[cid] = (item.get("name") or str(cid)).strip()
    return sorted(seen.items(), key=lambda row: row[1])


def _normalized_images(product):
    images = []
    for item in product.images_data or []:
        if not isinstance(item, dict):
            continue
        src = (item.get("src") or "").strip()
        if not src:
            continue
        images.append({"src": src, "alt": (item.get("alt") or "").strip()})
    return images


def _save_images(product, images):
    product.images_data = images
    product.save(update_fields=["images_data", "updated_at"])


def _images_partial(request, product, message="", icon="success"):
    response = render(request, "sync_app/partials/product_images.html", {
        "product": product,
    })
    if message:
        _attach_notify(response, message, icon)
    return response


def _store_uploaded_image(request, product, uploaded):
    content_type = (uploaded.content_type or "").lower()
    ext = Path(uploaded.name).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        return None, "فرمت تصویر مجاز نیست. از JPG، PNG، WebP یا GIF استفاده کنید."
    if content_type and content_type not in ALLOWED_IMAGE_TYPES:
        return None, "فرمت تصویر مجاز نیست. از JPG، PNG، WebP یا GIF استفاده کنید."
    if uploaded.size > MAX_UPLOAD_BYTES:
        return None, "حجم تصویر بیش از ۸ مگابایت است."

    filename = f"products/{product.pk}/{uuid.uuid4().hex}{ext}"
    saved = default_storage.save(filename, uploaded)
    url = request.build_absolute_uri(f"{settings.MEDIA_URL}{saved}")
    return url, None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HTMX Action Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@require_POST
def approve_product_view(request, pk):
    """Approve a product, persist any in-form edits, then push to target."""
    product = get_object_or_404(ProductSync, pk=pk)
    _apply_content_fields(product, request.POST)

    product.status = ProductSync.Status.APPROVED
    product.save()

    push_to_target_task.delay(product.pk)

    if request.headers.get("HX-Request"):
        response = render(request, "sync_app/partials/status_badge.html", {
            "product": product,
        })
        return _attach_notify(response, "تأیید شد — در حال ارسال به سایت مقصد…")

    review_url = reverse("sync_app:product_review", args=[product.pk])
    return redirect(f"{review_url}?approved=1")


def _product_row_response(request, product, generate_error=""):
    response = render(request, "sync_app/partials/product_row.html", {
        "product": product,
        "prompt_templates": PromptTemplate.objects.order_by("-is_active", "title"),
    })
    if generate_error:
        _attach_notify(response, generate_error, "error")
    return response


def product_row_view(request, pk):
    """HTMX: one product list row, used to poll AI rewrite status."""
    product = get_object_or_404(
        ProductSync.objects.select_related("prompt_template"),
        pk=pk,
    )
    if (
        product.status == ProductSync.Status.AI_PROCESSING
        and not AiSettings.is_configured()
    ):
        product.status = ProductSync.Status.FETCHED
        product.save(update_fields=["status"])
    if product.status == ProductSync.Status.SYNCED:
        response = HttpResponse()
        response["HX-Reswap"] = "delete"
        return response
    return _product_row_response(request, product)


def product_push_status_view(request, pk):
    """HTMX: poll until the destination push finishes, then leave review."""
    product = get_object_or_404(ProductSync, pk=pk)
    if product.status == ProductSync.Status.SYNCED:
        url = f"{reverse('sync_app:sent_products')}?sent=1"
        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Redirect"] = url
            return response
        return redirect(url)
    return render(request, "sync_app/partials/status_badge.html", {
        "product": product,
    })


@require_POST
def regenerate_ai_view(request, pk):
    """HTMX: Re-trigger the AI rewrite task with the chosen prompt."""
    product = get_object_or_404(
        ProductSync.objects.select_related("prompt_template"),
        pk=pk,
    )
    from_list = request.POST.get("from_list") == "1"
    raw_prompt = request.POST.get("prompt_template_id")
    if raw_prompt:
        try:
            prompt = PromptTemplate.objects.filter(pk=int(raw_prompt)).first()
        except (TypeError, ValueError):
            prompt = None
        if prompt:
            product.prompt_template = prompt
    if not product.prompt_template_id:
        message = "ابتدا قالب پرامپت این محصول را انتخاب کنید."
        if from_list:
            return _product_row_response(request, product, generate_error=message)
        return hx_notify(message, icon="error", status=400, html=message)

    if not AiSettings.is_configured():
        product.save(update_fields=["prompt_template"])
        if from_list:
            return _product_row_response(request, product, generate_error=AI_KEY_MISSING)
        return hx_notify(AI_KEY_MISSING, icon="error", status=400, html=AI_KEY_MISSING)

    product.status = ProductSync.Status.AI_PROCESSING
    product.save(update_fields=["prompt_template", "status"])

    process_ai_rewrite_task.delay(product.pk)

    if from_list:
        return _attach_notify(_product_row_response(request, product), "تولید محتوا شروع شد.")
    response = render(request, "sync_app/partials/status_badge.html", {
        "product": product,
    })
    return _attach_notify(response, "بازنویسی مجدد با AI شروع شد.")


@require_POST
def fetch_products_view(request):
    """HTMX: Trigger product fetch from source WooCommerce."""
    category_id = request.POST.get("category_id", "")
    fetch_all = request.POST.get("fetch_all") == "1"
    limit = request.POST.get("limit", "20")
    prompt_id = request.POST.get("prompt_template_id", "")

    if not category_id:
        return hx_notify("لطفاً یک دسته‌بندی انتخاب کنید.", icon="error", status=400, html="لطفاً یک دسته‌بندی انتخاب کنید.")

    try:
        prompt_id = int(prompt_id)
    except (TypeError, ValueError):
        return hx_notify("لطفاً قالب پرامپت را انتخاب کنید.", icon="error", status=400, html="قالب پرامپت")
    if not PromptTemplate.objects.filter(pk=prompt_id).exists():
        return hx_notify("قالب پرامپت پیدا نشد.", icon="error", status=400, html="قالب پرامپت")

    if not AiSettings.is_configured():
        return hx_notify(AI_KEY_MISSING, icon="error", status=400, html=AI_KEY_MISSING)

    try:
        category_id = int(category_id)
        if fetch_all:
            limit_value = None
        else:
            limit_value = int(limit)
            if limit_value <= 0:
                raise ValueError("limit must be positive")
    except ValueError:
        return hx_notify("مقادیر نامعتبر.", icon="error", status=400, html="مقادیر نامعتبر.")

    fetch_products_task.delay(category_id, limit_value, prompt_id)

    if fetch_all:
        message = f"استخراج همه محصولات دسته {category_id} شروع شد."
    else:
        message = f"استخراج حداکثر {limit_value} محصول از دسته {category_id} شروع شد."

    return hx_notify(message, icon="success")


def extract_products_view(request):
    """Dedicated page for pulling products from source WooCommerce categories."""
    error = ""
    categories = []
    source_url = ""
    creds = ApiSettings.load()
    source_url = creds.wc_source_url or settings.WC_SOURCE_URL

    if not source_url:
        error = "ابتدا آدرس و کلیدهای سایت منبع را در تنظیمات API ذخیره کنید."
    else:
        try:
            categories = list_wc_categories("source")
        except Exception:
            error = "ارتباط با فروشگاه منبع برقرار نشد. تنظیمات API منبع را بررسی کنید."

    prompt_templates = list(PromptTemplate.objects.order_by("-is_active", "title"))
    default_prompt_id = next((item.pk for item in prompt_templates if item.is_active), None)

    return render(request, "sync_app/extract_products.html", {
        "categories": categories,
        "error": error,
        "source_url": source_url,
        "prompt_templates": prompt_templates,
        "default_prompt_id": default_prompt_id,
        "swal_queue": [{"icon": "warning", "title": error}] if error else [],
    })


@require_POST
def update_product_fields_view(request, pk):
    """HTMX: Save inline-edited slug/keywords."""
    product = get_object_or_404(ProductSync, pk=pk)

    new_slug = request.POST.get("target_slug", "").strip()
    new_keywords = request.POST.get("target_keywords", "").strip()

    if new_slug:
        product.target_slug = new_slug
    if new_keywords is not None:
        product.target_keywords = new_keywords

    product.save(update_fields=["target_slug", "target_keywords", "updated_at"])

    return hx_notify("ذخیره شد.", icon="success")


@require_POST
def update_product_content_view(request, pk):
    """Save title, slug, keywords, and edited descriptions."""
    product = get_object_or_404(ProductSync, pk=pk)
    _apply_content_fields(product, request.POST)
    product.save()

    review_url = reverse("sync_app:product_review", args=[product.pk])
    return redirect(f"{review_url}?saved=1")


@require_POST
def update_product_images_view(request, pk):
    """HTMX: mutate featured image and gallery (add, replace, remove, reorder, alt)."""
    product = get_object_or_404(ProductSync, pk=pk)
    action = request.POST.get("action", "").strip()
    images = _normalized_images(product)

    def _index():
        try:
            idx = int(request.POST.get("index", -1))
        except (TypeError, ValueError):
            return -1
        if 0 <= idx < len(images):
            return idx
        return -1

    if action == "set_featured":
        idx = _index()
        if idx > 0:
            images.insert(0, images.pop(idx))
            _save_images(product, images)
            return _images_partial(request, product, "تصویر شاخص به‌روز شد.")

    elif action == "remove":
        idx = _index()
        if idx >= 0:
            images.pop(idx)
            _save_images(product, images)
            return _images_partial(request, product, "تصویر حذف شد.")

    elif action == "update_alt":
        idx = _index()
        if idx >= 0:
            images[idx]["alt"] = request.POST.get("alt", "").strip()
            _save_images(product, images)
            return _images_partial(request, product, "متن جایگزین ذخیره شد.")

    elif action == "replace":
        idx = _index()
        src = request.POST.get("src", "").strip()
        if idx >= 0 and src:
            images[idx]["src"] = src
            alt = request.POST.get("alt", "").strip()
            if alt:
                images[idx]["alt"] = alt
            _save_images(product, images)
            return _images_partial(request, product, "تصویر جایگزین شد.")

    elif action == "add":
        src = request.POST.get("src", "").strip()
        alt = request.POST.get("alt", "").strip()
        if src:
            images.append({"src": src, "alt": alt})
            _save_images(product, images)
            return _images_partial(request, product, "تصویر به گالری اضافه شد.")

    elif action == "move":
        idx = _index()
        direction = request.POST.get("direction", "")
        if idx >= 0:
            if direction == "up" and idx > 0:
                images[idx - 1], images[idx] = images[idx], images[idx - 1]
                _save_images(product, images)
                return _images_partial(request, product, "ترتیب تصاویر به‌روز شد.")
            if direction == "down" and idx < len(images) - 1:
                images[idx + 1], images[idx] = images[idx], images[idx + 1]
                _save_images(product, images)
                return _images_partial(request, product, "ترتیب تصاویر به‌روز شد.")

    elif action == "reorder":
        try:
            from_idx = int(request.POST.get("from_index", -1))
            to_idx = int(request.POST.get("to_index", -1))
        except (TypeError, ValueError):
            from_idx, to_idx = -1, -1
        count = len(images)
        if from_idx >= 1 and from_idx < count and 0 <= to_idx < count and from_idx != to_idx:
            order = list(range(count))
            from_pos = from_idx
            to_pos = to_idx
            order.pop(from_pos)
            insert_at = order.index(to_idx)
            if from_pos < to_pos:
                insert_at += 1
            order.insert(insert_at, from_idx)
            images = [images[i] for i in order]
            _save_images(product, images)
            if to_idx == 0:
                return _images_partial(request, product, "تصویر شاخص به‌روز شد.")
            return _images_partial(request, product, "ترتیب گالری به‌روز شد.")

    elif action == "upload":
        uploaded = request.FILES.get("image")
        if not uploaded:
            return _images_partial(request, product, "فایلی انتخاب نشده است.", icon="error")
        url, error = _store_uploaded_image(request, product, uploaded)
        if error:
            return _images_partial(request, product, error, icon="error")

        item = {"src": url, "alt": request.POST.get("alt", "").strip()}
        role = request.POST.get("role", "gallery")
        if role == "featured":
            if images:
                images[0] = item
            else:
                images.append(item)
            _save_images(product, images)
            return _images_partial(request, product, "تصویر شاخص به‌روز شد.")

        images.append(item)
        _save_images(product, images)
        return _images_partial(request, product, "تصویر به گالری اضافه شد.")

    return _images_partial(request, product)
