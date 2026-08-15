# modules/utils/cache.py
"""
簡單磁碟快取，減少 yfinance 重複請求與提升穩定性。
使用 pickle + 檔名 hash，TTL 預設 6 小時。
"""
import hashlib
import pickle
import time
from pathlib import Path
from typing import Any, Optional, Callable
import functools

CACHE_DIR = Path(__file__).resolve().parents[2] / "cache"
CACHE_DIR.mkdir(exist_ok=True)

DEFAULT_TTL = 6 * 3600  # 6 hours


def _key_to_path(key: str) -> Path:
    h = hashlib.md5(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{h}.pkl"


def cache_get(key: str, ttl: int = DEFAULT_TTL) -> Optional[Any]:
    path = _key_to_path(key)
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            payload = pickle.load(f)
        if time.time() - payload["ts"] > ttl:
            path.unlink(missing_ok=True)
            return None
        return payload["data"]
    except Exception:
        return None


def cache_set(key: str, data: Any) -> None:
    path = _key_to_path(key)
    try:
        with open(path, "wb") as f:
            pickle.dump({"ts": time.time(), "data": data}, f)
    except Exception:
        pass


def cached(key_prefix: str, ttl: int = DEFAULT_TTL):
    """裝飾器：依函式參數產生 cache key"""
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key_parts = [key_prefix]
            if args and hasattr(args[0], "__class__"):
                key_parts.extend(str(a) for a in args[1:])
            else:
                key_parts.extend(str(a) for a in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            key = "|".join(key_parts)
            hit = cache_get(key, ttl=ttl)
            if hit is not None:
                return hit
            result = func(*args, **kwargs)
            cache_set(key, result)
            return result
        return wrapper
    return decorator
