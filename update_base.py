import re

with open('sync_app/templates/base.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Swap main and aside
main_regex = re.compile(r'(<!-- ═══════ Main Content Area ═══════ -->.*?</main>)', re.DOTALL)
aside_regex = re.compile(r'(<!-- ═══════ Right Sidebar \(Fixed\) ═══════ -->.*?</aside>)', re.DOTALL)

main_match = main_regex.search(content)
aside_match = aside_regex.search(content)

if main_match and aside_match:
    main_text = main_match.group(1)
    aside_text = aside_match.group(1)
    
    # Change aside border
    aside_text = aside_text.replace('border-r', 'border-l')

    # Find where the main and aside start and end
    # They are wrapped in `<div class="flex min-h-screen">`
    # It's easier to just do string replacements since they are contiguous.
    # Actually, we can replace the whole block from main to aside
    start_idx = main_match.start()
    end_idx = aside_match.end()
    
    new_block = aside_text + '\n\n    ' + main_text
    content = content[:start_idx] + new_block + content[end_idx:]
    
    # Now add the AI Settings link
    ai_settings_link = """
        <!-- AI Settings -->
        <a href="{% url 'sync_app:ai_settings' %}"
           class="nav-item {% if request.resolver_match.url_name == 'ai_settings' %}active{% endif %}
                  flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium text-slate-600 transition-colors">
          <svg class="w-[18px] h-[18px] flex-shrink-0" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/>
          </svg>
          تنظیمات AI
        </a>"""
        
    content = content.replace('تنظیمات API\n        </a>', 'تنظیمات API\n        </a>\n' + ai_settings_link)
    
    with open('sync_app/templates/base.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Updated base.html successfully.")
else:
    print("Could not find main or aside tags.")
