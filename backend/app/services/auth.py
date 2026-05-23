import base64
import json
import hmac
import hashlib
import time
import os
from typing import List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def hash_password(password: str) -> str:
    """Hash a password using PBKDF2 with SHA-256 and a random salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return f"{salt.hex()}:{key.hex()}"

def verify_password(stored_password: str, provided_password: str) -> bool:
    """Verify a password against its stored PBKDF2 hash."""
    try:
        salt_hex, key_hex = stored_password.split(":")
        salt = bytes.fromhex(salt_hex)
        key = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt, 100000)
        return hmac.compare_digest(key.hex(), key_hex)
    except Exception:
        return False

def create_access_token(data: dict, expires_in: int = 86400) -> str:
    """Create a signed, base64-encoded token containing user metadata."""
    settings = get_settings()
    payload = data.copy()
    payload["exp"] = int(time.time()) + expires_in
    
    payload_json = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('utf-8')
    
    # Calculate HMAC signature using settings.app_secret_key
    signature = hmac.new(
        settings.app_secret_key.encode('utf-8'),
        payload_b64.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return f"{payload_b64}.{signature}"

def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify signature and expiration of an access token."""
    settings = get_settings()
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        
        # Verify HMAC signature
        expected_signature = hmac.new(
            settings.app_secret_key.encode('utf-8'),
            payload_b64.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected_signature, signature):
            return None
            
        # Decode and load payload
        payload_json = base64.urlsafe_b64decode(payload_b64.encode('utf-8')).decode('utf-8')
        payload = json.loads(payload_json)
        
        # Verify expiration time
        if payload.get("exp", 0) < time.time():
            return None
            
        return payload
    except Exception:
        return None

async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    token_param: Optional[str] = None
) -> dict:
    """FastAPI dependency to retrieve the currently logged-in user from the token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    resolved_token = token or token_param
    if not resolved_token:
        raise credentials_exception
        
    payload = decode_access_token(resolved_token)
    if payload is None:
        raise credentials_exception
        
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
        
    # Lazy import to avoid circular dependency
    from app.models.database import get_user_by_username
    user = await get_user_by_username(username)
    if user is None:
        raise credentials_exception
        
    return user

class RoleChecker:
    """Dependency checker to ensure the user has one of the allowed roles."""
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action"
            )
        return user

def require_role(roles: List[str]):
    """Helper to return a RoleChecker dependency instance."""
    return Depends(RoleChecker(roles))
