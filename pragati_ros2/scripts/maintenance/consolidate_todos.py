#!/usr/bin/env python3
"""
TODO Consolidation Script - Phase 2
Extracts, normalizes, classifies, and consolidates all TODOs from docs and code.
"""

import os
import re
import sys
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Set, Tuple
from datetime import datetime
from collections import defaultdict

class TodoItem:
    """Represents a single TODO item with metadata."""
    def __init__(self, title: str, source_file: str, line_num: int, raw_text: str):
        self.title = title
        self.source_file = source_file
        self.line_num = line_num
        self.raw_text = raw_text
        self.status = "backlog"  # backlog, future, done, obsolete, code-todo
        self.priority = "Medium"  # Critical, High, Medium, Low
        self.component = self._infer_component()
        self.hw_dependency = self._infer_hw_dependency()
        self.estimate_hours = None
        self.id = self._generate_id()
        
    def _generate_id(self) -> str:
        """Generate stable ID based on normalized title and source."""
        normalized = self.title.lower().strip()
        normalized = re.sub(r'[^\w\s-]', '', normalized)
        normalized = re.sub(r'\s+', '-', normalized)[:50]
        
        hash_input = f"{normalized}:{self.source_file}:{self.line_num}"
        hash_short = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        
        return f"T-PR2-2025-10-{hash_short}"
    
    def _infer_component(self) -> str:
        """Infer component from source file path."""
        if 'motor_control' in self.source_file:
            return "motor-control"
        elif 'cotton_detection' in self.source_file:
            return "cotton-detection"
        elif 'yanthra_move' in self.source_file:
            return "yanthra-move"
        elif 'common_utils' in self.source_file:
            return "common-utils"
        elif 'robo_description' in self.source_file:
            return "robo-description"
        elif 'pattern_finder' in self.source_file:
            return "pattern-finder"
        elif 'docs' in self.source_file:
            return "documentation"
        else:
            return "general"
    
    def _infer_hw_dependency(self) -> str:
        """Infer hardware dependency from text."""
        hw_keywords = [
            'motor', 'encoder', 'pwm', 'cotton', 'camera', 'sensor',
            'gantry', 'yanthra', 'actuator', 'gpio', 'can', 'hardware',
            'mg6010', 'oak-d', 'realsense', 'field', 'bench', 'rig'
        ]
        
        text_lower = (self.title + " " + self.raw_text).lower()
        
        if any(kw in text_lower for kw in ['hardware', 'actual', 'real', 'physical']):
            return "HW-blocked"
        elif any(kw in text_lower for kw in hw_keywords):
            return "HW-assist"
        else:
            return "SW-only"
    
    def classify_status(self):
        """Classify the TODO item's status."""
        text_lower = self.raw_text.lower()
        
        # Done indicators
        done_patterns = [
            r'\[x\]', r'complete', r'completed', r'done', r'merged',
            r'shipped', r'implemented', r'✅'
        ]
        if any(re.search(p, text_lower) for p in done_patterns):
            self.status = "done"
            return
        
        # Obsolete indicators
        obsolete_patterns = [
            r'odrive', r'deprecated', r'obsolete', r'superseded',
            r'replaced', r'realsense', r'ros1', r'melodic', r'dynamixel'
        ]
        if any(re.search(p, text_lower) for p in obsolete_patterns):
            self.status = "obsolete"
            return
        
        # Future/Parked indicators
        future_patterns = [
            r'phase 2', r'phase 3', r'later', r'parked', r'vnext',
            r'future', r'optional', r'nice-to-have'
        ]
        if any(re.search(p, text_lower) for p in future_patterns):
            self.status = "future"
            return
        
        # Code TODOs from source files
        if self.source_file.endswith(('.cpp', '.h', '.hpp', '.py')):
            if 'docs' not in self.source_file:
                self.status = "code-todo"
                return
        
        # Default to backlog
        self.status = "backlog"
    
    def classify_priority(self):
        """Classify priority based on keywords."""
        text_lower = self.raw_text.lower()
        
        if any(kw in text_lower for kw in ['critical', 'urgent', 'blocker', 'p0', 'security']):
            self.priority = "Critical"
        elif any(kw in text_lower for kw in ['high', 'important', 'p1']):
            self.priority = "High"
        elif any(kw in text_lower for kw in ['low', 'minor', 'p3', 'nice']):
            self.priority = "Low"
        else:
            self.priority = "Medium"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON export."""
        return {
            'id': self.id,
            'title': self.title,
            'status': self.status,
            'priority': self.priority,
            'component': self.component,
            'hw_dependency': self.hw_dependency,
            'estimate_hours': self.estimate_hours,
            'source_file': self.source_file,
            'line_num': self.line_num,
            'raw_text': self.raw_text
        }


class TodoConsolidator:
    """Main consolidator class."""
    
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.todos = []
        self.stats = defaultdict(int)
        
    def extract_from_code(self):
        """Extract TODOs from source code files."""
        print("🔍 Extracting TODOs from source code...")
        
        patterns = ['*.cpp', '*.h', '*.hpp', '*.py']
        for pattern in patterns:
            for file_path in self.root_dir.glob(f'src/**/{pattern}'):
                if 'deprecated' in str(file_path) or 'archive' in str(file_path):
                    continue
                self._extract_from_file(file_path)
        
        print(f"   Found {self.stats['code_todos']} code TODOs")
    
    def extract_from_docs(self):
        """Extract TODOs from documentation files."""
        print("🔍 Extracting TODOs from documentation...")
        
        doc_files = [
            'docs/TODO_MASTER.md',
            'docs/project-management/REMAINING_TASKS.md',
            'docs/project-management/GAP_ANALYSIS_OCT2025.md',
            'docs/project-management/COMPLETION_CHECKLIST.md',
            'docs/project-management/IMPLEMENTATION_PLAN_OCT2025.md',
        ]
        
        for doc_file in doc_files:
            file_path = self.root_dir / doc_file
            if file_path.exists():
                self._extract_from_markdown(file_path)
        
        print(f"   Found {self.stats['doc_todos']} documentation TODOs")
    
    def _extract_from_file(self, file_path: Path):
        """Extract TODOs from a single source file."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            for i, line in enumerate(lines, 1):
                if re.search(r'\b(TODO|FIXME|TBD)\b', line, re.IGNORECASE):
                    title = self._extract_title(line)
                    rel_path = str(file_path.relative_to(self.root_dir))
                    
                    todo = TodoItem(title, rel_path, i, line.strip())
                    todo.classify_status()
                    todo.classify_priority()
                    
                    self.todos.append(todo)
                    self.stats['code_todos'] += 1
        
        except Exception as e:
            print(f"   ⚠️  Error reading {file_path}: {e}")
    
    def _extract_from_markdown(self, file_path: Path):
        """Extract TODOs from a markdown file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            current_heading = ""
            for i, line in enumerate(lines, 1):
                # Track headings for context
                if line.startswith('#'):
                    current_heading = line.strip('#').strip()
                
                # Extract checklist items and explicit TODOs
                if re.match(r'^\s*-\s*\[([ x])\]', line) or 'TODO' in line.upper():
                    title = self._extract_title(line, current_heading)
                    rel_path = str(file_path.relative_to(self.root_dir))
                    
                    todo = TodoItem(title, rel_path, i, line.strip())
                    todo.classify_status()
                    todo.classify_priority()
                    
                    self.todos.append(todo)
                    self.stats['doc_todos'] += 1
        
        except Exception as e:
            print(f"   ⚠️  Error reading {file_path}: {e}")
    
    def _extract_title(self, line: str, heading: str = "") -> str:
        """Extract a clean title from a TODO line."""
        # Remove checkbox markers
        line = re.sub(r'-\s*\[([ x])\]', '', line)
        
        # Remove TODO/FIXME/TBD markers
        line = re.sub(r'\b(TODO|FIXME|TBD)(\([^)]+\))?:?', '', line, flags=re.IGNORECASE)
        
        # Remove comment markers
        line = re.sub(r'^//', '', line)
        line = re.sub(r'/\*|\*/', '', line)
        line = re.sub(r'#', '', line)
        
        # Clean and truncate
        title = line.strip()[:100]
        
        if not title and heading:
            title = heading[:100]
        
        return title or "Untitled TODO"
    
    def deduplicate(self):
        """Remove duplicate TODOs based on normalized text."""
        print("🔄 Deduplicating TODOs...")
        
        seen = set()
        unique_todos = []
        
        for todo in self.todos:
            # Normalize for comparison
            normalized = todo.title.lower().strip()
            normalized = re.sub(r'[^\w\s]', '', normalized)
            normalized = re.sub(r'\s+', ' ', normalized)
            
            if normalized not in seen:
                seen.add(normalized)
                unique_todos.append(todo)
            else:
                self.stats['duplicates'] += 1
        
        original_count = len(self.todos)
        self.todos = unique_todos
        print(f"   Removed {self.stats['duplicates']} duplicates ({original_count} → {len(self.todos)})")
    
    def generate_archives(self):
        """Generate archive files for completed and obsolete items."""
        print("📦 Generating archive files...")
        
        archive_dir = self.root_dir / 'docs' / 'archive' / '2025-10-15'
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Group by status
        by_status = defaultdict(list)
        for todo in self.todos:
            by_status[todo.status].append(todo)
        
        # Generate completed archive
        completed = by_status['done']
        if completed:
            self._write_archive(
                archive_dir / 'todos_completed.md',
                'Completed TODO Items',
                completed,
                "Tasks that have been verified as complete"
            )
            print(f"   ✅ Archived {len(completed)} completed items")
        
        # Generate obsolete archive
        obsolete = by_status['obsolete']
        if obsolete:
            self._write_archive(
                archive_dir / 'todos_obsolete.md',
                'Obsolete TODO Items',
                obsolete,
                "Tasks that are no longer relevant (deprecated features, replaced systems, etc.)"
            )
            print(f"   ❌ Archived {len(obsolete)} obsolete items")
    
    def _write_archive(self, file_path: Path, title: str, todos: List[TodoItem], description: str):
        """Write an archive file."""
        by_component = defaultdict(list)
        for todo in todos:
            by_component[todo.component].append(todo)
        
        with open(file_path, 'w') as f:
            f.write(f"# {title}\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write(f"**Count:** {len(todos)} items\n\n")
            f.write(f"{description}\n\n")
            f.write("---\n\n")
            
            for component in sorted(by_component.keys()):
                f.write(f"## {component.title()}\n\n")
                for todo in by_component[component]:
                    f.write(f"### {todo.id}: {todo.title}\n\n")
                    f.write(f"- **Source:** `{todo.source_file}:{todo.line_num}`\n")
                    f.write(f"- **Priority:** {todo.priority}\n")
                    f.write(f"- **Component:** {todo.component}\n")
                    f.write(f"- **Details:** {todo.raw_text}\n\n")
                
                f.write("\n")
    
    def generate_consolidated_todo_master(self):
        """Generate the consolidated TODO_MASTER.md with active items only."""
        print("📝 Generating consolidated TODO_MASTER.md...")
        
        # Get active items
        active = [t for t in self.todos if t.status in ['backlog', 'future', 'code-todo']]
        
        by_status = defaultdict(list)
        for todo in active:
            by_status[todo.status].append(todo)
        
        by_priority = defaultdict(list)
        for todo in by_status['backlog']:
            by_priority[todo.priority].append(todo)
        
        output_path = self.root_dir / 'docs' / 'TODO_MASTER_CONSOLIDATED.md'
        
        with open(output_path, 'w') as f:
            f.write("# TODO Master List - Consolidated\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Total Active Items:** {len(active)}\n")
            f.write(f"**Archived:** {self.stats['done']} completed, {self.stats['obsolete']} obsolete\n\n")
            f.write("---\n\n")
            
            # Summary table
            f.write("## Summary\n\n")
            f.write("| Status | Count |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Backlog | {len(by_status['backlog'])} |\n")
            f.write(f"| Future/Parked | {len(by_status['future'])} |\n")
            f.write(f"| Code TODOs | {len(by_status['code-todo'])} |\n")
            f.write(f"| **Total Active** | **{len(active)}** |\n\n")
            
            f.write("---\n\n")
            
            # Active Backlog by Priority
            f.write("## Active Backlog\n\n")
            for priority in ['Critical', 'High', 'Medium', 'Low']:
                todos = by_priority[priority]
                if not todos:
                    continue
                
                f.write(f"### {priority} Priority ({len(todos)} items)\n\n")
                for todo in todos:
                    f.write(f"- [ ] **[{todo.id}]** [{todo.hw_dependency}] {todo.title}\n")
                    f.write(f"  - **Component:** {todo.component}\n")
                    f.write(f"  - **Source:** `{todo.source_file}:{todo.line_num}`\n\n")
            
            # Future/Parked
            if by_status['future']:
                f.write("---\n\n## Future / Parked Items\n\n")
                for todo in by_status['future']:
                    f.write(f"- [ ] **[{todo.id}]** {todo.title}\n")
                    f.write(f"  - **Component:** {todo.component}\n")
                    f.write(f"  - **Source:** `{todo.source_file}:{todo.line_num}`\n\n")
            
            # Code TODOs
            if by_status['code-todo']:
                f.write("---\n\n## Code TODOs\n\n")
                by_component = defaultdict(list)
                for todo in by_status['code-todo']:
                    by_component[todo.component].append(todo)
                
                for component in sorted(by_component.keys()):
                    f.write(f"### {component.title()}\n\n")
                    for todo in by_component[component]:
                        f.write(f"- [ ] **[{todo.id}]** {todo.title}\n")
                        f.write(f"  - **Source:** `{todo.source_file}:{todo.line_num}`\n")
                        f.write(f"  - **Details:** `{todo.raw_text}`\n\n")
        
        print(f"   ✅ Generated: {output_path}")
        print(f"   📊 Active items: {len(active)}")
    
    def generate_report(self):
        """Generate summary report."""
        print("\n" + "=" * 80)
        print("CONSOLIDATION COMPLETE")
        print("=" * 80)
        
        by_status = defaultdict(int)
        for todo in self.todos:
            by_status[todo.status] += 1
        
        print(f"\n📊 TODO Items by Status:")
        print(f"   ✅ Done:         {by_status['done']}")
        print(f"   ❌ Obsolete:     {by_status['obsolete']}")
        print(f"   🔧 Backlog:      {by_status['backlog']}")
        print(f"   📋 Future:       {by_status['future']}")
        print(f"   💻 Code TODOs:   {by_status['code-todo']}")
        print(f"   📦 Total:        {len(self.todos)}")
        
        print(f"\n📂 Files Generated:")
        print(f"   - docs/archive/2025-10-15/todos_completed.md")
        print(f"   - docs/archive/2025-10-15/todos_obsolete.md")
        print(f"   - docs/TODO_MASTER_CONSOLIDATED.md")
        
        # Save JSON export
        json_path = self.root_dir / 'docs' / 'archive' / '2025-10-15' / 'todos_all.json'
        with open(json_path, 'w') as f:
            json.dump([t.to_dict() for t in self.todos], f, indent=2)
        print(f"   - docs/archive/2025-10-15/todos_all.json")


def main():
    root_dir = Path(__file__).resolve().parents[2]
    
    print("=" * 80)
    print("TODO CONSOLIDATION - Phase 2")
    print("=" * 80)
    print(f"Root: {root_dir}\n")
    
    consolidator = TodoConsolidator(root_dir)
    
    # Extract from all sources
    consolidator.extract_from_code()
    consolidator.extract_from_docs()
    
    # Process
    consolidator.deduplicate()
    
    # Generate outputs
    consolidator.generate_archives()
    consolidator.generate_consolidated_todo_master()
    consolidator.generate_report()


if __name__ == '__main__':
    main()
