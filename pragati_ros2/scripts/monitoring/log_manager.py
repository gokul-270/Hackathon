#!/usr/bin/env python3
"""
Automatic Log Management System for Pragati ROS2 Project
========================================================

This module provides comprehensive log management including:
- Automatic cleanup of old log files
- Log rotation and archiving
- Size-based cleanup
- Integration with ROS2 launch files
- Standalone utilities for system administration

Author: Generated for Pragati ROS2 Project
Date: 2025-09-18
"""

import os
import shutil
import logging
import glob
import gzip
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import subprocess
import json


class LogManager:
    """Comprehensive log management for Pragati ROS2 project."""
    
    def __init__(self, 
                 project_root: str = None,
                 max_log_age_days: int = 7,
                 max_log_size_mb: int = 100,
                 compress_old_logs: bool = True,
                 verbose: bool = False):
        """
        Initialize log manager.
        
        Args:
            project_root: Root directory of the project
            max_log_age_days: Maximum age of log files before cleanup
            max_log_size_mb: Maximum total size of logs in MB
            compress_old_logs: Whether to compress old logs before deletion
            verbose: Enable verbose logging
        """
        if project_root:
            self.project_root = Path(project_root).resolve()
            if not self.project_root.exists():
                raise ValueError(f"Project root directory does not exist: {project_root}")
        else:
            self.project_root = Path(__file__).parent.parent.parent
        self.max_log_age_days = max_log_age_days
        self.max_log_size_mb = max_log_size_mb
        self.compress_old_logs = compress_old_logs
        self.verbose = verbose
        
        # Define log directories within the project
        self.log_directories = [
            self.project_root / "logs",
            self.project_root / "logs" / "runtime",
            self.project_root / "logs" / "tests",
            self.project_root / "logs" / "validation",
            self.project_root / "logs" / "archived",
            self.project_root / "build" / "log",
            self.project_root / "install" / "log",
        ]
        
        # ROS2 log directory (if set to project)
        self.ros_log_dir = os.environ.get('ROS_LOG_DIR')
        if self.ros_log_dir and Path(self.ros_log_dir).is_relative_to(self.project_root):
            self.log_directories.append(Path(self.ros_log_dir))
        
        # Setup logging
        self._setup_logging()
        
        # Create log directories
        self._create_log_directories()
    
    def _setup_logging(self):
        """Setup internal logging for the log manager."""
        log_level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - LogManager - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(self.project_root / "logs" / "log_manager.log", mode='a')
            ] if (self.project_root / "logs").exists() else [logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)
    
    def _create_log_directories(self):
        """Create necessary log directories."""
        for log_dir in self.log_directories:
            log_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Ensured log directory exists: {log_dir}")
    
    def get_log_files(self, directory: Path, extensions: List[str] = None) -> List[Path]:
        """
        Get all log files in a directory.
        
        Args:
            directory: Directory to scan
            extensions: List of file extensions to include (default: common log extensions)
        
        Returns:
            List of log file paths
        """
        if not directory.exists():
            return []
        
        if extensions is None:
            extensions = ['.log', '.txt', '.out', '.err', '.stdout', '.stderr']
        
        log_files = []
        for ext in extensions:
            log_files.extend(directory.glob(f"**/*{ext}"))
            log_files.extend(directory.glob(f"**/*{ext}.gz"))
        
        return list(set(log_files))  # Remove duplicates
    
    def get_file_age(self, file_path: Path) -> float:
        """
        Get age of file in days.
        
        Args:
            file_path: Path to the file
        
        Returns:
            Age in days
        """
        if not file_path.exists():
            return 0
        
        mtime = file_path.stat().st_mtime
        age_seconds = time.time() - mtime
        return age_seconds / (24 * 3600)  # Convert to days
    
    def get_directory_size(self, directory: Path) -> float:
        """
        Get total size of directory in MB.
        
        Args:
            directory: Directory to measure
        
        Returns:
            Size in MB
        """
        if not directory.exists():
            return 0
        
        total_size = 0
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        
        return total_size / (1024 * 1024)  # Convert to MB
    
    def compress_file(self, file_path: Path) -> Optional[Path]:
        """
        Compress a file using gzip.
        
        Args:
            file_path: Path to file to compress
        
        Returns:
            Path to compressed file or None if failed
        """
        if not file_path.exists() or file_path.suffix == '.gz':
            return None
        
        compressed_path = file_path.with_suffix(file_path.suffix + '.gz')
        
        try:
            with open(file_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Remove original file
            file_path.unlink()
            self.logger.info(f"Compressed and removed: {file_path}")
            return compressed_path
            
        except Exception as e:
            self.logger.error(f"Failed to compress {file_path}: {e}")
            # Clean up partial compressed file
            if compressed_path.exists():
                compressed_path.unlink()
            return None
    
    def cleanup_old_files(self, directory: Path, max_age_days: int = None) -> Dict[str, Any]:
        """
        Clean up old files in a directory.
        
        Args:
            directory: Directory to clean
            max_age_days: Maximum age in days (uses instance default if None)
        
        Returns:
            Dictionary with cleanup statistics
        """
        if max_age_days is None:
            max_age_days = self.max_log_age_days
        
        stats = {
            'files_found': 0,
            'files_compressed': 0,
            'files_removed': 0,
            'space_freed_mb': 0,
            'errors': []
        }
        
        if not directory.exists():
            return stats
        
        log_files = self.get_log_files(directory)
        stats['files_found'] = len(log_files)
        
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        
        for file_path in log_files:
            try:
                file_age = self.get_file_age(file_path)
                file_size = file_path.stat().st_size / (1024 * 1024)  # MB
                
                if file_age > max_age_days:
                    # Check if it's a currently active log (modified in last 5 minutes)
                    if file_age < (5 / (24 * 60)):  # 5 minutes in days
                        self.logger.debug(f"Skipping active log file: {file_path}")
                        continue
                    
                    if self.compress_old_logs and file_path.suffix != '.gz':
                        # Try to compress first
                        compressed = self.compress_file(file_path)
                        if compressed:
                            stats['files_compressed'] += 1
                            # Check if compressed file is still too old
                            if file_age > max_age_days * 2:  # Keep compressed files longer
                                compressed.unlink()
                                stats['files_removed'] += 1
                                stats['space_freed_mb'] += file_size
                        else:
                            # Compression failed, remove original
                            file_path.unlink()
                            stats['files_removed'] += 1
                            stats['space_freed_mb'] += file_size
                    else:
                        # Direct removal
                        file_path.unlink()
                        stats['files_removed'] += 1
                        stats['space_freed_mb'] += file_size
                    
                    self.logger.info(f"Cleaned up old log: {file_path} (age: {file_age:.1f} days)")
            
            except Exception as e:
                error_msg = f"Error processing {file_path}: {e}"
                stats['errors'].append(error_msg)
                self.logger.error(error_msg)
        
        return stats
    
    def cleanup_by_size(self, directory: Path, max_size_mb: int = None) -> Dict[str, Any]:
        """
        Clean up files when directory size exceeds limit.
        
        Args:
            directory: Directory to clean
            max_size_mb: Maximum size in MB (uses instance default if None)
        
        Returns:
            Dictionary with cleanup statistics
        """
        if max_size_mb is None:
            max_size_mb = self.max_log_size_mb
        
        stats = {
            'initial_size_mb': 0,
            'final_size_mb': 0,
            'files_removed': 0,
            'space_freed_mb': 0
        }
        
        if not directory.exists():
            return stats
        
        current_size = self.get_directory_size(directory)
        stats['initial_size_mb'] = current_size
        
        if current_size <= max_size_mb:
            stats['final_size_mb'] = current_size
            return stats
        
        # Get files sorted by age (oldest first)
        log_files = self.get_log_files(directory)
        log_files.sort(key=lambda f: f.stat().st_mtime)
        
        target_size = max_size_mb * 0.8  # Clean to 80% of max size
        
        for file_path in log_files:
            if current_size <= target_size:
                break
            
            try:
                file_size = file_path.stat().st_size / (1024 * 1024)  # MB
                
                # Don't remove very recent files (less than 1 hour old)
                if self.get_file_age(file_path) < (1 / 24):
                    continue
                
                file_path.unlink()
                current_size -= file_size
                stats['files_removed'] += 1
                stats['space_freed_mb'] += file_size
                
                self.logger.info(f"Removed for size cleanup: {file_path} ({file_size:.1f} MB)")
            
            except Exception as e:
                self.logger.error(f"Error removing {file_path}: {e}")
        
        stats['final_size_mb'] = current_size
        return stats
    
    def cleanup_ros2_logs(self) -> Dict[str, Any]:
        """
        Clean up external ROS2 logs in ~/.ros/log/
        
        Returns:
            Dictionary with cleanup statistics
        """
        stats = {
            'external_ros_logs_found': 0,
            'directories_removed': 0,
            'space_freed_mb': 0,
            'errors': []
        }
        
        ros_log_path = Path.home() / ".ros" / "log"
        
        if not ros_log_path.exists():
            return stats
        
        # Get all timestamped log directories
        log_dirs = [d for d in ros_log_path.iterdir() if d.is_dir() and not d.name == 'latest']
        stats['external_ros_logs_found'] = len(log_dirs)
        
        cutoff_date = datetime.now() - timedelta(days=self.max_log_age_days)
        
        for log_dir in log_dirs:
            try:
                dir_age = self.get_file_age(log_dir)
                
                if dir_age > self.max_log_age_days:
                    dir_size = self.get_directory_size(log_dir)
                    shutil.rmtree(log_dir)
                    stats['directories_removed'] += 1
                    stats['space_freed_mb'] += dir_size
                    
                    self.logger.info(f"Removed old ROS2 log directory: {log_dir} ({dir_size:.1f} MB)")
            
            except Exception as e:
                error_msg = f"Error removing ROS2 log directory {log_dir}: {e}"
                stats['errors'].append(error_msg)
                self.logger.error(error_msg)
        
        return stats
    
    def run_full_cleanup(self) -> Dict[str, Any]:
        """
        Run complete log cleanup across all directories.
        
        Returns:
            Combined statistics from all cleanup operations
        """
        self.logger.info("Starting full log cleanup...")
        
        total_stats = {
            'start_time': datetime.now().isoformat(),
            'directories_processed': 0,
            'total_files_found': 0,
            'total_files_compressed': 0,
            'total_files_removed': 0,
            'total_space_freed_mb': 0,
            'external_ros_cleanup': {},
            'directory_stats': {},
            'errors': []
        }
        
        # Clean up project log directories
        for log_dir in self.log_directories:
            if not log_dir.exists():
                continue
                
            self.logger.info(f"Processing directory: {log_dir}")
            
            # Age-based cleanup
            age_stats = self.cleanup_old_files(log_dir)
            
            # Size-based cleanup
            size_stats = self.cleanup_by_size(log_dir)
            
            # Combine stats
            dir_stats = {
                'age_cleanup': age_stats,
                'size_cleanup': size_stats,
                'final_size_mb': self.get_directory_size(log_dir)
            }
            
            total_stats['directory_stats'][str(log_dir)] = dir_stats
            total_stats['directories_processed'] += 1
            total_stats['total_files_found'] += age_stats['files_found']
            total_stats['total_files_compressed'] += age_stats['files_compressed']
            total_stats['total_files_removed'] += age_stats['files_removed'] + size_stats['files_removed']
            total_stats['total_space_freed_mb'] += age_stats['space_freed_mb'] + size_stats['space_freed_mb']
            total_stats['errors'].extend(age_stats.get('errors', []))
        
        # Clean up external ROS2 logs
        ros_stats = self.cleanup_ros2_logs()
        total_stats['external_ros_cleanup'] = ros_stats
        total_stats['total_space_freed_mb'] += ros_stats['space_freed_mb']
        total_stats['errors'].extend(ros_stats.get('errors', []))
        
        total_stats['end_time'] = datetime.now().isoformat()
        
        # Log summary
        self.logger.info(f"Log cleanup completed:")
        self.logger.info(f"  - Directories processed: {total_stats['directories_processed']}")
        self.logger.info(f"  - Files found: {total_stats['total_files_found']}")
        self.logger.info(f"  - Files compressed: {total_stats['total_files_compressed']}")
        self.logger.info(f"  - Files removed: {total_stats['total_files_removed']}")
        self.logger.info(f"  - Space freed: {total_stats['total_space_freed_mb']:.2f} MB")
        self.logger.info(f"  - Errors: {len(total_stats['errors'])}")
        
        # Save cleanup report
        self._save_cleanup_report(total_stats)
        
        return total_stats
    
    def _save_cleanup_report(self, stats: Dict[str, Any]):
        """Save cleanup report to file."""
        report_file = self.project_root / "logs" / "cleanup_reports" / f"cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(report_file, 'w') as f:
                json.dump(stats, f, indent=2, default=str)
            self.logger.info(f"Cleanup report saved to: {report_file}")
        except Exception as e:
            self.logger.error(f"Failed to save cleanup report: {e}")


def main():
    """CLI interface for log manager."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Pragati ROS2 Log Manager")
    parser.add_argument("--project-root", type=str, help="Project root directory")
    parser.add_argument("--max-age-days", type=int, default=7, help="Maximum age of logs in days")
    parser.add_argument("--max-size-mb", type=int, default=100, help="Maximum log directory size in MB")
    parser.add_argument("--no-compress", action="store_true", help="Don't compress old logs")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    
    args = parser.parse_args()
    
    try:
        log_manager = LogManager(
            project_root=args.project_root,
            max_log_age_days=args.max_age_days,
            max_log_size_mb=args.max_size_mb,
            compress_old_logs=not args.no_compress,
            verbose=args.verbose
        )
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    
    if args.dry_run:
        print("DRY RUN MODE - No files will be modified")
    
    if not args.dry_run:
        stats = log_manager.run_full_cleanup()
        print(f"\nCleanup completed - freed {stats['total_space_freed_mb']:.2f} MB")
    else:
        # Dry run - just show what would be cleaned
        for log_dir in log_manager.log_directories:
            if log_dir.exists():
                size = log_manager.get_directory_size(log_dir)
                files = log_manager.get_log_files(log_dir)
                old_files = [f for f in files if log_manager.get_file_age(f) > args.max_age_days]
                print(f"{log_dir}: {size:.1f} MB, {len(files)} files, {len(old_files)} old files")


if __name__ == "__main__":
    main()