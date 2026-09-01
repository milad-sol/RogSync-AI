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

from .models import AiSettings, ProductSync, PromptTemplate, GlobalKeyword

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _source_api():
    """Return a WooCommerce API client for the source store."""
    return WooAPI(
        url=settings.WC_SOURCE_URL,
        consumer_key=settings.WC_SOURCE_KEY,
        consumer_secret=settings.WC_SOURCE_SECRET,
        version="wc/v3",
        timeout=30,
    )


def _target_api():
    """Return a WooCommerce API client for the target store."""
    return WooAPI(
        url=settings.WC_TARGET_URL,
        consumer_key=settings.WC_TARGET_KEY,
        consumer_secret=settings.WC_TARGET_SECRET,
        version="wc/v3",
        timeout=30,
    )


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
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Task 1: Fetch Products from Source
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def fetch_products_task(self, category_id: int, limit: int = 20):
    """
    Fetch products from the source WooCommerce store by category.

    For variable products, makes a secondary request to get variations.
    Creates or updates ProductSync records with status=FETCHED.
    """
    api = _source_api()
    fetched_ids = []

    try:
        # Paginate through products in the category
        page = 1
        total_fetched = 0

        while total_fetched < limit:
            per_page = min(limit - total_fetched, 100)
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

            if not products:
                break

            for product in products:
                # Extract image data
                images_data = [
                    {"src": img.get("src", ""), "alt": img.get("alt", "")}
                    for img in product.get("images", [])
                ]

                # Extract attributes
                attributes = product.get("attributes", [])

                # For variable products, fetch variations
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

                # Create or update the ProductSync record
                obj, created = ProductSync.objects.update_or_create(
                    source_id=product["id"],
                    defaults={
                        "title": product.get("name", ""),
                        "original_slug": product.get("slug", ""),
                        "product_type": product.get("type", "simple"),
                        "original_desc": product.get("description", ""),
                        "original_short_desc": product.get("short_description", ""),
                        "attributes": attributes,
                        "images_data": images_data,
                        "variations_data": variations_data,
                        "status": ProductSync.Status.FETCHED,
                    },
                )
                fetched_ids.append(obj.pk)
                total_fetched += 1

                if total_fetched >= limit:
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
      1. Generate SEO target keywords from the product title.
      2. Rewrite the main description (preserving HTML structure and links).
      3. Lightly tweak the short description.
      4. Generate SEO-optimized alt text for images.
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
        # Merge keywords from 2 sources: product, template (global keywords handled separately)
        ai_settings = AiSettings.load()
        
        # Get active global keywords ordered by priority descending
        global_kws = list(GlobalKeyword.objects.filter(is_active=True).order_by("-priority").values_list("word", flat=True))
        global_kws_str = ", ".join(global_kws)
        
        merged_kws = []
        for kw_source in [product.target_keywords, prompt_template.target_keywords]:
            if kw_source:
                # Split by comma and strip whitespace
                kws = [k.strip() for k in kw_source.split(",") if k.strip()]
                merged_kws.extend(kws)
                
        # Deduplicate while preserving order
        unique_kws = []
        for kw in merged_kws:
            if kw not in unique_kws:
                unique_kws.append(kw)
                
        if unique_kws:
            product.target_keywords = ", ".join(unique_kws)
        else:
            # Fall back to auto-generation
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

        # ── Step 2: Rewrite main description ───
        if product.original_desc:
            global_kws_instruction = ""
            if global_kws_str:
                global_kws_instruction = f"- CRITICAL: You must naturally inject these high-priority global keywords into the generated product description based on relevance: {global_kws_str}\n"

            main_prompt = (
                f"{prompt_template.main_desc_prompt}\n\n"
                f"Target SEO keywords: {product.target_keywords}\n\n"
                f"IMPORTANT RULES:\n"
                f"- You MUST preserve ALL original HTML tags, links, and structure.\n"
                f"- Inject the keywords naturally into the text.\n"
                f"{global_kws_instruction}"
                f"- The output must be unique and not duplicate the original.\n"
                f"- Return ONLY the rewritten HTML, no explanations.\n\n"
                f"Original HTML description:\n{product.original_desc}"
            )
            product.generated_desc = _openrouter_chat(
                system_prompt="You are a professional product copywriter and SEO specialist.",
                user_prompt=main_prompt,
            ).strip()

        # ── Step 3: Rewrite short description ──
        if product.original_short_desc:
            short_prompt = (
                f"{prompt_template.short_desc_prompt}\n\n"
                f"Target SEO keywords: {product.target_keywords}\n\n"
                f"IMPORTANT: Make only a minor tweak. Do NOT change it drastically. "
                f"Preserve the HTML tags. Return ONLY the rewritten HTML.\n\n"
                f"Original short description:\n{product.original_short_desc}"
            )
            product.generated_short_desc = _openrouter_chat(
                system_prompt="You are a product copywriter.",
                user_prompt=short_prompt,
            ).strip()

        # ── Step 4: Generate image alt texts ───
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
