"""
Enhanced Authentication System with JWT Tokens
Implements proper user authentication, authorization, and audit logging
"""

import os
import jwt
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum
import sqlite3
from flask import request, jsonify, g
from functools import wraps

class UserRole(Enum):
    """User roles for role-based access control"""
    ADMIN = "admin"
    MANAGER = "manager"
    VIEWER = "viewer"

@dataclass
class User:
    """User data structure"""
    id: str
    username: str
    role: UserRole
    password_hash: str
    salt: str
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True

class AuthenticationManager:
    """Handles user authentication, JWT tokens, and authorization"""
    
    def __init__(self, db_path: str = "data/boat_tracking.db"):
        self.db_path = db_path
        self.jwt_secret = os.getenv('JWT_SECRET_KEY', self._generate_jwt_secret())
        self.jwt_algorithm = 'HS256'
        self.token_expiry_hours = 24
        
        # Initialize users table
        self._init_users_table()
        
        # Create default admin user if none exists
        self._create_default_admin()
    
    def _generate_jwt_secret(self) -> str:
        """Generate a secure JWT secret key"""
        return secrets.token_urlsafe(32)
    
    def _init_users_table(self):
        """Initialize users table in database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    role TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    last_login TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            
            # Create audit log table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    user_id TEXT,
                    username TEXT,
                    action TEXT NOT NULL,
                    resource TEXT,
                    resource_id TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    success BOOLEAN NOT NULL,
                    details TEXT
                )
            """)
            conn.commit()
    
    def _create_default_admin(self):
        """Create default admin user if none exists"""
        if not self.get_user_by_username('admin'):
            default_password = os.getenv('DEFAULT_ADMIN_PASSWORD', 'Bmrc_2025_Secure')
            self.create_user('admin', default_password, UserRole.ADMIN)
            print(f"Created default admin user. Password: {default_password}")
            print("IMPORTANT: Change the default password after first login!")
    
    def _hash_password(self, password: str, salt: str) -> str:
        """Hash password with salt using PBKDF2"""
        return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
    
    def _generate_salt(self) -> str:
        """Generate a random salt"""
        return secrets.token_hex(16)
    
    def create_user(self, username: str, password: str, role: UserRole) -> User:
        """Create a new user"""
        salt = self._generate_salt()
        password_hash = self._hash_password(password, salt)
        user_id = f"user_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        
        user = User(
            id=user_id,
            username=username,
            role=role,
            password_hash=password_hash,
            salt=salt,
            created_at=datetime.now(timezone.utc)
        )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO users (id, username, role, password_hash, salt, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user.id, user.username, user.role.value, user.password_hash, user.salt, 
                  user.created_at, user.is_active))
            conn.commit()
        
        self._log_audit_event(user.id, user.username, 'USER_CREATED', 'user', user.id, True)
        return user
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password"""
        user = self.get_user_by_username(username)
        if not user or not user.is_active:
            self._log_audit_event(None, username, 'LOGIN_ATTEMPT', 'user', username, False)
            return None
        
        password_hash = self._hash_password(password, user.salt)
        if password_hash != user.password_hash:
            self._log_audit_event(user.id, username, 'LOGIN_ATTEMPT', 'user', username, False)
            return None
        
        # Update last login
        self._update_last_login(user.id)
        self._log_audit_event(user.id, username, 'LOGIN_SUCCESS', 'user', user.id, True)
        return user
    
    def generate_token(self, user: User) -> str:
        """Generate JWT token for user"""
        payload = {
            'user_id': user.id,
            'username': user.username,
            'role': user.role.value,
            'exp': datetime.now(timezone.utc) + timedelta(hours=self.token_expiry_hours),
            'iat': datetime.now(timezone.utc)
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
    
    def verify_token(self, token: str) -> Optional[Dict]:
        """Verify JWT token and return payload"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, username, role, password_hash, salt, created_at, last_login, is_active
                FROM users WHERE username = ? AND is_active = 1
            """, (username,))
            row = cursor.fetchone()
            
            if row:
                return User(
                    id=row[0],
                    username=row[1],
                    role=UserRole(row[2]),
                    password_hash=row[3],
                    salt=row[4],
                    created_at=datetime.fromisoformat(row[5]),
                    last_login=datetime.fromisoformat(row[6]) if row[6] else None,
                    is_active=bool(row[7])
                )
        return None
    
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, username, role, password_hash, salt, created_at, last_login, is_active
                FROM users WHERE id = ? AND is_active = 1
            """, (user_id,))
            row = cursor.fetchone()
            
            if row:
                return User(
                    id=row[0],
                    username=row[1],
                    role=UserRole(row[2]),
                    password_hash=row[3],
                    salt=row[4],
                    created_at=datetime.fromisoformat(row[5]),
                    last_login=datetime.fromisoformat(row[6]) if row[6] else None,
                    is_active=bool(row[7])
                )
        return None
    
    def _update_last_login(self, user_id: str):
        """Update user's last login timestamp"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE users SET last_login = ? WHERE id = ?
            """, (datetime.now(timezone.utc), user_id))
            conn.commit()
    
    def _log_audit_event(self, user_id: Optional[str], username: Optional[str], 
                         action: str, resource: str, resource_id: str, 
                         success: bool, details: str = None):
        """Log audit event"""
        audit_id = f"audit_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO audit_log (id, timestamp, user_id, username, action, resource, 
                                     resource_id, ip_address, user_agent, success, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (audit_id, datetime.now(timezone.utc), user_id, username, action, resource,
                  resource_id, self._get_client_ip(), self._get_user_agent(), success, details))
            conn.commit()
    
    def _get_client_ip(self) -> str:
        """Get client IP address"""
        if request:
            return request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
        return 'unknown'
    
    def _get_user_agent(self) -> str:
        """Get user agent string"""
        if request:
            return request.headers.get('User-Agent', 'unknown')
        return 'unknown'
    
    def get_audit_logs(self, limit: int = 100, user_id: str = None) -> List[Dict]:
        """Get audit logs"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if user_id:
                cursor.execute("""
                    SELECT id, timestamp, user_id, username, action, resource, resource_id,
                           ip_address, user_agent, success, details
                    FROM audit_log WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?
                """, (user_id, limit))
            else:
                cursor.execute("""
                    SELECT id, timestamp, user_id, username, action, resource, resource_id,
                           ip_address, user_agent, success, details
                    FROM audit_log ORDER BY timestamp DESC LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            return [{
                'id': row[0],
                'timestamp': row[1],
                'user_id': row[2],
                'username': row[3],
                'action': row[4],
                'resource': row[5],
                'resource_id': row[6],
                'ip_address': row[7],
                'user_agent': row[8],
                'success': bool(row[9]),
                'details': row[10]
            } for row in rows]

# Global authentication manager instance
auth_manager = None

def init_auth_manager(db_path: str = "data/boat_tracking.db"):
    """Initialize global authentication manager"""
    global auth_manager
    auth_manager = AuthenticationManager(db_path)
    return auth_manager

def get_auth_manager() -> AuthenticationManager:
    """Get global authentication manager"""
    global auth_manager
    if auth_manager is None:
        auth_manager = AuthenticationManager()
    return auth_manager

# Decorator functions for Flask routes
def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'No token provided'}), 401
        
        if token.startswith('Bearer '):
            token = token[7:]
        
        payload = get_auth_manager().verify_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        g.current_user = payload
        return f(*args, **kwargs)
    return decorated_function

def require_role(required_role: UserRole):
    """Decorator to require specific role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(g, 'current_user'):
                return jsonify({'error': 'Authentication required'}), 401
            
            user_role = UserRole(g.current_user['role'])
            if user_role != required_role and user_role != UserRole.ADMIN:
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_admin(f):
    """Decorator to require admin role"""
    return require_role(UserRole.ADMIN)(f)

def require_manager_or_admin(f):
    """Decorator to require manager or admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'current_user'):
            return jsonify({'error': 'Authentication required'}), 401
        
        user_role = UserRole(g.current_user['role'])
        if user_role not in [UserRole.ADMIN, UserRole.MANAGER]:
            return jsonify({'error': 'Insufficient permissions'}), 403
        
        return f(*args, **kwargs)
    return decorated_function
