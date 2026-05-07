from django.core.cache import cache
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

def generate_cache_key(prefix, params):
    """
    Generate a deterministic cache key based on a prefix and a dict of parameters.
    """
    # Sort keys to ensure consistent hashing
    sorted_params = json.dumps(params, sort_keys=True)
    hash_val = hashlib.md5(sorted_params.encode()).hexdigest()
    return f"{prefix}_{hash_val}"

def invalidate_cache_pattern(pattern):
    """
    Invalidate all keys matching a pattern. 
    Uses cache.delete_pattern if using django-redis, 
    otherwise falls back to a no-op or manual clear (if necessary).
    """
    try:
        if hasattr(cache, 'delete_pattern'):
            cache.delete_pattern(pattern)
            logger.info(f"Invalidated cache pattern: {pattern}")
        else:
            # Fallback for non-redis backends - we might need to clear everything
            # or just ignore if it's a minor performance hit.
            # cache.clear() 
            pass
    except Exception as e:
        logger.error(f"Error invalidating cache pattern {pattern}: {e}")

def get_cached_response(key):
    return cache.get(key)

def set_cached_response(key, data, timeout=300):
    cache.set(key, data, timeout)
