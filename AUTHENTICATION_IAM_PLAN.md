# Authentication & IAM Implementation Plan

## Project: PFM Web & Android App Authentication System

**Date Created:** December 9, 2025  
**Status:** Planning Phase

---

## Overview

Add comprehensive authentication and Identity Access Management (IAM) to both the PFM Web application and Android app, replacing the current device-based user system with proper user accounts.

---

## Current State

### Web Application
- No authentication - all pages publicly accessible
- Users created automatically as `{device_id}@device`
- No login/logout functionality
- No session management
- Data filtering by user_id parameter only

### Android App
- Device-based identification using `UserService`
- Device ID format: `device_{timestamp}_{random}`
- Stored in SharedPreferences
- No user login
- Syncs data using device ID as user identifier

---

## Goals

1. **Web Application**
   - User registration and login system
   - Session management with Flask-Login
   - Password hashing with bcrypt
   - Show only authenticated user's data
   - Admin role for viewing all data

2. **Android App**
   - Login screen with email/password
   - Token-based authentication (JWT)
   - Sync data only when logged in
   - Associate receipts with logged-in user
   - Secure token storage

3. **IAM Features**
   - Role-based access control (RBAC)
   - Roles: Owner, Family Member, Admin
   - Permission system for data access
   - Multi-user family accounts

---

## Architecture Design

### Authentication Flow

#### Web Application Flow (Google OAuth + Traditional)
```
Option 1: Google Sign-In
1. User clicks "Sign in with Google"
2. Redirects to Google OAuth consent screen
3. User approves access
4. Google redirects back with authorization code
5. Server exchanges code for access token
6. Server retrieves user info from Google
7. Creates/updates user in database
8. Creates session with Flask-Login
9. User accesses protected pages

Option 2: Email/Password (Fallback)
1. User visits login page
2. Enters email + password
3. Server validates credentials
4. Creates session with Flask-Login
5. User accesses protected pages
6. Session cookie maintains auth state
```

#### Android App Flow (Google Sign-In + Traditional)
```
Option 1: Google Sign-In (Recommended)
1. User opens app
2. If no token → Show login screen with "Sign in with Google" button
3. User taps "Sign in with Google"
4. Google Sign-In SDK handles authentication
5. App receives Google ID token
6. App sends ID token to /api/v1/auth/google
7. Server verifies token with Google
8. Server creates/retrieves user
9. Server returns JWT token
10. App stores token securely (EncryptedSharedPreferences)
11. App includes token in all API requests

Option 2: Email/Password (Fallback)
1. User enters email + password
2. App sends credentials to /api/v1/auth/login
3. Server returns JWT token
4. App stores token securely
5. App includes token in all API requests
```

### Database Schema Changes

#### Users Table (Enhanced)
```sql
ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE users ADD COLUMN last_login DATETIME;
ALTER TABLE users ADD COLUMN password_reset_token VARCHAR(255);
ALTER TABLE users ADD COLUMN password_reset_expires DATETIME;
```

#### New: Sessions Table
```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token VARCHAR(255) UNIQUE NOT NULL,
    device_info TEXT,
    ip_address VARCHAR(45),
    auth_provider VARCHAR(20) DEFAULT 'local',  -- 'local', 'google'
    expires_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

#### New: Permissions Table
```sql
CREATE TABLE permissions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    resource_type VARCHAR(50) NOT NULL,  -- 'receipts', 'amazon_orders', 'analytics'
    can_read BOOLEAN DEFAULT TRUE,
    can_write BOOLEAN DEFAULT TRUE,
    can_delete BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

---

## Implementation Steps

### Phase 1: Web Authentication with Google OAuth (Priority: HIGH)

**Step 1.1: Install Dependencies**
```bash
pip install Flask-Login flask-bcrypt PyJWT authlib requests
```

**Step 1.1b: Set Up Google OAuth Credentials**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project or select existing
3. Enable Google+ API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URIs:
   - `http://localhost:5000/auth/google/callback`
   - `http://10.0.0.19:5000/auth/google/callback`
   - Production URL when deployed
6. Save Client ID and Client Secret

**Step 1.2: Create Authentication Blueprint**
- `/pfm_web/auth/views.py` - Login, logout, register, Google OAuth routes
- `/pfm_web/auth/forms.py` - WTForms for validation (email/password fallback)
- `/pfm_web/auth/google.py` - Google OAuth helper functions
- `/pfm_web/auth/templates/` - Login/register pages with Google button

**Step 1.3: Update User Model**
```python
from flask_login import UserMixin
from flask_bcrypt import generate_password_hash, check_password_hash

class User(db.Model, UserMixin):
    # Add new columns:
    google_id: Mapped[Optional[str]] = mapped_column(db.String(255), unique=True)
    profile_picture: Mapped[Optional[str]] = mapped_column(db.String(500))
    auth_provider: Mapped[str] = mapped_column(db.String(20), default="local")  # 'local' or 'google'
    
    # Add methods:
    def set_password(self, password)
    def check_password(self, password)
    def get_id(self)
    
    @staticmethod
    def get_or_create_google_user(google_id, email, name, picture):
        """Get or create user from Google OAuth data"""
        user = User.query.filter_by(google_id=google_id).first()
        if not user:
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(
                    email=email,
                    google_id=google_id,
                    profile_picture=picture,
                    auth_provider='google',
                    password_hash=generate_password_hash('').decode('utf-8'),  # No password for Google users
                    role='owner'
                )
                db.session.add(user)
            else:
                # Link existing email account to Google
                user.google_id = google_id
                user.profile_picture = picture
                user.auth_provider = 'google'
            db.session.commit()
        return user
```

**Step 1.4: Configure Flask-Login**
```python
# In __init__.py or app.py
from flask_login import LoginManager

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
```

**Step 1.5: Protect Routes**
```python
from flask_login import login_required, current_user

@web_bp.get("/receipts")
@login_required
def receipts_list():
    # Only show current_user's receipts
    receipts = Receipt.query.filter_by(user_id=current_user.id).all()
```

**Step 1.6: Create Login/Register Pages**
- **Prominent "Sign in with Google" button** (primary option)
- Divider: "Or sign in with email"
- Login form with email/password (fallback)
- Registration form with email/password/confirm (fallback)
- Password reset functionality (for email/password users only)
- "Remember Me" checkbox

**Example Login Page HTML:**
```html
<div class="login-container">
  <h2>Sign In</h2>
  
  <!-- Google Sign-In (Primary) -->
  <a href="{{ url_for('auth.google_login') }}" class="btn-google">
    <img src="/static/img/google-icon.svg" alt="Google">
    Sign in with Google
  </a>
  
  <div class="divider">
    <span>or</span>
  </div>
  
  <!-- Email/Password (Fallback) -->
  <form method="POST">
    <input type="email" name="email" placeholder="Email" required>
    <input type="password" name="password" placeholder="Password" required>
    <button type="submit">Sign In</button>
  </form>
  
  <p>Don't have an account? <a href="{{ url_for('auth.register') }}">Register</a></p>
</div>
```

### Phase 2: API Token Authentication (Priority: HIGH)

**Step 2.1: Create JWT Token System**
```python
import jwt
from datetime import datetime, timedelta

def generate_token(user_id, expires_in=86400):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

def verify_token(token):
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload['user_id']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
```

**Step 2.2: Create Auth API Endpoints**
```
POST /api/v1/auth/register        # Email/password registration
POST /api/v1/auth/login           # Email/password login
POST /api/v1/auth/google          # Google ID token verification
POST /api/v1/auth/refresh         # Refresh JWT token
POST /api/v1/auth/logout          # Invalidate token
GET  /api/v1/auth/me              # Get current user info
```

**Google Token Verification Endpoint:**
```python
@auth_api.route('/google', methods=['POST'])
def google_auth():
    """Verify Google ID token and return JWT"""
    data = request.get_json()
    id_token = data.get('id_token')
    
    if not id_token:
        return {'error': 'ID token required'}, 400
    
    try:
        # Verify token with Google
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests
        
        idinfo = google_id_token.verify_oauth2_token(
            id_token, 
            requests.Request(), 
            app.config['GOOGLE_CLIENT_ID']
        )
        
        # Get user info
        google_user_id = idinfo['sub']
        email = idinfo['email']
        name = idinfo.get('name', '')
        picture = idinfo.get('picture', '')
        
        # Get or create user
        user = User.get_or_create_google_user(google_user_id, email, name, picture)
        
        # Generate JWT token
        token = generate_token(user.id)
        
        return {
            'token': token,
            'user': {
                'id': user.id,
                'email': user.email,
                'name': name,
                'picture': picture
            }
        }, 200
        
    except ValueError as e:
        return {'error': 'Invalid ID token'}, 401
    except Exception as e:
        return {'error': str(e)}, 500
```

**Step 2.3: Create Token Verification Decorator**
```python
from functools import wraps

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return {'error': 'Token missing'}, 401
        
        try:
            token = token.replace('Bearer ', '')
            user_id = verify_token(token)
            if not user_id:
                return {'error': 'Invalid token'}, 401
            
            request.current_user_id = user_id
        except:
            return {'error': 'Token invalid'}, 401
        
        return f(*args, **kwargs)
    return decorated
```

**Step 2.4: Update Receipt API**
```python
@api.route('/receipts', methods=['GET'])
@token_required
def get_receipts():
    user_id = request.current_user_id
    receipts = Receipt.query.filter_by(user_id=user_id).all()
    return jsonify([r.to_dict() for r in receipts])
```

### Phase 3: Android App Authentication with Google Sign-In (Priority: HIGH)

**Step 3.0: Add Dependencies**
```yaml
# pubspec.yaml
dependencies:
  google_sign_in: ^6.1.5
  flutter_secure_storage: ^9.0.0
  http: ^1.1.0
  provider: ^6.1.1
```

**Step 3.1: Create Auth Service**
```dart
// lib/core/services/auth_service.dart
import 'package:google_sign_in/google_sign_in.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthService {
  final GoogleSignIn _googleSignIn = GoogleSignIn(
    scopes: ['email', 'profile'],
  );
  final FlutterSecureStorage _secureStorage = FlutterSecureStorage();
  
  // Google Sign-In
  Future<AuthResult> signInWithGoogle()
  
  // Email/Password (Fallback)
  Future<AuthResult> login(String email, String password)
  Future<void> register(String email, String password)
  
  // Common
  Future<void> logout()
  Future<String?> getToken()
  Future<bool> isLoggedIn()
  Future<void> refreshToken()
  Future<User?> getCurrentUser()
}
```

**Step 3.1b: Implement Google Sign-In**
```dart
Future<AuthResult> signInWithGoogle() async {
  try {
    // Trigger Google Sign-In flow
    final GoogleSignInAccount? googleUser = await _googleSignIn.signIn();
    
    if (googleUser == null) {
      return AuthResult(success: false, error: 'Sign in cancelled');
    }
    
    // Get authentication details
    final GoogleSignInAuthentication googleAuth = await googleUser.authentication;
    final String? idToken = googleAuth.idToken;
    
    if (idToken == null) {
      return AuthResult(success: false, error: 'Failed to get ID token');
    }
    
    // Send ID token to backend
    final response = await _apiClient.post(
      '/auth/google',
      data: {'id_token': idToken},
    );
    
    if (response.statusCode == 200) {
      final data = response.data;
      final String token = data['token'];
      
      // Store token securely
      await _secureStorage.write(key: 'auth_token', value: token);
      await _secureStorage.write(key: 'user_email', value: googleUser.email);
      await _secureStorage.write(key: 'user_name', value: googleUser.displayName ?? '');
      await _secureStorage.write(key: 'user_photo', value: googleUser.photoUrl ?? '');
      
      return AuthResult(
        success: true,
        user: User.fromJson(data['user']),
      );
    } else {
      return AuthResult(success: false, error: 'Authentication failed');
    }
  } catch (e) {
    return AuthResult(success: false, error: e.toString());
  }
}
```

**Step 3.2: Secure Token Storage**
```kotlin
// Use EncryptedSharedPreferences
implementation "androidx.security:security-crypto:1.1.0-alpha06"

val sharedPreferences = EncryptedSharedPreferences.create(
    "secure_prefs",
    masterKeyAlias,
    context,
    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
)
```

**Step 3.3: Configure Google Sign-In (Android)**
```xml
<!-- android/app/build.gradle -->
dependencies {
    implementation 'com.google.android.gms:play-services-auth:20.7.0'
}
```

Add to `android/app/src/main/AndroidManifest.xml`:
```xml
<meta-data
    android:name="com.google.android.gms.version"
    android:value="@integer/google_play_services_version" />
```

Get your OAuth 2.0 Client ID from Google Cloud Console and configure.

**Step 3.3b: Create Login Screen with Google Sign-In**
```
lib/features/auth/
  ├── login_page.dart          # Google Sign-In + Email/Password UI
  ├── register_page.dart       # Email/Password registration (fallback)
  ├── auth_provider.dart       # State management
  └── widgets/
      ├── google_sign_in_button.dart
      └── email_login_form.dart
```

**Example Login Page:**
```dart
// lib/features/auth/login_page.dart
class LoginPage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Logo
              Icon(Icons.account_balance_wallet, size: 80, color: Colors.purple),
              SizedBox(height: 24),
              Text('Welcome to PFM', style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
              SizedBox(height: 48),
              
              // Google Sign-In Button (Primary)
              GoogleSignInButton(
                onPressed: () async {
                  final authService = context.read<AuthService>();
                  final result = await authService.signInWithGoogle();
                  
                  if (result.success) {
                    Navigator.pushReplacementNamed(context, '/home');
                  } else {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text(result.error ?? 'Sign in failed')),
                    );
                  }
                },
              ),
              
              SizedBox(height: 24),
              
              // Divider
              Row(
                children: [
                  Expanded(child: Divider()),
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: 16),
                    child: Text('or', style: TextStyle(color: Colors.grey)),
                  ),
                  Expanded(child: Divider()),
                ],
              ),
              
              SizedBox(height: 24),
              
              // Email/Password Form (Fallback)
              EmailLoginForm(),
              
              SizedBox(height: 16),
              
              TextButton(
                onPressed: () => Navigator.pushNamed(context, '/register'),
                child: Text('Don\'t have an account? Register'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
```

**Step 3.4: Update API Client**
```dart
class PfmApiClient {
  Future<void> _addAuthHeader(RequestOptions options) async {
    final token = await _authService.getToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
  }
}
```

**Step 3.5: Update Data Sync**
```dart
Future<void> syncReceipts() async {
  if (!await _authService.isLoggedIn()) {
    throw Exception('User not logged in');
  }
  
  final userId = await _authService.getCurrentUserId();
  // Sync with authenticated user
}
```

### Phase 4: Role-Based Access Control (Priority: MEDIUM)

**Step 4.1: Define Roles**
```python
class Role(Enum):
    OWNER = "owner"          # Full access to own data
    FAMILY = "family"        # Read access to shared data
    ADMIN = "admin"          # Access to all data
```

**Step 4.2: Permission Decorator**
```python
def require_permission(resource, action):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.has_permission(resource, action):
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator

@web_bp.delete("/receipts/<int:receipt_id>")
@login_required
@require_permission('receipts', 'delete')
def receipt_delete(receipt_id):
    pass
```

**Step 4.3: Admin Dashboard**
- View all users
- View all receipts (with user filter)
- Manage user permissions
- System statistics

### Phase 5: Migration Strategy (Priority: HIGH)

**Step 5.1: Migrate Existing Device Users**
```python
# Migration script
def migrate_device_users():
    device_users = User.query.filter(User.email.like('%@device')).all()
    
    for user in device_users:
        # Option 1: Convert to real accounts
        # Send email with registration link
        
        # Option 2: Create placeholder accounts
        # Set temporary password, mark as needs_password_reset
        
        print(f"Migrated {user.email}")
```

**Step 5.2: Handle Existing App Users**
```
1. App update includes login screen
2. On first launch after update:
   - Check if logged in
   - If not, show welcome screen
   - Options:
     a. Create new account
     b. Login to existing account
     c. Continue as guest (read-only, no sync)
```

---

## Security Considerations

### Password Security
- Minimum 8 characters
- Require uppercase, lowercase, number
- Hash with bcrypt (cost factor 12)
- Store only hashed passwords
- Implement password reset via email

### Token Security
- JWT tokens with 24-hour expiry
- Refresh tokens with 30-day expiry
- Store tokens securely (encrypted storage)
- Invalidate on logout
- HTTPS only for production

### Session Security
- Secure session cookies
- HttpOnly and SameSite flags
- CSRF protection with Flask-WTF
- Session timeout after 24 hours
- Force re-auth for sensitive operations

### API Security
- Rate limiting (Flask-Limiter)
- Input validation
- SQL injection prevention (SQLAlchemy)
- XSS protection
- CORS configuration

---

### Configuration

### Environment Variables
```bash
# .env file
SECRET_KEY=<random-256-bit-key>
JWT_SECRET_KEY=<different-random-key>
SECURITY_PASSWORD_SALT=<random-salt>

# Google OAuth Configuration
GOOGLE_CLIENT_ID=<your-client-id>.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=<your-client-secret>
GOOGLE_DISCOVERY_URL=https://accounts.google.com/.well-known/openid-configuration

# Session Configuration
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE='Lax'
```

### Flask Config
```python
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///pfm.db'
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
```

---

## Testing Plan

### Unit Tests
- User model password hashing
- Token generation/verification
- Permission checks
- Session management

### Integration Tests
- Login/logout flow
- Registration flow
- API authentication
- Token refresh

### End-to-End Tests
- Web login → access receipts
- App login → sync receipts
- Logout → clear session
- Multiple users → data isolation

---

## Deployment Checklist

- [ ] Generate strong SECRET_KEY and JWT_SECRET_KEY
- [ ] Enable HTTPS
- [ ] Configure production database
- [ ] Set up email service (password reset)
- [ ] Enable rate limiting
- [ ] Configure CORS properly
- [ ] Set secure cookie flags
- [ ] Add monitoring/logging
- [ ] Create admin user
- [ ] Backup database before migration

---

## Timeline Estimate

**Phase 1 (Web Auth):** 2-3 days  
**Phase 2 (API Auth):** 1-2 days  
**Phase 3 (Android Auth):** 3-4 days  
**Phase 4 (RBAC):** 2-3 days  
**Phase 5 (Migration):** 1-2 days  
**Testing & Refinement:** 2-3 days  

**Total:** 11-17 days

---

## Next Steps

1. Review and approve this plan
2. Set up development environment with new dependencies
3. Create feature branch: `feature/authentication`
4. Start with Phase 1: Web Authentication
5. Implement incrementally with testing at each phase
6. Code review before merging to master

---

## References

- [Flask-Login Documentation](https://flask-login.readthedocs.io/)
- [JWT.io](https://jwt.io/)
- [Flask-Security Documentation](https://pythonhosted.org/Flask-Security/)
- [Android EncryptedSharedPreferences](https://developer.android.com/reference/androidx/security/crypto/EncryptedSharedPreferences)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)

---

## Notes

- **Google Sign-In is the primary authentication method** (better UX, more secure)
- Email/password authentication serves as fallback option
- Consider using Flask-Security-Too for comprehensive security features
- May want to add other OAuth providers later (Facebook, Apple)
- Consider implementing 2FA in future for high-security accounts
- Email verification for email/password accounts recommended
- API versioning strategy needed (currently v1)

## Google OAuth Setup Steps

### For Web Application
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create/select project
3. Enable "Google+ API" or "Google Identity"
4. Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client ID"
5. Application type: "Web application"
6. Authorized redirect URIs:
   - `http://localhost:5000/auth/google/callback`
   - `http://10.0.0.19:5000/auth/google/callback`
   - `https://yourdomain.com/auth/google/callback` (production)
7. Save Client ID and Client Secret

### For Android Application
1. Same project in Google Cloud Console
2. Create another OAuth 2.0 Client ID
3. Application type: "Android"
4. Package name: Your app's package (e.g., `com.yourapp.pfm`)
5. SHA-1 certificate fingerprint:
   ```bash
   keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android -keypass android
   ```
6. Get the Client ID (will be different from web)
7. Configure in `google_sign_in` plugin

### Testing
- Use test users during development
- Add test accounts in OAuth consent screen
- For production, submit app for verification
