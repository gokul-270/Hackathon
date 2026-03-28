#!/usr/bin/env python3
"""
Intelligent TODO Cleanup Script
Removes completed and obsolete TODOs from codebase based on verification data.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Set, Tuple
import json
from datetime import datetime

# Categories of TODOs to remove
COMPLETED_PATTERNS = [
    # ROS1 to ROS2 migration (100% complete)
    
    # Build system (all packages build)
    
    # Motor control implementation (verified complete)
    
    # Cotton detection Phase 1 (operational at 84%)
    
    # Already implemented features
    
    # Specific completed items from audit
]

OBSOLETE_PATTERNS = [
    # ODrive legacy (replaced by MG6010)
    
    # RealSense (reverted to OAK-D Lite)
    
    # ROS1 bridge (full ROS2 migration)
    
    # Old config formats (YAML standard now)
    
    # ROS Melodic (ROS2 Jazzy only)
    
    # CANopen for MG6010 (using proprietary protocol)
    
    # Intermediate service layer (direct topic communication)
    
    # Temp file polling (signal-based now)
    
    # Manual parameter loading (YAML-based now)
]

# Patterns to KEEP (active work)
KEEP_PATTERNS = [
    # Hardware validation (waiting for hardware)
    r'TODO.*(?:Test.*actual.*MG6010|Test.*real.*cotton|hardware.*test|Validate.*CAN|Calibrate.*camera)',
    
    # Phase 2/3 features (planned future work)
    r'TODO.*(?:Phase [23]|direct.*DepthAI|pure.*C\+\+.*detection)',
    
    # Performance optimization (valid backlog)
    r'TODO.*(?:Optimize|optimize|performance|Performance|benchmark|Benchmark)',
    
    # Documentation improvements (valid backlog)
    r'TODO.*(?:Add.*documentation|Document|documentation|API.*doc)',
    
    # Error handling (valid backlog)
    r'TODO.*(?:error.*handling|recovery|reconnection)',
    
    # Testing (valid backlog)
    r'TODO.*(?:unit.*test|integration.*test|stress.*test)',
    
    # Developer tasks (valid implementation notes)
    r'TODO\(developer\)',
]


class TODOCleaner:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.stats = {
            'files_scanned': 0,
            'files_modified': 0,
            'todos_removed': 0,
            'todos_kept': 0,
            'completed_removed': 0,
            'obsolete_removed': 0,
        }
        self.removed_todos = []
        self.kept_todos = []
        
    def should_remove_todo(self, line: str, todo_text: str) -> Tuple[bool, str]:
        """Determine if a TODO should be removed and why."""
        
        # First check if it should be kept (highest priority)
        for pattern in KEEP_PATTERNS:
            if re.search(pattern, todo_text, re.IGNORECASE):
                return False, "keep_pattern_match"
        
        # Check if it's completed
        for pattern in COMPLETED_PATTERNS:
            if re.search(pattern, todo_text, re.IGNORECASE):
                return True, "completed"
        
        # Check if it's obsolete
        for pattern in OBSOLETE_PATTERNS:
            if re.search(pattern, todo_text, re.IGNORECASE):
                return True, "obsolete"
        
        return False, "no_match"
    
    def extract_todo_text(self, line: str) -> str:
        """Extract the full TODO text from a line."""
        match = re.search(r'(TODO|FIXME|XXX).*$', line, re.IGNORECASE)
        return match.group(0) if match else ""
    
    def process_file(self, file_path: Path) -> bool:
        """Process a single file and remove completed/obsolete TODOs."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"  ⚠️  Error reading {file_path}: {e}")
            return False
        
        new_lines = []
        file_modified = False
        todos_in_file = 0
        removed_in_file = 0
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Check if line contains TODO/FIXME/XXX
            if re.search(r'\b(TODO|FIXME|XXX)\b', line, re.IGNORECASE):
                todos_in_file += 1
                todo_text = self.extract_todo_text(line)
                should_remove, reason = self.should_remove_todo(line, todo_text)
                
                if should_remove:
                    # Remove the line
                    file_modified = True
                    removed_in_file += 1
                    self.removed_todos.append({
                        'file': str(file_path.relative_to(self.root_dir)),
                        'line': i + 1,
                        'text': todo_text.strip(),
                        'reason': reason
                    })
                    
                    if reason == "completed":
                        self.stats['completed_removed'] += 1
                    elif reason == "obsolete":
                        self.stats['obsolete_removed'] += 1
                    
                    # Skip this line
                    i += 1
                    continue
                else:
                    self.kept_todos.append({
                        'file': str(file_path.relative_to(self.root_dir)),
                        'line': i + 1,
                        'text': todo_text.strip(),
                        'reason': reason
                    })
                    self.stats['todos_kept'] += 1
            
            new_lines.append(line)
            i += 1
        
        if file_modified:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                self.stats['files_modified'] += 1
                self.stats['todos_removed'] += removed_in_file
                print(f"  ✅ {file_path.relative_to(self.root_dir)}: Removed {removed_in_file}/{todos_in_file} TODOs")
                return True
            except Exception as e:
                print(f"  ⚠️  Error writing {file_path}: {e}")
                return False
        
        return False
    
    def scan_directory(self, extensions: List[str]):
        """Scan directory for files with given extensions."""
        for ext in extensions:
            for file_path in self.root_dir.rglob(f'*{ext}'):
                # Skip archived and generated files
                if any(skip in str(file_path) for skip in ['archive/', '_generated/', '.git/', 'build/']):
                    continue
                
                self.stats['files_scanned'] += 1
                self.process_file(file_path)
    
    def generate_report(self, output_path: Path):
        """Generate cleanup report."""
        report = f"""# TODO Cleanup Report
**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Branch:** feature/todo-cleanup-2025-10-14

---

## Summary

| Metric | Count |
|--------|-------|
| Files Scanned | {self.stats['files_scanned']} |
| Files Modified | {self.stats['files_modified']} |
| TODOs Removed | {self.stats['todos_removed']} |
| TODOs Kept (Active) | {self.stats['todos_kept']} |
| - Completed Items | {self.stats['completed_removed']} |
| - Obsolete Items | {self.stats['obsolete_removed']} |

**Reduction:** {self.stats['todos_removed']}/{self.stats['todos_removed'] + self.stats['todos_kept']} TODOs removed ({100 * self.stats['todos_removed'] / (self.stats['todos_removed'] + self.stats['todos_kept']) if (self.stats['todos_removed'] + self.stats['todos_kept']) > 0 else 0:.1f}%)

---

## Removed TODOs by Category

### Completed Items ({self.stats['completed_removed']})
"""
        
        completed = [t for t in self.removed_todos if t['reason'] == 'completed']
            report += f"- `{todo['file']}:{todo['line']}` - {todo['text']}\n"
        
        if len(completed) > 50:
            report += f"\n*...and {len(completed) - 50} more*\n"
        
        report += f"\n### Obsolete Items ({self.stats['obsolete_removed']})\n"
        obsolete = [t for t in self.removed_todos if t['reason'] == 'obsolete']
        for todo in obsolete[:50]:
            report += f"- `{todo['file']}:{todo['line']}` - {todo['text']}\n"
        
        if len(obsolete) > 50:
            report += f"\n*...and {len(obsolete) - 50} more*\n"
        
        report += f"""

---

## Active TODOs Preserved ({self.stats['todos_kept']})

These TODOs remain in the codebase as active work:

### Hardware Validation
"""
        
        hw_todos = [t for t in self.kept_todos if 'hardware' in t['text'].lower() or 'test' in t['text'].lower()]
        for todo in hw_todos[:20]:
            report += f"- `{todo['file']}:{todo['line']}` - {todo['text']}\n"
        
        report += """

### Future Features (Phase 2/3)
"""
        phase_todos = [t for t in self.kept_todos if 'phase' in t['text'].lower()]
        for todo in phase_todos[:20]:
            report += f"- `{todo['file']}:{todo['line']}` - {todo['text']}\n"
        
        report += """

### Other Active Work
"""
        other_todos = [t for t in self.kept_todos if t not in hw_todos and t not in phase_todos]
        for todo in other_todos[:30]:
            report += f"- `{todo['file']}:{todo['line']}` - {todo['text']}\n"
        
        report += f"""

---

## Verification

To verify the cleanup:
```bash
# Count remaining TODOs in code
grep -r "TODO\\|FIXME\\|XXX" --include="*.py" --include="*.cpp" --include="*.h" src/ scripts/ | wc -l

# Count remaining TODOs in docs
grep -r "TODO\\|FIXME\\|XXX" --include="*.md" docs/ | wc -l

# Review changes
git diff --stat
```

---

## Next Steps

1. ✅ Review this report
2. ⏭️ Run build validation (`colcon build`)
3. ⏭️ Commit changes
4. ⏭️ Update TODO_CONSOLIDATED.md with new counts

---

**Full data available in:**
- `{output_path.parent}/todo_cleanup_removed.json` - All removed TODOs
- `{output_path.parent}/todo_cleanup_kept.json` - All kept TODOs
"""
        
        with open(output_path, 'w') as f:
            f.write(report)
        
        # Save JSON data
        with open(output_path.parent / 'todo_cleanup_removed.json', 'w') as f:
            json.dump(self.removed_todos, f, indent=2)
        
        with open(output_path.parent / 'todo_cleanup_kept.json', 'w') as f:
            json.dump(self.kept_todos, f, indent=2)
        
        print(f"\n📄 Report saved to: {output_path}")


def main():
    root_dir = Path(__file__).resolve().parents[2]  # Go up to repo root
    
    print("=" * 80)
    print("=" * 80)
    print(f"Root: {root_dir}\n")
    
    cleaner = TODOCleaner(root_dir)
    
    # Process code files
    print("🔍 Scanning code files...")
    cleaner.scan_directory(['.cpp', '.h', '.hpp', '.py', '.launch.py'])
    
    # Process documentation (be more conservative here)
    print("\n🔍 Scanning documentation files...")
    cleaner.scan_directory(['.md'])
    
    # Generate report
    print("\n📊 Generating report...")
    report_path = root_dir / 'docs' / '_generated' / 'TODO_CLEANUP_REPORT.md'
    cleaner.generate_report(report_path)
    
    print("\n" + "=" * 80)
    print("CLEANUP COMPLETE")
    print("=" * 80)
    print(f"✅ Files modified: {cleaner.stats['files_modified']}")
    print(f"✅ TODOs removed: {cleaner.stats['todos_removed']}")
    print(f"   - Completed: {cleaner.stats['completed_removed']}")
    print(f"   - Obsolete: {cleaner.stats['obsolete_removed']}")
    print(f"📋 TODOs kept (active): {cleaner.stats['todos_kept']}")
    print(f"\n📄 Report: {report_path}")
    print("\nNext: Run 'colcon build' to verify integrity")


if __name__ == '__main__':
    main()
