"""
RogSync AI — Views

Dashboard, product list/review, prompt templates, API settings,
and HTMX action endpoints.
"""
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .content import strip_keyword_marks
from .models import AiSettings, ApiSettings, ProductSync, PromptTemplate, GlobalKeyword
from .tasks import (
    fetch_products_task,
    list_wc_categories,
    process_ai_rewrite_task,
    push_to_target_task,
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
def product_list_view(request):
    """Filterable list of all products in the pipeline."""
    status_filter = request.GET.get("status", "")
    search_query = request.GET.get("q", "")
    source_cat = request.GET.get("source_cat", "")

    products = ProductSync.objects.all()

    if status_filter:
        products = products.filter(status=status_filter)
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

    products = products.order_by("-updated_at")

    return render(request, "sync_app/product_list.html", {
        "products": products,
        "status_filter": status_filter,
        "search_query": search_query,
        "source_cat": source_cat,
        "status_choices": ProductSync.Status.choices,
        "source_category_options": _unique_source_categories(),
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Product Review (Detail)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def product_review_view(request, pk):
    """Review and edit product content, featured image, and gallery."""
    product = get_object_or_404(ProductSync, pk=pk)
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


def prompt_list_view(request):
    """List all prompt templates."""
    prompts = list(PromptTemplate.objects.all().order_by("-is_active", "-updated_at"))
    keywords = list(GlobalKeyword.objects.all().order_by("-is_active", "-priority", "word"))
    _attach_selected_keyword_ids(prompts, keywords)
    return render(request, "sync_app/prompt_list.html", {
        "prompts": prompts,
        "keywords": keywords,
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
    return redirect("sync_app:prompt_list")


@require_POST
def prompt_update_view(request, pk):
    """Update an existing prompt template."""
    prompt = get_object_or_404(PromptTemplate, pk=pk)
    prompt.title = request.POST.get("title", "").strip() or prompt.title
    prompt.prompt = request.POST.get("prompt", "").strip()
    prompt.target_keywords = _keywords_from_request(request)
    prompt.save()
    return redirect("sync_app:prompt_list")


@require_POST
def prompt_activate_view(request, pk):
    """Activate a prompt template (deactivates others via model's save)."""
    prompt = get_object_or_404(PromptTemplate, pk=pk)
    prompt.is_active = True
    prompt.save()
    return redirect("sync_app:prompt_list")


@require_POST
def prompt_delete_view(request, pk):
    """Delete a prompt template."""
    prompt = get_object_or_404(PromptTemplate, pk=pk)
    prompt.delete()
    return redirect("sync_app:prompt_list")


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
        "saved": saved,
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
        "saved": saved,
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


@require_POST
def keyword_create_view(request):
    """Create a new global keyword."""
    word = request.POST.get("word", "").strip()
    priority = request.POST.get("priority", GlobalKeyword.Priority.MEDIUM)
    
    if word:
        GlobalKeyword.objects.get_or_create(
            word=word,
            defaults={"priority": priority, "is_active": True}
        )
    
    # After creation, if it's HTMX, return the updated list or just redirect
    if request.headers.get("HX-Request"):
        keywords = GlobalKeyword.objects.all().order_by("-priority", "-created_at")
        return render(request, "sync_app/partials/keyword_rows.html", {
            "keywords": keywords,
        })
    return redirect("sync_app:keyword_list")


@require_POST
def keyword_toggle_view(request, pk):
    """Toggle active status of a keyword."""
    keyword = get_object_or_404(GlobalKeyword, pk=pk)
    keyword.is_active = not keyword.is_active
    keyword.save()
    
    if request.headers.get("HX-Request"):
        keywords = GlobalKeyword.objects.all().order_by("-priority", "-created_at")
        return render(request, "sync_app/partials/keyword_rows.html", {
            "keywords": keywords,
        })
    return redirect("sync_app:keyword_list")


@require_POST
def keyword_delete_view(request, pk):
    """Delete a keyword."""
    keyword = get_object_or_404(GlobalKeyword, pk=pk)
    keyword.delete()
    
    if request.headers.get("HX-Request"):
        keywords = GlobalKeyword.objects.all().order_by("-priority", "-created_at")
        return render(request, "sync_app/partials/keyword_rows.html", {
            "keywords": keywords,
        })
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


def _images_partial(request, product, message=""):
    return render(request, "sync_app/partials/product_images.html", {
        "product": product,
        "message": message,
    })


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
        return render(request, "sync_app/partials/status_badge.html", {
            "product": product,
            "message": "تأیید شد — در حال ارسال به سایت مقصد…",
        })

    return redirect("sync_app:product_review", pk=product.pk)


@require_POST
def regenerate_ai_view(request, pk):
    """HTMX: Re-trigger the AI rewrite task."""
    product = get_object_or_404(ProductSync, pk=pk)
    product.status = ProductSync.Status.AI_PROCESSING
    product.save(update_fields=["status"])

    process_ai_rewrite_task.delay(product.pk)

    return render(request, "sync_app/partials/status_badge.html", {
        "product": product,
        "message": "بازنویسی مجدد با AI شروع شد…",
    })


@require_POST
def fetch_products_view(request):
    """HTMX: Trigger product fetch from source WooCommerce."""
    category_id = request.POST.get("category_id", "")
    fetch_all = request.POST.get("fetch_all") == "1"
    limit = request.POST.get("limit", "20")

    if not category_id:
        return HttpResponse(
            '<span class="text-[12px] text-red-600 font-medium">لطفاً یک دسته‌بندی انتخاب کنید.</span>',
            status=400,
        )

    try:
        category_id = int(category_id)
        if fetch_all:
            limit_value = None
        else:
            limit_value = int(limit)
            if limit_value <= 0:
                raise ValueError("limit must be positive")
    except ValueError:
        return HttpResponse(
            '<span class="text-[12px] text-red-600 font-medium">مقادیر نامعتبر.</span>',
            status=400,
        )

    fetch_products_task.delay(category_id, limit_value)

    if fetch_all:
        message = f"✓ استخراج همه محصولات دسته {category_id} شروع شد"
    else:
        message = f"✓ استخراج حداکثر {limit_value} محصول از دسته {category_id} شروع شد"

    return HttpResponse(
        f'<span class="text-[12px] text-emerald-600 font-medium">{message}</span>'
    )


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

    return render(request, "sync_app/extract_products.html", {
        "categories": categories,
        "error": error,
        "source_url": source_url,
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

    return HttpResponse(
        '<span class="text-[12px] text-emerald-600 font-medium toast-enter">ذخیره شد ✓</span>'
    )


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
            return _images_partial(request, product, "فایلی انتخاب نشده است.")
        url, error = _store_uploaded_image(request, product, uploaded)
        if error:
            return _images_partial(request, product, error)

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
