#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filter file processing tool
- Replace SetFontSize xx with SetFontSize $fontsize
- Remove MinimapIcon lines
- Apply tier configuration to enable/disable tiers
"""

import re
import json
import argparse
from pathlib import Path
from typing import Dict

def load_tier_config(config_path: Path) -> Dict[str, bool]:
    """Load tier configuration from JSON file"""
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    tier_config = {}
    if 'tiers' in config:
        for tier_name, tier_data in config['tiers'].items():
            if isinstance(tier_data, dict):
                tier_config[tier_name] = tier_data.get('enabled', True)
            else:
                tier_config[tier_name] = bool(tier_data)
    
    return tier_config


def apply_tier_config(filter_content: str, tier_config: Dict[str, bool]) -> str:
    """Apply tier configuration to filter content"""
    lines = filter_content.split('\n')
    result_lines = []
    
    tier_pattern = r'\$tier->(\w+)'
    current_rule_lines = []
    current_tier = None
    in_rule = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        is_commented = stripped.startswith('#')
        
        # Check for Show/Hide
        if stripped.startswith('Show') or stripped.startswith('Hide'):
            # Process previous rule
            if in_rule and current_tier is not None:
                enabled = tier_config.get(current_tier, True)
                if not enabled:
                    # Comment out all lines in the rule
                    for rule_line in current_rule_lines:
                        if rule_line.strip() and not rule_line.strip().startswith('#'):
                            indent = len(rule_line) - len(rule_line.lstrip())
                            result_lines.append(' ' * indent + '#' + rule_line.lstrip())
                        else:
                            result_lines.append(rule_line)
                else:
                    # Uncomment all lines in the rule
                    for rule_line in current_rule_lines:
                        if rule_line.strip().startswith('#'):
                            decomment = rule_line.lstrip('#')
                            indent = len(rule_line) - len(rule_line.lstrip())
                            result_lines.append(' ' * indent + decomment.lstrip())
                        else:
                            result_lines.append(rule_line)
            else:
                result_lines.extend(current_rule_lines)
            
            # Start new rule
            current_rule_lines = [line]
            in_rule = True
            
            # Extract tier
            tier_match = re.search(tier_pattern, line)
            if tier_match:
                current_tier = tier_match.group(1)
            else:
                current_tier = None
        else:
            if in_rule:
                current_rule_lines.append(line)
                # Check if rule ends
                if stripped == '':
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        next_stripped = next_line.strip()
                        if (next_stripped.startswith('#') and '===' in next_stripped) or \
                           next_stripped.startswith('Show') or next_stripped.startswith('Hide') or \
                           (next_stripped and not next_line.startswith('\t') and not next_line.startswith(' ')):
                            # Process current rule
                            if current_tier is not None:
                                enabled = tier_config.get(current_tier, True)
                                if not enabled:
                                    for rule_line in current_rule_lines:
                                        if rule_line.strip() and not rule_line.strip().startswith('#'):
                                            indent = len(rule_line) - len(rule_line.lstrip())
                                            result_lines.append(' ' * indent + '#' + rule_line.lstrip())
                                        else:
                                            result_lines.append(rule_line)
                                else:
                                    for rule_line in current_rule_lines:
                                        if rule_line.strip().startswith('#'):
                                            decomment = rule_line.lstrip('#')
                                            indent = len(rule_line) - len(rule_line.lstrip())
                                            result_lines.append(' ' * indent + decomment.lstrip())
                                        else:
                                            result_lines.append(rule_line)
                            else:
                                result_lines.extend(current_rule_lines)
                            
                            current_rule_lines = []
                            current_tier = None
                            in_rule = False
            else:
                result_lines.append(line)
    
    # Handle last rule
    if in_rule and current_rule_lines:
        if current_tier is not None:
            enabled = tier_config.get(current_tier, True)
            if not enabled:
                for rule_line in current_rule_lines:
                    if rule_line.strip() and not rule_line.strip().startswith('#'):
                        indent = len(rule_line) - len(rule_line.lstrip())
                        result_lines.append(' ' * indent + '#' + rule_line.lstrip())
                    else:
                        result_lines.append(rule_line)
            else:
                for rule_line in current_rule_lines:
                    if rule_line.strip().startswith('#'):
                        decomment = rule_line.lstrip('#')
                        indent = len(rule_line) - len(rule_line.lstrip())
                        result_lines.append(' ' * indent + decomment.lstrip())
                    else:
                        result_lines.append(rule_line)
        else:
            result_lines.extend(current_rule_lines)
    
    return '\n'.join(result_lines)


def process_filter(args):
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: File not found - {input_path}")
        return
    
    # Determine output file path
    if args.output is None:
        # Auto-generate output filename: add _new suffix to original filename
        output_path = input_path.parent / f"{input_path.stem}_new{input_path.suffix}"
    else:
        output_path = Path(args.output)
    
    # Read file content
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error: Cannot read file - {e}")
        return
    
    # Process SetFontSize replacement
    if args.fontsize is not None:
        content = replace_fontsize(content, args.fontsize)
    
    # Remove MinimapIcon lines
    if args.remove_minimapicon:
        content = remove_minimapicon(content)
    
    # Apply tier configuration
    if args.tier_config:
        config_path = Path(args.tier_config)
        if not config_path.exists():
            print(f"Error: Config file not found: {config_path}")
            return
        
        print(f"Loading tier configuration from: {config_path}")
        tier_config = load_tier_config(config_path)
        print(f"Loaded {len(tier_config)} tier configurations")
        
        enabled_count = sum(1 for v in tier_config.values() if v)
        disabled_count = len(tier_config) - enabled_count
        print(f"  Enabled: {enabled_count}, Disabled: {disabled_count}")
        
        print("Applying tier configuration...")
        content = apply_tier_config(content, tier_config)
    
    # Write to new file
    try:
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Success: Output file created - {output_path}")
    except Exception as e:
        print(f"Error: Cannot write file - {e}")


def replace_fontsize(content, fontsize_param='35'):
    """Replace all SetFontSize xx with SetFontSize fontsize_param"""
    # Use regex to replace SetFontSize numbers
    # Pattern: SetFontSize followed by one or more digits
    # Preserve leading whitespace (tabs or spaces)
    pattern = r'(\s*SetFontSize\s+)\d+'
    replacement = r'\1' + fontsize_param
    
    # Count number of matches before replacement
    matches = len(re.findall(r'\s*SetFontSize\s+\d+', content))
    
    # Perform replacement
    new_content = re.sub(pattern, replacement, content)
    
    if matches == 0:
        print(f"Warning: No SetFontSize statements found")
    else:
        print(f"Found {matches} SetFontSize statements, all replaced with SetFontSize {fontsize_param}")
    
    return new_content


def remove_minimapicon(content):
    """Remove all MinimapIcon lines (including commented ones)"""
    # Pattern to match MinimapIcon lines with optional leading whitespace and comment
    # Matches: "MinimapIcon ..." or "# MinimapIcon ..." or "\tMinimapIcon ..." etc.
    pattern = r'^\s*#?\s*MinimapIcon\s+.*$'
    
    lines = content.split('\n')
    original_count = len(lines)
    
    # Remove lines matching MinimapIcon pattern
    new_lines = [line for line in lines if not re.match(pattern, line)]
    
    removed_count = original_count - len(new_lines)
    
    if removed_count == 0:
        print(f"Warning: No MinimapIcon statements found")
    else:
        print(f"Removed {removed_count} MinimapIcon statement(s)")
    
    return '\n'.join(new_lines)


def main():
    parser = argparse.ArgumentParser(
        description='Filter file processing tool - SetFontSize, MinimapIcon, and tier configuration'
    )
    parser.add_argument(
        'input_file',
        type=str,
        help='Input .filter file path (e.g., PoE/filter/0.4.filter)'
    )
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=None,
        help='Output .filter file path (if not specified, auto-generate as original_filename_new.filter)'
    )
    parser.add_argument(
        '-fs', '--fontsize',
        type=str,
        default=None,
        help='Replace SetFontSize xx with SetFontSize <value> (e.g., 35)'
    )
    parser.add_argument(
        '-rm', '--remove-minimapicon',
        action='store_true',
        help='Remove all MinimapIcon statements from the filter file'
    )
    parser.add_argument(
        '-tc', '--tier-config',
        type=str,
        default=None,
        help='Apply tier configuration JSON file to enable/disable tiers'
    )
    
    args = parser.parse_args()
    process_filter(args)


if __name__ == '__main__':
    main()