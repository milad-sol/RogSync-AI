"""
RogSync AI — Views

Dashboard, product list/review, prompt templates, API settings,
and HTMX action endpoints.
"""
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import AiSettings, ApiSettings, ProductSync, PromptTemplate, GlobalKeyword
from .tasks import fetch_products_task, process_ai_rewrite_task, push_to_target_task


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

    products = ProductSync.objects.all()

    if status_filter:
        products = products.filter(status=status_filter)
    if search_query:
        products = products.filter(
            Q(title__icontains=search_query) | Q(source_id__icontains=search_query)
        )

    products = products.order_by("-updated_at")

    return render(request, "sync_app/product_list.html", {
        "products": products,
        "status_filter": status_filter,
        "search_query": search_query,
        "status_choices": ProductSync.Status.choices,
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Product Review (Detail)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def product_review_view(request, pk):
    """Side-by-side review of original vs. generated content."""
    product = get_object_or_404(ProductSync, pk=pk)
    return render(request, "sync_app/product_review.html", {
        "product": product,
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Prompt Templates
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def prompt_list_view(request):
    """List all prompt templates."""
    prompts = PromptTemplate.objects.all().order_by("-is_active", "-updated_at")
    return render(request, "sync_app/prompt_list.html", {
        "prompts": prompts,
    })


@require_POST
def prompt_create_view(request):
    """Create a new prompt template."""
    PromptTemplate.objects.create(
        title=request.POST.get("title", "").strip(),
        main_desc_prompt=request.POST.get("main_desc_prompt", "").strip(),
        short_desc_prompt=request.POST.get("short_desc_prompt", "").strip(),
        target_keywords=request.POST.get("target_keywords", "").strip(),
        is_active=bool(request.POST.get("is_active")),
    )
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
#  HTMX Action Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@require_POST
def approve_product_view(request, pk):
    """HTMX: Approve a product and trigger the push task."""
    product = get_object_or_404(ProductSync, pk=pk)

    new_slug = request.POST.get("target_slug", "").strip()
    new_keywords = request.POST.get("target_keywords", "").strip()
    if new_slug:
        product.target_slug = new_slug
    if new_keywords:
        product.target_keywords = new_keywords

    product.status = ProductSync.Status.APPROVED
    product.save()

    push_to_target_task.delay(product.pk)

    return render(request, "sync_app/partials/status_badge.html", {
        "product": product,
        "message": "تأیید شد — در حال ارسال به سایت مقصد…",
    })


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
    limit = request.POST.get("limit", "20")

    if not category_id:
        return HttpResponse(
            '<span class="text-[12px] text-red-600 font-medium">لطفاً شناسه دسته‌بندی را وارد کنید.</span>',
            status=400,
        )

    try:
        category_id = int(category_id)
        limit = int(limit)
    except ValueError:
        return HttpResponse(
            '<span class="text-[12px] text-red-600 font-medium">مقادیر نامعتبر.</span>',
            status=400,
        )

    fetch_products_task.delay(category_id, limit)

    return HttpResponse(
        f'<span class="text-[12px] text-emerald-600 font-medium">'
        f'✓ دریافت از دسته {category_id} شروع شد (حداکثر {limit})'
        f'</span>'
    )


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
