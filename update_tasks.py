import re

with open('sync_app/tasks.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update imports
content = content.replace(
    'from .models import ProductSync, PromptTemplate',
    'from .models import AiSettings, ProductSync, PromptTemplate'
)

# 2. Update _openrouter_chat
old_or_chat = """def _openrouter_chat(system_prompt: str, user_prompt: str) -> str:
    \"\"\"Send a chat completion request to the OpenRouter API and return the response text.\"\"\"
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        },
        timeout=120,
    )"""

new_or_chat = """def _openrouter_chat(system_prompt: str, user_prompt: str) -> str:
    \"\"\"Send a chat completion request to the OpenRouter API and return the response text.\"\"\"
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
    )"""
content = content.replace(old_or_chat, new_or_chat)

# 3. Update process_ai_rewrite_task
old_step1 = """        # ── Step 1: Generate SEO keywords ──────
        keywords_prompt = (
            "You are an SEO expert. Given the following product title, generate "
            "5-8 highly relevant SEO keywords in the same language as the title. "
            "Return ONLY the keywords separated by commas, nothing else.\\n\\n"
            f"Product title: {product.title}"
        )
        keywords_result = _openrouter_chat(
            system_prompt="You are an SEO keyword research specialist.",
            user_prompt=keywords_prompt,
        )
        product.target_keywords = keywords_result.strip()"""

new_step1 = """        # ── Step 1: Handle SEO keywords ────────
        # Merge keywords from 3 sources: product, template, global
        ai_settings = AiSettings.load()
        
        merged_kws = []
        for kw_source in [product.target_keywords, prompt_template.target_keywords, ai_settings.global_keywords]:
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
                "Return ONLY the keywords separated by commas, nothing else.\\n\\n"
                f"Product title: {product.title}"
            )
            keywords_result = _openrouter_chat(
                system_prompt="You are an SEO keyword research specialist.",
                user_prompt=keywords_prompt,
            )
            product.target_keywords = keywords_result.strip()"""

content = content.replace(old_step1, new_step1)

with open('sync_app/tasks.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated tasks.py successfully.")
