"""
RogSync AI — Celery Tasks

Three-stage pipeline:
  1. fetch_products_task   → Pull from source WooCommerce
  2. process_ai_rewrite_task → Rewrite via OpenRouter
  3. push_to_target_task   → Push to target WooCommerce
"""
import json
import logging

import requests
from celery import shared_task
from django.conf import settings
from woocommerce import API as WooAPI

from .content import embed_images_after_paragraphs
from .models import AiSettings, ApiSettings, ProductSync, PromptTemplate, GlobalKeyword
from .prompts import build_generation_prompt, select_injection_keywords, split_generated_content

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _wc_api(kind="source"):
    """Return a WooCommerce client using UI settings, falling back to env vars."""
    creds = ApiSettings.load()
    if kind == "source":
        url = creds.wc_source_url or settings.WC_SOURCE_URL
        key = creds.wc_source_key or settings.WC_SOURCE_KEY
        secret = creds.wc_source_secret or settings.WC_SOURCE_SECRET
    else:
        url = creds.wc_target_url or settings.WC_TARGET_URL
        key = creds.wc_target_key or settings.WC_TARGET_KEY
        secret = creds.wc_target_secret or settings.WC_TARGET_SECRET

    if not url or not key or not secret:
        raise ValueError("WooCommerce credentials are missing.")

    return WooAPI(
        url=url,
        consumer_key=key,
        consumer_secret=secret,
        version="wc/v3",
        timeout=30,
    )


def _source_api():
    """Return a WooCommerce API client for the source store."""
    return _wc_api("source")


def _target_api():
    """Return a WooCommerce API client for the target store."""
    return _wc_api("target")


def _category_path(category, by_id):
    names = [category.get("name") or str(category.get("id", ""))]
    parent = category.get("parent") or 0
    seen = set()
    while parent and parent in by_id and parent not in seen:
        seen.add(parent)
        parent_cat = by_id[parent]
        names.append(parent_cat.get("name") or str(parent))
        parent = parent_cat.get("parent") or 0
    return " / ".join(reversed(names))


def decorate_wc_categories(raw_categories):
    """Add a hierarchical label to each WooCommerce category."""
    by_id = {
        item["id"]: item
        for item in raw_categories
        if isinstance(item, dict) and item.get("id") is not None
    }
    decorated = []
    for item in raw_categories:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        decorated.append({
            "id": int(item["id"]),
            "name": item.get("name") or "",
            "slug": item.get("slug") or "",
            "parent": item.get("parent") or 0,
            "count": item.get("count") or 0,
            "label": _category_path(item, by_id),
        })
    decorated.sort(key=lambda row: row["label"])
    return decorated


def list_wc_categories(kind="source"):
    """Fetch all product categories from a WooCommerce store."""
    api = _wc_api(kind)
    results = []
    page = 1
    while page <= 50:
        response = api.get(
            "products/categories",
            params={"per_page": 100, "page": page, "hide_empty": False},
        )
        batch = response.json()
        if not isinstance(batch, list):
            message = "Invalid WooCommerce category response."
            if isinstance(batch, dict):
                message = batch.get("message") or message
            raise ValueError(message)
        if not batch:
            break
        results.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return decorate_wc_categories(results)


def _normalize_source_categories(product_payload):
    categories = []
    for item in product_payload.get("categories") or []:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        categories.append({
            "id": item.get("id"),
            "name": item.get("name") or "",
            "slug": item.get("slug") or "",
        })
    return categories


def _openrouter_chat(system_prompt: str, user_prompt: str) -> str:
    """Send a chat completion request to the OpenRouter API and return the response text."""
    ai_settings = AiSettings.load()
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {ai_settings.openrouter_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": ai_settings.openrouter_model or "openai/gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 8000,
        },
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Task 1: Fetch Products from Source
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def fetch_products_task(self, category_id: int, limit=None):
    """
    Fetch products from the source WooCommerce store by category.

    Pass limit=None to pull every published product in the category.
    For variable products, makes a secondary request to get variations.
    Creates or updates ProductSync records with status=FETCHED.
    """
    api = _source_api()
    fetched_ids = []
    unlimited = limit is None or int(limit) <= 0
    max_items = None if unlimited else int(limit)

    try:
        page = 1
        total_fetched = 0

        while True:
            if max_items is not None and total_fetched >= max_items:
                break

            per_page = 100
            if max_items is not None:
                per_page = min(max_items - total_fetched, 100)

            response = api.get(
                "products",
                params={
                    "category": category_id,
                    "per_page": per_page,
                    "page": page,
                    "status": "publish",
                },
            )
            products = response.json()

            if not isinstance(products, list) or not products:
                break

            for product in products:
                images_data = [
                    {"src": img.get("src", ""), "alt": img.get("alt", "")}
                    for img in product.get("images", [])
                ]
                attributes = product.get("attributes", [])
                source_categories = _normalize_source_categories(product)

                variations_data = []
                if product.get("type") == "variable":
                    try:
                        var_response = api.get(
                            f"products/{product['id']}/variations",
                            params={"per_page": 100},
                        )
                        variations_data = var_response.json()
                    except Exception as e:
                        logger.warning(
                            "Failed to fetch variations for product %s: %s",
                            product["id"],
                            e,
                        )

                obj, _created = ProductSync.objects.update_or_create(
                    source_id=product["id"],
                    defaults={
                        "title": product.get("name", ""),
                        "original_slug": product.get("slug", ""),
                        "product_type": product.get("type", "simple"),
                        "original_desc": product.get("description", ""),
                        "original_short_desc": product.get("short_description", ""),
                        "source_permalink": product.get("permalink", "") or "",
                        "attributes": attributes,
                        "images_data": images_data,
                        "variations_data": variations_data,
                        "source_categories": source_categories,
                        "status": ProductSync.Status.FETCHED,
                    },
                )
                fetched_ids.append(obj.pk)
                total_fetched += 1

                if max_items is not None and total_fetched >= max_items:
                    break

            if len(products) < per_page:
                break
            page += 1

    except Exception as exc:
        logger.error("fetch_products_task failed: %s", exc)
        raise self.retry(exc=exc)

    logger.info("Fetched %d products from category %s", len(fetched_ids), category_id)
    return fetched_ids


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Task 2: AI Rewrite via OpenRouter
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def process_ai_rewrite_task(self, product_id: int):
    """
    Use the active PromptTemplate + OpenRouter to:
      1. Resolve SEO keywords.
      2. Generate short + main copy in one prompt.
      3. Generate SEO-optimized alt text for images.
    """
    try:
        product = ProductSync.objects.get(pk=product_id)
    except ProductSync.DoesNotExist:
        logger.error("ProductSync %s not found", product_id)
        return

    # Get the active prompt template
    prompt_template = PromptTemplate.objects.filter(is_active=True).first()
    if not prompt_template:
        logger.error("No active PromptTemplate found. Aborting AI rewrite.")
        return

    product.status = ProductSync.Status.AI_PROCESSING
    product.save(update_fields=["status"])

    try:
        # ── Step 1: Handle SEO keywords ────────
        merged_kws = []
        for kw_source in [product.target_keywords, prompt_template.target_keywords]:
            if kw_source:
                merged_kws.extend(k.strip() for k in kw_source.split(",") if k.strip())

        unique_kws = []
        for kw in merged_kws:
            if kw not in unique_kws:
                unique_kws.append(kw)

        if unique_kws:
            product.target_keywords = ", ".join(unique_kws)
        else:
            keywords_prompt = (
                "You are an SEO expert. Given the following product title, generate "
                "5-8 highly relevant SEO keywords in the same language as the title. "
                "Return ONLY the keywords separated by commas, nothing else.\n\n"
                f"Product title: {product.title}"
            )
            keywords_result = _openrouter_chat(
                system_prompt="You are an SEO keyword research specialist.",
                user_prompt=keywords_prompt,
            )
            product.target_keywords = keywords_result.strip()

        seo_candidates = [(word, 3) for word in product.keywords_list]
        seo_candidates.extend(
            (item.word, item.priority)
            for item in GlobalKeyword.objects.filter(is_active=True)
        )
        seo_keywords = select_injection_keywords(product, seo_candidates, limit=8)

        # ── Step 2: Generate short + main copy together ──
        user_prompt = build_generation_prompt(
            prompt_template.prompt,
            product,
            ", ".join(seo_keywords),
        )
        generated = _openrouter_chat(
            system_prompt=(
                "Follow the user prompt exactly. Output only the requested sections. "
                "Published copy must be 100% Persian except Latin technical tokens."
            ),
            user_prompt=user_prompt,
        )
        short_html, main_html = split_generated_content(generated)
        if not short_html and not main_html:
            raise ValueError("AI returned empty content.")
        if short_html:
            product.generated_short_desc = short_html
        if main_html:
            product.generated_desc = main_html

        # ── Step 3: Generate image alt texts ───
        if product.images_data:
            updated_images = []
            for img in product.images_data:
                alt_prompt = (
                    f"Generate a short, SEO-optimized alt text (max 125 characters) "
                    f"for a product image. The product is: {product.title}. "
                    f"Keywords: {product.target_keywords}. "
                    f"Return ONLY the alt text, nothing else."
                )
                new_alt = _openrouter_chat(
                    system_prompt="You are an SEO image alt text specialist.",
                    user_prompt=alt_prompt,
                ).strip().strip('"').strip("'")
                updated_images.append({"src": img["src"], "alt": new_alt})
            product.images_data = updated_images

        if product.generated_desc:
            product.generated_desc = embed_images_after_paragraphs(
                product.generated_desc,
                product.images_data,
            )

        # ── Done ───────────────────────────────
        product.status = ProductSync.Status.READY_FOR_REVIEW
        product.save()
        logger.info("AI rewrite complete for product %s", product_id)

    except Exception as exc:
        logger.error("AI rewrite failed for product %s: %s", product_id, exc)
        product.status = ProductSync.Status.FETCHED
        product.save(update_fields=["status"])
        raise self.retry(exc=exc)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Task 3: Push to Target WooCommerce
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def push_to_target_task(self, product_id: int):
    """
    Push an approved product to the target WooCommerce store.

    For variable products: create parent first, then push variations.
    Images are sent as an array so WP handles media sideloading.
    """
    try:
        product = ProductSync.objects.get(pk=product_id)
    except ProductSync.DoesNotExist:
        logger.error("ProductSync %s not found", product_id)
        return

    api = _target_api()

    try:
        # Build the product payload
        payload = {
            "name": product.title,
            "slug": product.target_slug,
            "type": product.product_type,
            "description": product.generated_desc or product.original_desc,
            "short_description": product.generated_short_desc or product.original_short_desc,
            "images": product.images_data,
            "attributes": product.attributes,
        }
        if product.target_categories:
            payload["categories"] = [
                {"id": item["id"]}
                for item in product.target_categories
                if isinstance(item, dict) and item.get("id") is not None
            ]

        # Create the product on the target store
        response = api.post("products", payload)
        result = response.json()
        new_product_id = result.get("id")

        if not new_product_id:
            raise ValueError(f"Target API did not return a product ID: {result}")

        logger.info(
            "Created product %s on target store (new ID: %s)",
            product_id,
            new_product_id,
        )

        # For variable products, push each variation
        if product.product_type == ProductSync.ProductType.VARIABLE and product.variations_data:
            for variation in product.variations_data:
                # Build variation payload (keep relevant fields)
                var_payload = {
                    "regular_price": str(variation.get("regular_price", "")),
                    "sale_price": str(variation.get("sale_price", "")),
                    "sku": variation.get("sku", ""),
                    "stock_quantity": variation.get("stock_quantity"),
                    "stock_status": variation.get("stock_status", "instock"),
                    "attributes": variation.get("attributes", []),
                }
                if variation.get("image"):
                    var_payload["image"] = variation["image"]

                api.post(f"products/{new_product_id}/variations", var_payload)

            logger.info(
                "Pushed %d variations for product %s",
                len(product.variations_data),
                new_product_id,
            )

        # Mark as synced
        product.status = ProductSync.Status.SYNCED
        product.save(update_fields=["status"])

    except Exception as exc:
        logger.error("push_to_target_task failed for product %s: %s", product_id, exc)
        raise self.retry(exc=exc)
