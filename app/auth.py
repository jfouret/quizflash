import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from fastmcp.server.auth import AccessToken, TokenVerifier
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, delete, select

from app.models import ApiToken, AppSettings, AuthSession, User, as_utc, utc_now

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
MIN_PASSWORD_LENGTH = 12
TOKEN_PREFIX = "qd_"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AuthConfig:
    cookie_secure: bool = True
    session_idle: timedelta = timedelta(days=7)
    session_max: timedelta = timedelta(days=30)
    secret_key: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_scopes: str = "openid email profile"
    oidc_role_claim: str = "roles"
    oidc_admin_role: str = "admin"

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer)

    @property
    def cookie_name(self) -> str:
        # __Host- forces Secure, Path=/ and no Domain in compliant browsers.
        return "__Host-session" if self.cookie_secure else "quizdeck_session"

    @classmethod
    def from_env(cls) -> "AuthConfig":
        issuer = os.getenv("OIDC_ISSUER") or None
        secret = os.getenv("SECRET_KEY")
        if issuer and not secret:
            raise RuntimeError("SECRET_KEY is required when OIDC_ISSUER is set")
        if issuer and not (os.getenv("OIDC_CLIENT_ID") and os.getenv("OIDC_CLIENT_SECRET")):
            raise RuntimeError("OIDC_CLIENT_ID and OIDC_CLIENT_SECRET are required with OIDC")
        return cls(
            cookie_secure=_env_bool("COOKIE_SECURE", True),
            session_idle=timedelta(hours=int(os.getenv("SESSION_IDLE_HOURS", "168"))),
            session_max=timedelta(hours=int(os.getenv("SESSION_MAX_HOURS", "720"))),
            secret_key=secret or secrets.token_urlsafe(32),
            oidc_issuer=issuer,
            oidc_client_id=os.getenv("OIDC_CLIENT_ID"),
            oidc_client_secret=os.getenv("OIDC_CLIENT_SECRET"),
            oidc_scopes=os.getenv("OIDC_SCOPES", "openid email profile"),
            oidc_role_claim=os.getenv("OIDC_ROLE_CLAIM", "roles"),
            oidc_admin_role=os.getenv("OIDC_ADMIN_ROLE", "admin"),
        )


# --- Passwords ----------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check; unknown users still pay the hashing cost."""
    try:
        _, n, r, p, salt, expected = (stored or _DUMMY_HASH).split("$")
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
    except ValueError:
        return False
    return stored is not None and hmac.compare_digest(digest.hex(), expected)


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- Browser sessions ---------------------------------------------------------


def create_session(db: Session, user: User, user_agent: str, config: AuthConfig) -> str:
    """Issue a fresh opaque token; only its hash is stored."""
    if user.id is None:
        raise ValueError("User has no ID")
    token = secrets.token_urlsafe(32)
    now = utc_now()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=_hash_token(token),
            csrf_token=secrets.token_urlsafe(32),
            user_agent=user_agent[:200],
            created_at=now,
            last_seen_at=now,
            expires_at=now + config.session_max,
        )
    )
    user.last_login_at = now
    db.add(user)
    db.exec(delete(AuthSession).where(col(AuthSession.expires_at) < now))
    db.commit()
    return token


def resolve_session(db: Session, token: str, config: AuthConfig) -> tuple[AuthSession, User] | None:
    auth_session = db.exec(
        select(AuthSession).where(AuthSession.token_hash == _hash_token(token))
    ).first()
    if auth_session is None:
        return None
    now = utc_now()
    expired = as_utc(auth_session.expires_at) <= now or (
        as_utc(auth_session.last_seen_at) + config.session_idle <= now
    )
    user = db.get(User, auth_session.user_id)
    if expired or user is None or user.status != "active":
        db.delete(auth_session)
        db.commit()
        return None
    if now - as_utc(auth_session.last_seen_at) > timedelta(minutes=1):
        auth_session.last_seen_at = now
        db.add(auth_session)
        db.commit()
        db.refresh(auth_session)
    return auth_session, user


def delete_session(db: Session, token: str) -> None:
    db.exec(delete(AuthSession).where(col(AuthSession.token_hash) == _hash_token(token)))
    db.commit()


class LoginThrottle:
    """shortcut: in-memory, per process; move to a shared store when running several workers."""

    def __init__(self, max_failures: int = 5, window_s: float = 900) -> None:
        self.max_failures = max_failures
        self.window_s = window_s
        self.failures: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        cutoff = time.monotonic() - self.window_s
        recent = [stamp for stamp in self.failures.get(key, []) if stamp > cutoff]
        self.failures[key] = recent
        return recent

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.max_failures

    def fail(self, key: str) -> None:
        self._recent(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self.failures.pop(key, None)


# --- Users --------------------------------------------------------------------


def create_local_user(
    db: Session,
    *,
    email: str,
    password: str,
    display_name: str = "",
    role: str = "user",
    status: str = "pending",
) -> User:
    validate_password(password)
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError("A valid email is required")
    if db.exec(select(User).where(User.email == email)).first() is not None:
        raise ValueError("An account with this email already exists")
    user = User(
        email=email,
        display_name=display_name.strip() or email.split("@")[0],
        password_hash=hash_password(password),
        role=role,
        status=status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_local(db: Session, email: str, password: str) -> User | None:
    user = db.exec(select(User).where(User.email == email.strip().lower())).first()
    if not verify_password(password, user.password_hash if user else None):
        return None
    return user


def _claim(claims: dict[str, Any], path: str) -> Any:
    value: Any = claims
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def oidc_role(claims: dict[str, Any], config: AuthConfig) -> str:
    roles = _claim(claims, config.oidc_role_claim)
    if isinstance(roles, str):
        roles = roles.split()
    return "admin" if isinstance(roles, list) and config.oidc_admin_role in roles else "user"


def provision_oidc_user(db: Session, claims: dict[str, Any], config: AuthConfig) -> User:
    """Match strictly on (iss, sub); email is never used to link accounts."""
    issuer, subject = claims.get("iss"), claims.get("sub")
    if not issuer or not subject:
        raise ValueError("ID token is missing iss or sub")
    user = db.exec(
        select(User).where(User.oidc_issuer == issuer, User.oidc_subject == subject)
    ).first()
    role = oidc_role(claims, config)
    if user is None:
        app_settings = db.get(AppSettings, 1) or AppSettings()
        if app_settings.registration == "closed" and role != "admin":
            raise PermissionError("Registration is closed")
        email = str(claims.get("email") or f"{subject}@{issuer}").lower()
        if db.exec(select(User).where(User.email == email)).first() is not None:
            raise PermissionError("Another account already uses this email")
        user = User(
            email=email,
            oidc_issuer=issuer,
            oidc_subject=subject,
            status="active"
            if app_settings.registration == "open" or role == "admin"
            else "pending",
        )
    user.display_name = str(claims.get("name") or claims.get("preferred_username") or user.email)
    if user.role != role and user.id is not None:
        db.exec(delete(AuthSession).where(col(AuthSession.user_id) == user.id))
    user.role = role
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- MCP tokens ---------------------------------------------------------------


def create_api_token(db: Session, user: User, name: str) -> tuple[ApiToken, str]:
    if user.id is None:
        raise ValueError("User has no ID")
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token = ApiToken(
        user_id=user.id, name=name.strip(), prefix=raw[:10], token_hash=_hash_token(raw)
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token, raw


def list_api_tokens(db: Session, user: User) -> list[ApiToken]:
    statement = select(ApiToken).where(ApiToken.user_id == user.id).order_by(col(ApiToken.id))
    return list(db.exec(statement).all())


def revoke_api_token(db: Session, user: User, token_id: int) -> None:
    token = db.get(ApiToken, token_id)
    if token is None or token.user_id != user.id:
        raise LookupError(f"Token {token_id} not found")
    if token.revoked_at is None:
        token.revoked_at = utc_now()
        db.add(token)
        db.commit()


def user_for_api_token(db: Session, raw: str) -> User | None:
    if not raw.startswith(TOKEN_PREFIX):
        return None
    token = db.exec(select(ApiToken).where(ApiToken.token_hash == _hash_token(raw))).first()
    if token is None or token.revoked_at is not None:
        return None
    user = db.get(User, token.user_id)
    if user is None or user.status != "active":
        return None
    token.last_used_at = utc_now()
    db.add(token)
    db.commit()
    return user


class ApiTokenVerifier(TokenVerifier):
    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine

    async def verify_token(self, token: str) -> AccessToken | None:
        with Session(self.engine) as db:
            user = user_for_api_token(db, token)
            if user is None:
                return None
            return AccessToken(token=token, client_id=str(user.id), scopes=[])
