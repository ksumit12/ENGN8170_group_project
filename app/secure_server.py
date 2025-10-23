"""
Enhanced HTTPS Server Implementation
Provides secure web server with SSL/TLS encryption and security headers
"""

import os
import ssl
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from werkzeug.serving import WSGIRequestHandler
import threading
import time
from datetime import datetime, timezone

class SecureHTTPServer:
    """Enhanced HTTPS server with security features"""
    
    def __init__(self, app: Flask, cert_path: str = "ssl/cert.pem", key_path: str = "ssl/key.pem"):
        self.app = app
        self.cert_path = cert_path
        self.key_path = key_path
        self.ssl_context = None
        
        # Security configuration
        self.security_headers = {
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            'Referrer-Policy': 'strict-origin-when-cross-origin'
        }
        
        self._setup_security()
        self._setup_ssl_context()
    
    def _setup_security(self):
        """Setup security headers and CORS"""
        # Configure CORS with security restrictions
        CORS(self.app, origins=[
            "https://localhost:5000",
            "https://127.0.0.1:5000",
            # Add your specific domains here
        ], supports_credentials=True)
        
        # Add security headers to all responses
        @self.app.after_request
        def add_security_headers(response):
            for header, value in self.security_headers.items():
                response.headers[header] = value
            return response
        
        # Rate limiting (basic implementation)
        self.request_counts = {}
        self.rate_limit_window = 60  # 1 minute
        self.max_requests_per_minute = 100
        
        @self.app.before_request
        def rate_limit():
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
            current_time = time.time()
            
            # Clean old entries
            self.request_counts = {
                ip: count for ip, count in self.request_counts.items()
                if current_time - count['last_reset'] < self.rate_limit_window
            }
            
            # Check rate limit
            if client_ip in self.request_counts:
                if self.request_counts[client_ip]['count'] >= self.max_requests_per_minute:
                    return jsonify({'error': 'Rate limit exceeded'}), 429
                self.request_counts[client_ip]['count'] += 1
            else:
                self.request_counts[client_ip] = {
                    'count': 1,
                    'last_reset': current_time
                }
    
    def _setup_ssl_context(self):
        """Setup SSL context for HTTPS"""
        if os.path.exists(self.cert_path) and os.path.exists(self.key_path):
            self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.ssl_context.load_cert_chain(self.cert_path, self.key_path)
            
            # Configure SSL settings for security
            self.ssl_context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
            self.ssl_context.options |= ssl.OP_NO_SSLv2
            self.ssl_context.options |= ssl.OP_NO_SSLv3
            self.ssl_context.options |= ssl.OP_NO_TLSv1
            self.ssl_context.options |= ssl.OP_NO_TLSv1_1
            
            print("SSL context configured for HTTPS")
        else:
            print("SSL certificates not found, HTTPS disabled")
            print(f"   Certificate: {self.cert_path}")
            print(f"   Private key: {self.key_path}")
    
    def run(self, host='0.0.0.0', port=5000, debug=False):
        """Run the secure HTTPS server"""
        if self.ssl_context:
            print(f"Starting secure HTTPS server on https://{host}:{port}")
            self.app.run(
                host=host,
                port=port,
                debug=debug,
                ssl_context=self.ssl_context,
                threaded=True
            )
        else:
            print(f"Starting HTTP server on http://{host}:{port} (not secure)")
            self.app.run(
                host=host,
                port=port,
                debug=debug,
                threaded=True
            )

class SecurityMiddleware:
    """Security middleware for additional protection"""
    
    def __init__(self, app):
        self.app = app
    
    def __call__(self, environ, start_response):
        # Add security checks
        if self._is_suspicious_request(environ):
            start_response('403 Forbidden', [('Content-Type', 'text/plain')])
            return [b'Access denied']
        
        return self.app(environ, start_response)
    
    def _is_suspicious_request(self, environ):
        """Check for suspicious request patterns"""
        path = environ.get('PATH_INFO', '')
        user_agent = environ.get('HTTP_USER_AGENT', '')
        
        # Block common attack patterns
        suspicious_patterns = [
            '../', '..\\', 'cmd.exe', 'powershell', 'bash',
            'script>', '<script', 'javascript:', 'data:',
            'eval(', 'exec(', 'system('
        ]
        
        for pattern in suspicious_patterns:
            if pattern in path.lower() or pattern in user_agent.lower():
                return True
        
        return False

def create_secure_app():
    """Create Flask app with security features"""
    app = Flask(__name__)
    
    # Configure Flask for security
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', os.urandom(32).hex())
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
    
    # Add security middleware
    app.wsgi_app = SecurityMiddleware(app.wsgi_app)
    
    return app

def generate_self_signed_cert(hostname='localhost', days=365):
    """Generate self-signed SSL certificate"""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import datetime
    
    # Create private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Create certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "AU"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "ACT"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Canberra"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Black Mountain Rowing Club"),
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
        datetime.datetime.utcnow() + datetime.timedelta(days=days)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(hostname),
            x509.DNSName("localhost"),
            x509.IPAddress("127.0.0.1"),
        ]),
        critical=False,
    ).sign(private_key, hashes.SHA256())
    
    # Save certificate and key
    os.makedirs("ssl", exist_ok=True)
    
    with open("ssl/cert.pem", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    with open("ssl/key.pem", "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    print(f"Self-signed certificate generated for {hostname}")
    print(f"   Certificate: ssl/cert.pem")
    print(f"   Private key: ssl/key.pem")
    print(f"   Valid for: {days} days")

# Security utilities
def validate_input(data, max_length=1000):
    """Validate user input for security"""
    if isinstance(data, str):
        if len(data) > max_length:
            return False
        
        # Check for SQL injection patterns
        dangerous_patterns = [
            "'", '"', ';', '--', '/*', '*/', 'xp_', 'sp_',
            'union', 'select', 'insert', 'update', 'delete',
            'drop', 'create', 'alter', 'exec', 'execute'
        ]
        
        data_lower = data.lower()
        for pattern in dangerous_patterns:
            if pattern in data_lower:
                return False
    
    return True

def sanitize_filename(filename):
    """Sanitize filename for security"""
    import re
    # Remove dangerous characters
    filename = re.sub(r'[^\w\-_\.]', '', filename)
    # Limit length
    filename = filename[:100]
    return filename
