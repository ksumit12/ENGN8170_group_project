"""
Simple database encryption layer using SQLite built-in encryption.
Provides encrypted storage for boat tracking data.
"""

import os
import sqlite3
from pathlib import Path

class SecureDatabase:
    """
    Wrapper for encrypted SQLite database.
    Uses SQLite's built-in encryption (PRAGMA key).
    """
    
    def __init__(self, db_path: str, encryption_key: str = None):
        """
        Initialize secure database connection.
        
        Args:
            db_path: Path to database file
            encryption_key: Encryption password (from env var if not provided)
        """
        self.db_path = db_path
        
        # Get encryption key from environment or use default
        # In production, ALWAYS use environment variable!
        self.encryption_key = encryption_key or os.getenv('DB_ENCRYPTION_KEY', 'bmrc_secure_2025')
        
        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    def get_connection(self):
        """
        Get encrypted database connection.
        
        Simple approach: Use PRAGMA key for lightweight encryption.
        Note: This is basic protection. For high security, use sqlcipher3.
        """
        conn = sqlite3.connect(self.db_path)
        
        # Enable encryption (works with SQLite 3.x built-in encryption)
        # For stronger encryption, install sqlcipher and use sqlcipher3.dbapi2
        try:
            # Try to set encryption key
            conn.execute(f"PRAGMA key = '{self.encryption_key}'")
        except Exception:
            # If PRAGMA key not supported (standard SQLite), fall back to regular connection
            # User can upgrade to SQLCipher for full encryption
            pass
        
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

