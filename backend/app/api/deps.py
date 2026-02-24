from collections import deque
from threading import Lock
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.services.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
_RATE_LIMIT_LOCK = Lock()
_RATE_LIMIT_STATE: dict[str, deque[float]] = {}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    username = decode_token(token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証情報が無効です",
        )

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザーが見つかりません",
        )
    return user


def enforce_rate_limit(
    *,
    scope: str,
    identity: str,
    max_requests: int,
    window_seconds: int = 60,
) -> None:
    now = time.time()
    key = f"{scope}:{identity}"

    with _RATE_LIMIT_LOCK:
        bucket = _RATE_LIMIT_STATE.get(key)
        if bucket is None:
            bucket = deque()
            _RATE_LIMIT_STATE[key] = bucket

        cutoff = now - window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= max_requests:
            retry_after = int(max(1, window_seconds - (now - bucket[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Retry in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
