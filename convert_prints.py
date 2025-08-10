#!/usr/bin/env python3
"""Convert all print statements to debug_log calls"""
import os
import re

def convert_file(filepath):
    """Convert print statements to debug_log in a single file"""
    
    # Determine category based on file path
    if 'ai' in filepath.lower():
        if 'economy' in filepath:
            category = 'AI_ECONOMY'
        elif 'military' in filepath:
            category = 'AI_MILITARY'
        elif 'exploration' in filepath:
            category = 'AI_EXPLORE'
        elif 'resource' in filepath:
            category = 'AI_RESOURCE'
        elif 'base_module' in filepath:
            category = 'AI_MODULE'
        else:
            category = 'AI'
    elif 'movement' in filepath:
        category = 'MOVEMENT'
    elif 'building' in filepath:
        category = 'BUILDING'
    elif 'gathering' in filepath:
        category = 'GATHERING'
    elif 'production' in filepath:
        category = 'PRODUCTION'
    elif 'combat' in filepath:
        category = 'COMBAT'
    elif 'unit_watchdog' in filepath:
        category = 'WATCHDOG'
    else:
        category = 'GENERAL'
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Check if already has debug_log import
    has_import = 'from utils.debug_logger import debug_log' in content
    
    # Replace print statements
    modified = False
    lines = content.split('\n')
    new_lines = []
    
    for line in lines:
        # Match print statements
        match = re.match(r'^(\s*)print\((.*)\)(\s*)$', line)
        if match:
            indent = match.group(1)
            print_content = match.group(2)
            trailing = match.group(3)
            
            # Skip if it's a debug print about debug files
            if 'debug file' in print_content.lower() or 'debug_log' in print_content:
                new_lines.append(line)
                continue
                
            new_line = f'{indent}debug_log.log({print_content}, "{category}"){trailing}'
            new_lines.append(new_line)
            modified = True
        else:
            new_lines.append(line)
    
    if modified and not has_import:
        # Add import at the top after other imports
        import_added = False
        for i, line in enumerate(new_lines):
            if line.startswith('from ') or line.startswith('import '):
                continue
            elif not line.strip() and i > 0:
                # Found empty line after imports
                new_lines.insert(i, 'from utils.debug_logger import debug_log')
                import_added = True
                break
        
        if not import_added:
            # No imports found, add at top
            new_lines.insert(0, 'from utils.debug_logger import debug_log')
    
    if modified:
        with open(filepath, 'w') as f:
            f.write('\n'.join(new_lines))
        print(f"Converted {filepath}")
        return True
    return False

# Files to convert
files_to_convert = [
    'systems/ai/economy_module.py',
    'systems/ai/military_module.py',
    'systems/ai/exploration_module.py',
    'systems/ai/resource_manager.py',
    'systems/ai/base_module.py',
    'systems/ai/modular_ai_system.py',
    'systems/movement_system.py',
    'systems/building_system.py',
    'systems/gathering_manager.py',
    'systems/production_manager.py',
    'systems/unit_watchdog.py',
    'systems/ai_system.py',
    'core/game.py',
    'entities/objects.py'
]

converted_count = 0
for file in files_to_convert:
    filepath = f'/mnt/c/programming/python/rts-v2/{file}'
    if os.path.exists(filepath):
        if convert_file(filepath):
            converted_count += 1

print(f"\nConverted {converted_count} files")