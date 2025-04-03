import time
import functools
import asyncio
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar, cast

T = TypeVar('T')

class Cache:
    """簡單的內存緩存實現，支持TTL和異步函數"""
    
    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        
    def get(self, key: str) -> Optional[Any]:
        """從緩存中獲取值，如果鍵不存在或已過期則返回None"""
        if key not in self._cache:
            return None
            
        value, expiry = self._cache[key]
        if expiry > 0 and time.time() > expiry:
            # 鍵已過期
            del self._cache[key]
            return None
            
        return value
        
    def set(self, key: str, value: Any, ttl: int = 0) -> None:
        """將值存入緩存，可選地設置生存時間（以秒為單位）"""
        expiry = time.time() + ttl if ttl > 0 else 0
        self._cache[key] = (value, expiry)
        
    def delete(self, key: str) -> None:
        """從緩存中刪除鍵"""
        if key in self._cache:
            del self._cache[key]
            
    def clear(self) -> None:
        """清空整個緩存"""
        self._cache.clear()
        
    def cleanup(self) -> None:
        """清理過期的鍵"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if expiry > 0 and current_time > expiry
        ]
        
        for key in expired_keys:
            del self._cache[key]

# 全局緩存實例
_cache = Cache()

def cache(ttl: int = 3600):
    """緩存裝飾器，可用於同步和異步函數
    
    Args:
        ttl: 緩存生存時間（以秒為單位），預設為1小時
        
    例如:
        @cache(ttl=60)  # 緩存60秒
        async def fetch_data(url):
            # 獲取數據的代碼
            return data
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            # 生成緩存鍵
            key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # 檢查緩存
            cached_value = _cache.get(key)
            if cached_value is not None:
                return cached_value
                
            # 如果緩存未命中，調用原始函數
            result = await func(*args, **kwargs)
            
            # 存入緩存
            _cache.set(key, result, ttl)
            
            return result
            
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            # 生成緩存鍵
            key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # 檢查緩存
            cached_value = _cache.get(key)
            if cached_value is not None:
                return cached_value
                
            # 如果緩存未命中，調用原始函數
            result = func(*args, **kwargs)
            
            # 存入緩存
            _cache.set(key, result, ttl)
            
            return result
            
        # 根據函數是否為協程來返回相應的包裝器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
        
    return decorator
    
def invalidate_cache(func_name: str, *args: Any, **kwargs: Any) -> None:
    """手動使特定函數調用的緩存失效"""
    key = f"{func_name}:{str(args)}:{str(kwargs)}"
    _cache.delete(key)
    
def clear_cache() -> None:
    """清空整個緩存"""
    _cache.clear()
    
# 定期清理過期的緩存項
async def cleanup_task(interval: int = 60) -> None:
    """定期清理緩存的後台任務
    
    Args:
        interval: 清理間隔（以秒為單位），預設每分鐘清理一次
    """
    while True:
        _cache.cleanup()
        await asyncio.sleep(interval)  # 可配置清理間隔
        
def start_cleanup_task(interval: int = 60) -> asyncio.Task:
    """啟動緩存清理任務
    
    Args:
        interval: 清理間隔（以秒為單位），預設每分鐘清理一次
        
    Returns:
        緩存清理的非同步任務
    """
    return asyncio.create_task(cleanup_task(interval))

def get_cache_size():
    """
    獲取當前緩存大小
    
    Returns:
        緩存中的項目數量
    """
    return len(_cache._cache)

def get_cache_keys():
    """
    獲取所有緩存鍵
    
    Returns:
        緩存鍵列表
    """
    return list(_cache._cache.keys()) 