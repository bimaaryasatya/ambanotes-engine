import re

services = [
    'auth_service/auth_service.py',
    'document_service/document_service.py',
    'ai_service/ai_service.py',
    'classification_service/classification_service.py',
    'ocr_service/ocr_service.py',
    'ner_service/ner_service.py',
    'insight_service/insight_service.py',
    'reminder_service/reminder.py',
    'generator_service/generator.py',
    'notification_service/notif.py',
]

for s in services:
    with open(s, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"\n=== {s} ===")
    for i, line in enumerate(lines):
        # Find route decorators
        if '@' in line and '.route(' in line:
            route_match = re.search(r"\.route\(['\"](.+?)['\"]", line)
            route = route_match.group(1) if route_match else "?"
            
            # Find the def line (within next 5 lines)
            func_name = "?"
            func_line = i
            for j in range(i+1, min(i+5, len(lines))):
                m = re.match(r'\s*def (\w+)\(', lines[j])
                if m:
                    func_name = m.group(1)
                    func_line = j
                    break
            
            # Check if there's a swagger docstring (look for '---' within the next 10 lines after def)
            has_swagger = False
            for j in range(func_line+1, min(func_line+15, len(lines))):
                if '---' in lines[j] and '"""' not in lines[j]:
                    has_swagger = True
                    break
                if lines[j].strip() and not lines[j].strip().startswith('"""') and not lines[j].strip().startswith('#'):
                    # Hit actual code before finding ---
                    break
            
            status = "[OK] HAS SWAGGER" if has_swagger else "[!!] NO SWAGGER"
            print(f"  {route:40s} -> {func_name:25s} {status}")
