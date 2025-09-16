#!/usr/bin/env python3
"""
Logging configuration for Boat Tracking System
Provides centralized logging with file output, error handling, and status monitoring
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

class BoatTrackingLogger:
    """Centralized logging system for boat tracking."""
    
    def __init__(self, log_dir: str = "logs", max_log_size: int = 10 * 1024 * 1024, backup_count: int = 5):
        """
        Initialize logging system.
        
        Args:
            log_dir: Directory to store log files
            max_log_size: Maximum size of each log file in bytes (default: 10MB)
            backup_count: Number of backup log files to keep
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Create formatters
        self.detailed_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-15s:%(lineno)-4d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        self.simple_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Setup loggers
        self._setup_main_logger(max_log_size, backup_count)
        self._setup_error_logger(max_log_size, backup_count)
        self._setup_status_logger(max_log_size, backup_count)
        self._setup_audit_logger(max_log_size, backup_count)
        
        # System status tracking
        self.status = {
            'system_started': datetime.now(timezone.utc),
            'last_error': None,
            'error_count': 0,
            'last_scan': None,
            'last_detection': None,
            'scanners_active': 0,
            'api_healthy': True,
            'database_healthy': True
        }
    
    def _setup_main_logger(self, max_log_size: int, backup_count: int):
        """Setup main application logger."""
        self.main_logger = logging.getLogger('boat_tracking')
        self.main_logger.setLevel(logging.INFO)
        
        # File handler for main logs
        main_file = self.log_dir / 'boat_tracking.log'
        file_handler = logging.handlers.RotatingFileHandler(
            main_file, maxBytes=max_log_size, backupCount=backup_count
        )
        file_handler.setFormatter(self.detailed_formatter)
        file_handler.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(self.simple_formatter)
        console_handler.setLevel(logging.INFO)
        
        self.main_logger.addHandler(file_handler)
        self.main_logger.addHandler(console_handler)
    
    def _setup_error_logger(self, max_log_size: int, backup_count: int):
        """Setup error-specific logger."""
        self.error_logger = logging.getLogger('boat_tracking.errors')
        self.error_logger.setLevel(logging.ERROR)
        
        # File handler for errors only
        error_file = self.log_dir / 'errors.log'
        error_handler = logging.handlers.RotatingFileHandler(
            error_file, maxBytes=max_log_size, backupCount=backup_count
        )
        error_handler.setFormatter(self.detailed_formatter)
        error_handler.setLevel(logging.ERROR)
        
        self.error_logger.addHandler(error_handler)
    
    def _setup_status_logger(self, max_log_size: int, backup_count: int):
        """Setup status monitoring logger."""
        self.status_logger = logging.getLogger('boat_tracking.status')
        self.status_logger.setLevel(logging.INFO)
        
        # File handler for status logs
        status_file = self.log_dir / 'status.log'
        status_handler = logging.handlers.RotatingFileHandler(
            status_file, maxBytes=max_log_size, backupCount=backup_count
        )
        status_handler.setFormatter(self.simple_formatter)
        status_handler.setLevel(logging.INFO)
        
        self.status_logger.addHandler(status_handler)
    
    def _setup_audit_logger(self, max_log_size: int, backup_count: int):
        """Setup audit trail logger."""
        self.audit_logger = logging.getLogger('boat_tracking.audit')
        self.audit_logger.setLevel(logging.INFO)
        
        # File handler for audit logs
        audit_file = self.log_dir / 'audit.log'
        audit_handler = logging.handlers.RotatingFileHandler(
            audit_file, maxBytes=max_log_size, backupCount=backup_count
        )
        audit_handler.setFormatter(self.detailed_formatter)
        audit_handler.setLevel(logging.INFO)
        
        self.audit_logger.addHandler(audit_handler)
    
    def info(self, message: str, component: str = "SYSTEM"):
        """Log info message."""
        self.main_logger.info(f"[{component}] {message}")
        self.status_logger.info(f"[{component}] {message}")
    
    def warning(self, message: str, component: str = "SYSTEM"):
        """Log warning message."""
        self.main_logger.warning(f"[{component}] {message}")
        self.status_logger.warning(f"[{component}] {message}")
    
    def error(self, message: str, component: str = "SYSTEM", exception: Optional[Exception] = None):
        """Log error message with optional exception details."""
        error_msg = f"[{component}] {message}"
        if exception:
            error_msg += f" | Exception: {type(exception).__name__}: {str(exception)}"
        
        self.main_logger.error(error_msg)
        self.error_logger.error(error_msg)
        self.status_logger.error(error_msg)
        
        # Update status
        self.status['last_error'] = {
            'timestamp': datetime.now(timezone.utc),
            'message': message,
            'component': component,
            'exception': str(exception) if exception else None
        }
        self.status['error_count'] += 1
    
    def critical(self, message: str, component: str = "SYSTEM", exception: Optional[Exception] = None):
        """Log critical error message."""
        error_msg = f"[{component}] {message}"
        if exception:
            error_msg += f" | Exception: {type(exception).__name__}: {str(exception)}"
        
        self.main_logger.critical(error_msg)
        self.error_logger.critical(error_msg)
        self.status_logger.critical(error_msg)
        
        # Update status
        self.status['last_error'] = {
            'timestamp': datetime.now(timezone.utc),
            'message': message,
            'component': component,
            'exception': str(exception) if exception else None
        }
        self.status['error_count'] += 1
    
    def debug(self, message: str, component: str = "SYSTEM"):
        """Log debug message."""
        self.main_logger.debug(f"[{component}] {message}")
    
    def audit(self, action: str, user: str = "SYSTEM", details: str = ""):
        """Log audit trail entry."""
        audit_msg = f"USER:{user} | ACTION:{action}"
        if details:
            audit_msg += f" | DETAILS:{details}"
        
        self.audit_logger.info(audit_msg)
        self.main_logger.info(f"[AUDIT] {audit_msg}")
    
    def update_status(self, key: str, value):
        """Update system status."""
        self.status[key] = value
        self.status_logger.info(f"STATUS UPDATE | {key}: {value}")
    
    def get_status(self) -> dict:
        """Get current system status."""
        return self.status.copy()
    
    def get_recent_errors(self, count: int = 10) -> list:
        """Get recent error entries from log files."""
        try:
            error_file = self.log_dir / 'errors.log'
            if not error_file.exists():
                return []
            
            with open(error_file, 'r') as f:
                lines = f.readlines()
                return lines[-count:] if lines else []
        except Exception as e:
            self.error(f"Failed to read recent errors: {e}")
            return []
    
    def get_recent_logs(self, count: int = 50) -> list:
        """Get recent log entries from main log file."""
        try:
            main_file = self.log_dir / 'boat_tracking.log'
            if not main_file.exists():
                return []
            
            with open(main_file, 'r') as f:
                lines = f.readlines()
                return lines[-count:] if lines else []
        except Exception as e:
            self.error(f"Failed to read recent logs: {e}")
            return []

# Global logger instance
logger_instance = None

def get_logger() -> BoatTrackingLogger:
    """Get the global logger instance."""
    global logger_instance
    if logger_instance is None:
        logger_instance = BoatTrackingLogger()
    return logger_instance

def setup_logging(log_dir: str = "logs") -> BoatTrackingLogger:
    """Setup and return logger instance."""
    global logger_instance
    logger_instance = BoatTrackingLogger(log_dir)
    return logger_instance
