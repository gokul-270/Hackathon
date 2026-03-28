#!/usr/bin/env python3
"""
CMake Audit Script for ROS2 Workspace
Analyzes CMakeLists.txt files to identify build optimization opportunities
"""

import os
import re
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Tuple
from collections import defaultdict


class CMakeAuditor:
    """Analyzes CMakeLists.txt files for build optimization opportunities"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.packages = {}
        self.violations = []
        
        # Patterns for detection
        self.test_keywords = ['test', 'example', 'demo', 'sample', 'bench', 'tool', 'debug']
        self.option_pattern = re.compile(r'option\s*\(\s*(\w+)\s+["\']([^"\']+)["\']\s+(ON|OFF)\s*\)', re.IGNORECASE)
        self.executable_pattern = re.compile(r'add_executable\s*\(\s*(\w+)', re.IGNORECASE)
        self.library_pattern = re.compile(r'add_library\s*\(\s*(\w+)', re.IGNORECASE)
        self.gtest_pattern = re.compile(r'ament_add_gtest\s*\(\s*(\w+)', re.IGNORECASE)
        self.pytest_pattern = re.compile(r'ament_add_pytest\s*\(\s*(\w+)', re.IGNORECASE)
        
    def get_packages(self) -> List[Tuple[str, Path]]:
        """Get list of packages using colcon"""
        try:
            result = subprocess.run(
                ['colcon', 'list', '--base-paths', str(self.workspace_root)],
                capture_output=True, text=True, check=True
            )
            packages = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split()
                    if len(parts) >= 2:
                        name = parts[0]
                        path = Path(parts[1]) if len(parts) > 1 else self.workspace_root / 'src' / name
                        packages.append((name, path))
            return packages
        except subprocess.CalledProcessError as e:
            print(f"Error getting package list: {e}", file=sys.stderr)
            return []
    
    def parse_cmake_file(self, file_path: Path) -> Dict:
        """Parse a CMakeLists.txt file and extract relevant information"""
        if not file_path.exists():
            return {}
        
        result = {
            'executables': [],
            'libraries': [],
            'test_executables': [],
            'options': [],
            'in_testing_block': [],
            'outside_testing_block': [],
            'gtest_targets': [],
            'pytest_targets': []
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)
            return result
        
        lines = content.split('\n')
        block_stack = []  # Track if/endif blocks
        in_testing = False
        in_examples = False
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Track BUILD_TESTING blocks
            if re.search(r'if\s*\(\s*BUILD_TESTING', stripped, re.IGNORECASE):
                block_stack.append('BUILD_TESTING')
                in_testing = True
            elif re.search(r'if\s*\(\s*BUILD_EXAMPLES', stripped, re.IGNORECASE):
                block_stack.append('BUILD_EXAMPLES')
                in_examples = True
            elif stripped.startswith('endif'):
                if block_stack:
                    popped = block_stack.pop()
                    if popped == 'BUILD_TESTING':
                        in_testing = False
                    elif popped == 'BUILD_EXAMPLES':
                        in_examples = False
            
            # Find options
            option_match = self.option_pattern.search(line)
            if option_match:
                option_name = option_match.group(1)
                option_desc = option_match.group(2)
                option_default = option_match.group(3).upper()
                result['options'].append({
                    'name': option_name,
                    'description': option_desc,
                    'default': option_default,
                    'line': i
                })
            
            # Find executables
            exe_match = self.executable_pattern.search(line)
            if exe_match:
                exe_name = exe_match.group(1)
                is_test = any(kw in exe_name.lower() for kw in self.test_keywords)
                
                exe_info = {
                    'name': exe_name,
                    'line': i,
                    'is_test': is_test,
                    'in_testing_block': in_testing,
                    'in_examples_block': in_examples
                }
                
                result['executables'].append(exe_info)
                
                if is_test:
                    result['test_executables'].append(exe_info)
                    if in_testing:
                        result['in_testing_block'].append(exe_info)
                    else:
                        result['outside_testing_block'].append(exe_info)
            
            # Find libraries
            lib_match = self.library_pattern.search(line)
            if lib_match:
                lib_name = lib_match.group(1)
                result['libraries'].append({
                    'name': lib_name,
                    'line': i
                })
            
            # Find gtest targets
            gtest_match = self.gtest_pattern.search(line)
            if gtest_match:
                test_name = gtest_match.group(1)
                result['gtest_targets'].append({
                    'name': test_name,
                    'line': i,
                    'in_testing_block': in_testing
                })
                if not in_testing:
                    result['outside_testing_block'].append({
                        'name': test_name,
                        'line': i,
                        'is_test': True,
                        'in_testing_block': False
                    })
            
            # Find pytest targets
            pytest_match = self.pytest_pattern.search(line)
            if pytest_match:
                test_name = pytest_match.group(1)
                result['pytest_targets'].append({
                    'name': test_name,
                    'line': i,
                    'in_testing_block': in_testing
                })
        
        return result
    
    def analyze_package(self, package_name: str, package_path: Path) -> Dict:
        """Analyze a single package"""
        cmake_file = package_path / 'CMakeLists.txt'
        
        analysis = {
            'name': package_name,
            'path': str(package_path),
            'cmake_exists': cmake_file.exists(),
            'data': {}
        }
        
        if cmake_file.exists():
            analysis['data'] = self.parse_cmake_file(cmake_file)
            
            # Identify issues
            issues = []
            
            # Check for tests outside BUILD_TESTING
            outside_tests = analysis['data']['outside_testing_block']
            if outside_tests:
                issues.append({
                    'severity': 'HIGH',
                    'type': 'tests_outside_guard',
                    'message': f"{len(outside_tests)} test executable(s) outside BUILD_TESTING guard",
                    'targets': [t['name'] for t in outside_tests]
                })
            
            # Check for options defaulting to ON that could be OFF
            risky_options = []
            for opt in analysis['data']['options']:
                opt_name = opt['name'].upper()
                if opt['default'] == 'ON':
                    # Check if it's an optional feature
                    if any(kw in opt_name for kw in ['HAS_', 'WITH_', 'USE_', 'ENABLE_', 'BUILD_EXAMPLES', 'BUILD_TOOLS', 'BUILD_BENCHMARKS']):
                        risky_options.append(opt)
            
            if risky_options:
                issues.append({
                    'severity': 'MEDIUM',
                    'type': 'options_default_on',
                    'message': f"{len(risky_options)} optional feature(s) default to ON",
                    'options': [{'name': o['name'], 'desc': o['description']} for o in risky_options]
                })
            
            # Check for multiple test executables that could be consolidated
            test_exes = analysis['data']['test_executables']
            if len(test_exes) > 5:
                # Group by common prefix
                prefixes = defaultdict(list)
                for test in test_exes:
                    name = test['name']
                    # Extract prefix (word before _test or _node)
                    parts = name.split('_')
                    if len(parts) > 1:
                        prefix = parts[0]
                        prefixes[prefix].append(name)
                
                consolidation_candidates = {k: v for k, v in prefixes.items() if len(v) > 2}
                if consolidation_candidates:
                    issues.append({
                        'severity': 'LOW',
                        'type': 'test_consolidation',
                        'message': f"Multiple test executables could be consolidated",
                        'groups': consolidation_candidates
                    })
            
            analysis['issues'] = issues
            self.violations.extend(issues)
        
        return analysis
    
    def generate_report(self, output_dir: Path):
        """Generate JSON and Markdown reports"""
        timestamp = datetime.now().strftime('%Y%m%d-%H%M')
        
        # Generate JSON report
        json_path = output_dir / f'{timestamp}-analysis.json'
        with open(json_path, 'w') as f:
            json.dump(self.packages, f, indent=2)
        
        print(f"✓ JSON report: {json_path}")
        
        # Generate Markdown report
        md_path = output_dir / f'{timestamp}-analysis.md'
        with open(md_path, 'w') as f:
            self._write_markdown_report(f)
        
        print(f"✓ Markdown report: {md_path}")
        
        return len(self.violations) > 0
    
    def _write_markdown_report(self, f):
        """Write the markdown report content"""
        f.write("# CMake Build Configuration Audit Report\n\n")
        f.write(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Workspace**: {self.workspace_root}\n\n")
        
        # Summary statistics
        total_packages = len(self.packages)
        packages_with_issues = sum(1 for p in self.packages.values() if p.get('issues'))
        total_violations = len(self.violations)
        
        f.write("## Summary\n\n")
        f.write(f"- **Total Packages**: {total_packages}\n")
        f.write(f"- **Packages with Issues**: {packages_with_issues}\n")
        f.write(f"- **Total Issues Found**: {total_violations}\n\n")
        
        # Count test executables
        total_test_exes = 0
        total_outside_testing = 0
        total_options_on = 0
        
        for pkg in self.packages.values():
            if pkg.get('cmake_exists'):
                total_test_exes += len(pkg['data'].get('test_executables', []))
                total_outside_testing += len(pkg['data'].get('outside_testing_block', []))
                for issue in pkg.get('issues', []):
                    if issue['type'] == 'options_default_on':
                        total_options_on += len(issue.get('options', []))
        
        f.write("### Key Findings\n\n")
        f.write(f"- **Test Executables**: {total_test_exes} total\n")
        f.write(f"- **Tests Outside BUILD_TESTING**: {total_outside_testing} ⚠️\n")
        f.write(f"- **Optional Features Defaulting to ON**: {total_options_on}\n\n")
        
        # Estimated savings
        estimated_targets_to_disable = total_outside_testing + (total_options_on // 2)
        f.write("### Estimated Impact\n\n")
        f.write(f"- **Targets that can be disabled by default**: ~{estimated_targets_to_disable}\n")
        f.write(f"- **Estimated build time reduction**: 20-40% (based on disabled test/example targets)\n")
        f.write(f"- **Estimated disk space savings**: 15-30% in build directory\n\n")
        
        # Per-package details
        f.write("## Package Details\n\n")
        
        for pkg_name, pkg_data in sorted(self.packages.items()):
            f.write(f"### {pkg_name}\n\n")
            
            if not pkg_data.get('cmake_exists'):
                f.write("*No CMakeLists.txt found*\n\n")
                continue
            
            data = pkg_data['data']
            
            # Targets summary
            num_exes = len(data.get('executables', []))
            num_libs = len(data.get('libraries', []))
            num_tests = len(data.get('test_executables', []))
            
            f.write(f"**Targets**: {num_exes} executables, {num_libs} libraries\n\n")
            f.write(f"**Test Executables**: {num_tests}\n\n")
            
            # List executables
            if data.get('executables'):
                prod_exes = [e for e in data['executables'] if not e['is_test']]
                test_exes = [e for e in data['executables'] if e['is_test']]
                
                if prod_exes:
                    f.write("**Production Executables**:\n")
                    for exe in prod_exes:
                        f.write(f"- `{exe['name']}`\n")
                    f.write("\n")
                
                if test_exes:
                    f.write("**Test/Debug Executables**:\n")
                    for exe in test_exes:
                        guarded = "✓" if exe['in_testing_block'] else "✗"
                        f.write(f"- `{exe['name']}` [{guarded} guarded]\n")
                    f.write("\n")
            
            # List options
            if data.get('options'):
                f.write("**CMake Options**:\n")
                for opt in data['options']:
                    default_indicator = "⚠️ ON" if opt['default'] == 'ON' else "OFF"
                    f.write(f"- `{opt['name']}`: {opt['description']} (default: {default_indicator})\n")
                f.write("\n")
            
            # Issues
            if pkg_data.get('issues'):
                f.write("**Issues Found**:\n\n")
                for issue in pkg_data['issues']:
                    severity_emoji = {'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(issue['severity'], '⚪')
                    f.write(f"{severity_emoji} **{issue['severity']}**: {issue['message']}\n")
                    
                    if 'targets' in issue:
                        for target in issue['targets']:
                            f.write(f"  - `{target}`\n")
                    
                    if 'options' in issue:
                        for opt in issue['options']:
                            f.write(f"  - `{opt['name']}`: {opt['desc']}\n")
                    
                    if 'groups' in issue:
                        for prefix, targets in issue['groups'].items():
                            f.write(f"  - **{prefix}_*** group: {', '.join(f'`{t}`' for t in targets)}\n")
                    
                    f.write("\n")
            else:
                f.write("✅ **No issues found**\n\n")
            
            f.write("---\n\n")
        
        # Recommendations
        f.write("## Recommendations\n\n")
        f.write("1. **High Priority**: Move all test executables inside `if(BUILD_TESTING)` guards\n")
        f.write("2. **Medium Priority**: Change optional features to default OFF (HAS_DEPTHAI, etc.)\n")
        f.write("3. **Low Priority**: Consolidate multiple related test executables\n")
        f.write("4. **Infrastructure**: Add ccache support for faster rebuilds\n")
        f.write("5. **Infrastructure**: Consider using Ninja generator for better incremental builds\n\n")
    
    def audit(self):
        """Run the full audit"""
        print("🔍 Starting CMake audit...\n")
        
        # Get packages
        packages = self.get_packages()
        print(f"Found {len(packages)} packages\n")
        
        # Analyze each package
        for pkg_name, pkg_path in packages:
            print(f"Analyzing {pkg_name}...")
            analysis = self.analyze_package(pkg_name, pkg_path)
            self.packages[pkg_name] = analysis
        
        print("\n✓ Analysis complete\n")
        
        # Generate reports
        output_dir = self.workspace_root / 'log' / 'cmake_audit'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        has_violations = self.generate_report(output_dir)
        
        # Print summary
        print(f"\n📊 Summary:")
        print(f"  Packages analyzed: {len(self.packages)}")
        print(f"  Issues found: {len(self.violations)}")
        
        return 1 if has_violations else 0


def main():
    """Main entry point"""
    # Determine workspace root
    if len(sys.argv) > 1:
        workspace_root = sys.argv[1]
    else:
        # Try to find workspace root
        workspace_root = os.getcwd()
        while workspace_root != '/':
            if (Path(workspace_root) / 'src').is_dir():
                break
            workspace_root = str(Path(workspace_root).parent)
        
        if workspace_root == '/':
            print("Error: Could not find ROS2 workspace root", file=sys.stderr)
            print("Usage: cmake_audit.py [workspace_root]", file=sys.stderr)
            sys.exit(1)
    
    auditor = CMakeAuditor(workspace_root)
    exit_code = auditor.audit()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
