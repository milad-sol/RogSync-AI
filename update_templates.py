import re

# Update api_settings.html
with open('sync_app/templates/sync_app/api_settings.html', 'r', encoding='utf-8') as f:
    api_html = f.read()

# Remove the OpenRouter block
api_html = re.sub(r'    <!-- ── OpenRouter ──────────────────── -->.*?    <!-- ── Save ────────────────────────── -->', '    <!-- ── Save ────────────────────────── -->', api_html, flags=re.DOTALL)

with open('sync_app/templates/sync_app/api_settings.html', 'w', encoding='utf-8') as f:
    f.write(api_html)


# Create ai_settings.html
ai_html = """{% extends "base.html" %}

{% block title %}تنظیمات هوش مصنوعی — RogSync AI{% endblock %}
{% block page_title %}تنظیمات هوش مصنوعی{% endblock %}

{% block content %}
<div class="max-w-3xl space-y-6">

  {% if saved %}
  <div class="bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-3 text-[13px] text-emerald-700 font-medium flex items-center gap-2 toast-enter">
    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>
    </svg>
    تنظیمات با موفقیت ذخیره شد.
  </div>
  {% endif %}

  <form method="post" class="space-y-6">
    {% csrf_token %}

    <!-- ── OpenRouter ──────────────────── -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <div class="flex items-center gap-3 mb-5">
        <div class="w-8 h-8 rounded-lg bg-violet-50 flex items-center justify-center">
          <svg class="w-4 h-4 text-violet-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/>
          </svg>
        </div>
        <div>
          <h3 class="text-[14px] font-semibold text-slate-800">OpenRouter API</h3>
          <p class="text-[12px] text-slate-400">تنظیمات مدل هوش مصنوعی برای بازنویسی</p>
        </div>
      </div>

      <div class="space-y-4">
        <div>
          <label class="block text-[13px] font-medium text-slate-600 mb-1.5">کلید API</label>
          <input type="password" name="openrouter_api_key" value="{{ settings.openrouter_api_key }}" dir="ltr"
                 placeholder="sk-or-xxxxxxxx"
                 class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-2.5 text-[13px] text-slate-700 font-mono placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-400 transition">
        </div>
        <div>
          <label class="block text-[13px] font-medium text-slate-600 mb-1.5">مدل AI</label>
          <input type="text" name="openrouter_model" value="{{ settings.openrouter_model }}" dir="ltr"
                 placeholder="openai/gpt-4o"
                 class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-2.5 text-[13px] text-slate-700 font-mono placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-400 transition">
          <p class="text-[11px] text-slate-400 mt-1">مثال: openai/gpt-4o, anthropic/claude-3.5-sonnet, google/gemini-pro</p>
        </div>
      </div>
    </div>
    
    <!-- ── Global Keywords ─────────────── -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <div class="flex items-center gap-3 mb-5">
        <div class="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center">
          <svg class="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14"/>
          </svg>
        </div>
        <div>
          <h3 class="text-[14px] font-semibold text-slate-800">کلمات کلیدی سراسری</h3>
          <p class="text-[12px] text-slate-400">این کلمات کلیدی در بازنویسی تمامی محصولات استفاده خواهند شد</p>
        </div>
      </div>

      <div>
        <textarea name="global_keywords" rows="3"
                  placeholder="مثال: گوشی ارزان, خرید آنلاین موبایل"
                  class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-[13px] text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-400 transition resize-y">{{ settings.global_keywords }}</textarea>
        <p class="text-[11px] text-slate-400 mt-2">کلمات کلیدی را با کاما (,) جدا کنید.</p>
      </div>
    </div>

    <!-- ── Save ────────────────────────── -->
    <div class="flex items-center justify-end">
      <button type="submit"
              class="bg-brand-600 hover:bg-brand-700 text-white text-[13px] font-semibold px-6 py-2.5 rounded-lg transition-all hover:shadow-md hover:shadow-brand-500/20 active:scale-[0.97]">
        ذخیره تنظیمات
      </button>
    </div>
  </form>

</div>
{% endblock %}
"""
with open('sync_app/templates/sync_app/ai_settings.html', 'w', encoding='utf-8') as f:
    f.write(ai_html)

# Update prompt_list.html
with open('sync_app/templates/sync_app/prompt_list.html', 'r', encoding='utf-8') as f:
    prompt_html = f.read()

# Insert keyword input in the form
keyword_input = """        <div>
          <label class="block text-[13px] font-medium text-slate-600 mb-1.5">کلمات کلیدی پیش‌فرض (اختیاری)</label>
          <input type="text" name="target_keywords"
                 placeholder="مثال: ساعت هوشمند, خرید ساعت"
                 class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-2.5 text-[13px] text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-400 transition">
        </div>"""
        
prompt_html = prompt_html.replace(
    """        <div class="flex items-center gap-2">""",
    keyword_input + '\n' + """        <div class="flex items-center gap-2">"""
)

# Insert keywords in the card view
keyword_display = """
    {% if prompt.target_keywords %}
    <div class="mb-4">
      <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">کلمات کلیدی</p>
      <div class="bg-slate-50 rounded-lg p-3 text-[13px] text-slate-600 leading-relaxed">{{ prompt.target_keywords }}</div>
    </div>
    {% endif %}"""

prompt_html = prompt_html.replace(
    """    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">""",
    keyword_display + '\n    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">'
)

with open('sync_app/templates/sync_app/prompt_list.html', 'w', encoding='utf-8') as f:
    f.write(prompt_html)

print("Updated templates successfully.")
