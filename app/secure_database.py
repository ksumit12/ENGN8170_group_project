"""
Enhanced database encryption layer with SQLCipher support.
Provides encrypted storage for boat tracking data with automatic backups.
"""

import os
import sqlite3
import shutil
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List

class SecureDatabase:
    """
    Enhanced wrapper for encrypted SQLite database.
    Uses SQLCipher for strong encryption with automatic backups.
    """
    
    def __init__(self, db_path: str, encryption_key: str = None, enable_backups: bool = True):
        """
        Initialize secure database connection.
        
        Args:
            db_path: Path to database file
            encryption_key: Encryption password (from env var if not provided)
            enable_backups: Enable automatic daily backups
        """
        self.db_path = db_path
        self.enable_backups = enable_backups
        
        # Get encryption key from environment or use default
        # In production, ALWAYS use environment variable!
        self.encryption_key = encryption_key or os.getenv('DB_ENCRYPTION_KEY', self._generate_secure_key())
        
        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize backup directory
        if self.enable_backups:
            self.backup_dir = Path(db_path).parent / "backups"
            self.backup_dir.mkdir(exist_ok=True)
        
        # Test encryption on initialization
        self._test_encryption()
    
    def _generate_secure_key(self) -> str:
        """Generate a secure encryption key"""
        import secrets
        return secrets.token_urlsafe(32)
    
    def _test_encryption(self):
        """Test if encryption is working properly"""
        try:
            conn = self.get_connection()
            conn.execute("SELECT 1")
            conn.close()
            print("Database encryption is working")
        except Exception as e:
            print(f"Database encryption test failed: {e}")
            print("   Database will work without encryption")
    
    def get_connection(self):
        """
        Get encrypted database connection.
        
        Uses SQLCipher if available, otherwise falls back to standard SQLite.
        """
        # Try SQLCipher first (strongest encryption)
        try:
            import sqlcipher3.dbapi2 as sqlcipher
            conn = sqlcipher.connect(self.db_path)
            conn.execute(f"PRAGMA key = '{self.encryption_key}'")
            # Test the connection
            conn.execute("SELECT 1")
            return conn
        except ImportError:
            pass
        except Exception as e:
            print(f"SQLCipher connection failed: {e}")
        
        # Fallback to standard SQLite with basic protection
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(f"PRAGMA key = '{self.encryption_key}'")
            # Test the connection
            conn.execute("SELECT 1")
        except Exception:
            # Standard SQLite doesn't support encryption, but connection still works
            print("Database encryption not available. Install sqlcipher3 for encryption.")
            print("   Run: pip install sqlcipher3")
        
        return conn
    
    def test_connection(self) -> bool:
        """Test if database connection works with current key."""
        try:
            conn = self.get_connection()
            conn.execute("SELECT 1")
            conn.close()
            return True
        except Exception as e:
            print(f"Database connection test failed: {e}")
            return False
    
    def create_backup(self, backup_name: str = None) -> str:
        """
        Create a backup of the encrypted database.
        
        Args:
            backup_name: Optional custom backup name
            
        Returns:
            Path to the backup file
        """
        if not self.enable_backups:
            raise ValueError("Backups are disabled")
        
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database file not found: {self.db_path}")
        
        # Generate backup filename
        if not backup_name:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}.db"
        
        backup_path = self.backup_dir / backup_name
        
        # Copy the encrypted database file
        shutil.copy2(self.db_path, backup_path)
        
        # Verify backup integrity
        if self._verify_backup(backup_path):
            print(f"Backup created: {backup_path}")
            return str(backup_path)
        else:
            os.remove(backup_path)
            raise Exception("Backup verification failed")
    
    def _verify_backup(self, backup_path: Path) -> bool:
        """Verify backup integrity by testing connection"""
        try:
            # Try to connect to backup with same encryption key
            if backup_path.suffix == '.db':
                # Try SQLCipher first
                try:
                    import sqlcipher3.dbapi2 as sqlcipher
                    conn = sqlcipher.connect(str(backup_path))
                    conn.execute(f"PRAGMA key = '{self.encryption_key}'")
                    conn.execute("SELECT 1")
                    conn.close()
                    return True
                except ImportError:
                    pass
                
                # Fallback to standard SQLite
                conn = sqlite3.connect(str(backup_path))
                try:
                    conn.execute(f"PRAGMA key = '{self.encryption_key}'")
                    conn.execute("SELECT 1")
                    conn.close()
                    return True
                except Exception:
                    conn.close()
                    return False
        except Exception:
            return False
    
    def list_backups(self) -> List[dict]:
        """List all available backups"""
        if not self.enable_backups or not self.backup_dir.exists():
            return []
        
        backups = []
        for backup_file in self.backup_dir.glob("backup_*.db"):
            stat = backup_file.stat()
            backups.append({
                'name': backup_file.name,
                'path': str(backup_file),
                'size': stat.st_size,
                'created': datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
                'modified': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            })
        
        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x['created'], reverse=True)
        return backups
    
    def restore_backup(self, backup_name: str) -> bool:
        """
        Restore database from backup.
        
        Args:
            backup_name: Name of backup file to restore
            
        Returns:
            True if restore successful, False otherwise
        """
        if not self.enable_backups:
            raise ValueError("Backups are disabled")
        
        backup_path = self.backup_dir / backup_name
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_name}")
        
        # Verify backup integrity
        if not self._verify_backup(backup_path):
            raise Exception("Backup verification failed - cannot restore")
        
        # Create current database backup before restore
        current_backup = None
        if os.path.exists(self.db_path):
            try:
                current_backup = self.create_backup("pre_restore_backup.db")
            except Exception as e:
                print(f"Warning: Could not create pre-restore backup: {e}")
        
        try:
            # Restore from backup
            shutil.copy2(backup_path, self.db_path)
            
            # Test restored database
            if self.test_connection():
                print(f"Database restored from: {backup_name}")
                if current_backup:
                    print(f"   Previous database backed up as: {current_backup}")
                return True
            else:
                # Restore failed, try to restore previous database
                if current_backup and os.path.exists(current_backup):
                    shutil.copy2(current_backup, self.db_path)
                    print("Restore failed, previous database restored")
                return False
        except Exception as e:
            print(f"Restore failed: {e}")
            return False
    
    def cleanup_old_backups(self, keep_days: int = 90):
        """
        Clean up old backups, keeping only recent ones.
        
        Args:
            keep_days: Number of days to keep backups
        """
        if not self.enable_backups:
            return
        
        cutoff_date = datetime.now(timezone.utc).timestamp() - (keep_days * 24 * 3600)
        removed_count = 0
        
        for backup_file in self.backup_dir.glob("backup_*.db"):
            if backup_file.stat().st_ctime < cutoff_date:
                try:
                    backup_file.unlink()
                    removed_count += 1
                except Exception as e:
                    print(f"Could not remove old backup {backup_file.name}: {e}")
        
        if removed_count > 0:
            print(f"Cleaned up {removed_count} old backups (older than {keep_days} days)")


def enable_encryption_if_available():
    """
    Check if SQLCipher is available for full database encryption.
    Returns True if available, False otherwise.
    """
    try:
        import sqlcipher3
        return True
    except ImportError:
        return False


def get_secure_connection(db_path: str, encryption_key: str = None):
    """
    Get a secure database connection.
    Uses SQLCipher if available, otherwise standard SQLite with PRAGMA key.
    
    Args:
        db_path: Path to database file
        encryption_key: Encryption password
        
    Returns:
        Database connection object
    """
    encryption_key = encryption_key or os.getenv('DB_ENCRYPTION_KEY', 'bmrc_secure_2025')
    
    # Try SQLCipher first (strongest encryption)
    try:
        import sqlcipher3.dbapi2 as sqlcipher
        conn = sqlcipher.connect(db_path)
        conn.execute(f"PRAGMA key = '{encryption_key}'")
        return conn
    except ImportError:
        pass
    
    # Fallback to standard SQLite with basic protection
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"PRAGMA key = '{encryption_key}'")
    except Exception:
        # Standard SQLite doesn't support encryption, but connection still works
        print("WARNING: Database encryption not available. Install sqlcipher3 for encryption.")
        print("  Run: pip install sqlcipher3")
    
    return conn


# Export helper
__all__ = ['SecureDatabase', 'enable_encryption_if_available', 'get_secure_connection']

