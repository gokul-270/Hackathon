#!/usr/bin/env python3
"""
Fix broken markdown links identified in broken_links.csv
Reads the CSV and applies fixes to markdown files.
"""

import csv
import os
import re
from pathlib import Path

def fix_broken_links(csv_path: str, dry_run: bool = False):
    """
    Fix broken markdown links from CSV report.
    
    Args:
        csv_path: Path to broken_links.csv
        dry_run: If True, only print what would be changed
    """
    fixes_by_file = {}
    skipped_links = []
    
    # Read the CSV
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            from_file = row['from_file']
            line_num = int(row['line'])
            link_snippet = row['link_snippet']
            resolved_target = row['resolved_target']
            
            # Skip certain problematic patterns
            # 1. Lambda captures and C++ code (contains "this" or function signatures)
            if '](const ' in link_snippet or '](std::' in link_snippet:
                skipped_links.append((from_file, line_num, 'C++ code, not a real link'))
                continue
            
            # 2. Regex patterns or placeholders
            if '](.*.md)' in link_snippet or '](.*\\]' in link_snippet or '[relevant_file]' in link_snippet:
                skipped_links.append((from_file, line_num, 'Placeholder/regex pattern'))
                continue
            
            # 3. Generic placeholders
            if 'link to other related reports' in link_snippet:
                skipped_links.append((from_file, line_num, 'Generic placeholder'))
                continue
            
            # Extract the current link path and link text
            match = re.match(r'\[(.*?)\]\((.*?)\)', link_snippet)
            if not match:
                skipped_links.append((from_file, line_num, 'Could not parse link'))
                continue
            
            link_text = match.group(1)
            old_path = match.group(2)
            
            # Calculate the correct relative path from from_file to resolved_target
            from_dir = Path(from_file).parent
            target_path = Path(resolved_target)
            
            # Check if target exists
            if not target_path.exists():
                skipped_links.append((from_file, line_num, f'Target does not exist: {resolved_target}'))
                continue
            
            # Calculate relative path
            try:
                new_path = os.path.relpath(target_path, from_dir)
            except ValueError:
                # On different drives (Windows) - use absolute path
                new_path = str(target_path)
            
            # Store the fix
            if from_file not in fixes_by_file:
                fixes_by_file[from_file] = []
            
            fixes_by_file[from_file].append({
                'line': line_num,
                'old_link': link_snippet,
                'new_link': f'[{link_text}]({new_path})',
                'old_path': old_path,
                'new_path': new_path
            })
    
    # Apply fixes
    total_fixed = 0
    total_files = len(fixes_by_file)
    
    print(f"{'DRY RUN: ' if dry_run else ''}Fixing broken links in {total_files} files...")
    print()
    
    for file_path, fixes in fixes_by_file.items():
        if not Path(file_path).exists():
            print(f"⚠️  File does not exist: {file_path}")
            continue
        
        # Read the file
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Apply fixes (in reverse order to maintain line numbers)
        fixes_applied = 0
        for fix in sorted(fixes, key=lambda x: x['line'], reverse=True):
            line_idx = fix['line'] - 1
            if line_idx < len(lines):
                old_line = lines[line_idx]
                # Replace only the specific link
                new_line = old_line.replace(fix['old_link'], fix['new_link'])
                if new_line != old_line:
                    lines[line_idx] = new_line
                    fixes_applied += 1
        
        if fixes_applied > 0:
            if not dry_run:
                # Write back
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
            
            print(f"✅ {Path(file_path).name}: {fixes_applied} link(s) fixed")
            total_fixed += fixes_applied
    
    print()
    print(f"{'DRY RUN: ' if dry_run else ''}Summary:")
    print(f"  Files processed: {total_files}")
    print(f"  Links fixed: {total_fixed}")
    print(f"  Links skipped: {len(skipped_links)}")
    
    if skipped_links and dry_run:
        print()
        print("Skipped links (first 10):")
        for file_path, line, reason in skipped_links[:10]:
            print(f"  {Path(file_path).name}:{line} - {reason}")
    
    return total_fixed, len(skipped_links)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix broken markdown links')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be changed without making changes')
    parser.add_argument('--csv', default='docs/_reports/2025-10-21/broken_links.csv', help='Path to broken_links.csv')
    
    args = parser.parse_args()
    
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"❌ Error: CSV file not found: {csv_path}")
        exit(1)
    
    fixed, skipped = fix_broken_links(str(csv_path), dry_run=args.dry_run)
    
    if args.dry_run:
        print()
        print("Run without --dry-run to apply changes.")
