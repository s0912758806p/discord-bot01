import time
import functools
import asyncio
import os
import logging
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar, cast, List

T = TypeVar('T')

class Cache:
    """簡單的內存緩存實現，支持TTL和異步函數，帶效能統計"""
    
    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        # 統計計數器
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._deletes = 0
        self._cleanups = 0
        
    def get(self, key: str) -> Optional[Any]:
        """從緩存中獲取值，如果鍵不存在或已過期則返回None"""
        if key not in self._cache:
            self._misses += 1
            return None
            
        value, expiry = self._cache[key]
        if expiry > 0 and time.time() > expiry:
            # 鍵已過期
            del self._cache[key]
            self._misses += 1
            return None
            
        self._hits += 1
        return value
        
    def set(self, key: str, value: Any, ttl: int = 0) -> None:
        """將值存入緩存，可選地設置生存時間（以秒為單位）"""
        expiry = time.time() + ttl if ttl > 0 else 0
        self._cache[key] = (value, expiry)
        self._sets += 1
        
    def delete(self, key: str) -> None:
        """從緩存中刪除鍵"""
        if key in self._cache:
            del self._cache[key]
            self._deletes += 1
            
    def clear(self) -> None:
        """清空整個緩存"""
        count = len(self._cache)
        self._cache.clear()
        self._deletes += count
        
    def cleanup(self) -> None:
        """清理過期的鍵"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if expiry > 0 and current_time > expiry
        ]
        
        for key in expired_keys:
            del self._cache[key]
            
        if expired_keys:
            self._cleanups += len(expired_keys)
            logging.debug(f"緩存清理: 移除了 {len(expired_keys)} 個過期項目")
            
    def get_stats(self) -> Dict[str, Any]:
        """獲取緩存統計信息"""
        total_operations = self._hits + self._misses
        hit_rate = (self._hits / total_operations * 100) if total_operations > 0 else 0
        
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "sets": self._sets,
            "deletes": self._deletes,
            "cleanups": self._cleanups,
            "hit_rate": f"{hit_rate:.1f}%"
        }
        
    def reset_stats(self) -> None:
        """重置統計計數器"""
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._deletes = 0
        self._cleanups = 0

# 全局緩存實例
_cache = Cache()

# 從環境變數獲取緩存配置
try:
    cache_ttl_str = os.environ.get('CACHE_TTL', '3600')
    # 確保值是數字，去除可能的註釋或空格
    if '#' in cache_ttl_str:
        cache_ttl_str = cache_ttl_str.split('#')[0].strip()
    DEFAULT_TTL = int(cache_ttl_str)
except (ValueError, TypeError):
    DEFAULT_TTL = 3600  # 默認為1小時
    logging.warning(f"無法解析CACHE_TTL值 '{os.environ.get('CACHE_TTL')}', 使用預設值 3600 秒")

try:
    cleanup_interval_str = os.environ.get('CACHE_CLEANUP_INTERVAL', '60')
    # 確保值是數字，去除可能的註釋或空格
    if '#' in cleanup_interval_str:
        cleanup_interval_str = cleanup_interval_str.split('#')[0].strip()
    CLEANUP_INTERVAL = int(cleanup_interval_str)
except (ValueError, TypeError) as e:
    CLEANUP_INTERVAL = 60  # 默認為1分鐘
    logging.warning(f"無法解析CACHE_CLEANUP_INTERVAL值 '{os.environ.get('CACHE_CLEANUP_INTERVAL')}', 使用預設值 60 秒: {e}")

def cache(ttl: int = DEFAULT_TTL):
    """緩存裝飾器，可用於同步和異步函數
    
    Args:
        ttl: 緩存生存時間（以秒為單位），預設從環境變數獲取
        
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
            start_time = time.time()
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # 記錄較慢的調用
            if execution_time > 1.0:  # 超過1秒的調用視為慢調用
                logging.info(f"慢速函數調用: {func.__name__} 耗時 {execution_time:.3f}秒")
            
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
            start_time = time.time()
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # 記錄較慢的調用
            if execution_time > 0.5:  # 同步函數超過0.5秒視為慢調用
                logging.info(f"慢速函數調用: {func.__name__} 耗時 {execution_time:.3f}秒")
            
            # 存入緩存
            _cache.set(key, result, ttl)
            
            return result
            
        # 根據函數是否為協程來返回相應的包裝器
        if asyncio.iscoroutinefunction(func):
            return cast(Callable, async_wrapper)
        return cast(Callable, sync_wrapper)
        
    return decorator
    
def invalidate_cache(func_name: str, *args: Any, **kwargs: Any) -> None:
    """手動使特定函數調用的緩存失效"""
    key = f"{func_name}:{str(args)}:{str(kwargs)}"
    _cache.delete(key)
    
def clear_cache() -> None:
    """清空整個緩存"""
    _cache.clear()
    logging.info("緩存已清空")
    
# 定期清理過期的緩存項
async def cleanup_task(interval: int = CLEANUP_INTERVAL) -> None:
    """定期清理緩存的後台任務
    
    Args:
        interval: 清理間隔（以秒為單位），預設從環境變數獲取
    """
    logging.info(f"緩存清理任務已啟動，間隔 {interval} 秒")
    while True:
        try:
            _cache.cleanup()
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logging.info("緩存清理任務已取消")
            break
        except Exception as e:
            logging.error(f"緩存清理任務出錯: {e}")
            await asyncio.sleep(interval)  # 發生錯誤時仍繼續任務
        
def start_cleanup_task(interval: int = CLEANUP_INTERVAL) -> asyncio.Task:
    """啟動緩存清理任務
    
    Args:
        interval: 清理間隔（以秒為單位），預設從環境變數獲取
        
    Returns:
        緩存清理的非同步任務
    """
    return asyncio.create_task(cleanup_task(interval))

def get_cache_size() -> int:
    """
    獲取當前緩存大小
    
    Returns:
        緩存中的項目數量
    """
    return len(_cache._cache)

def get_cache_keys() -> List[str]:
    """
    獲取所有緩存鍵
    
    Returns:
        緩存鍵列表
    """
    return list(_cache._cache.keys())

def get_cache_stats() -> Dict[str, Any]:
    """
    獲取緩存統計信息
    
    Returns:
        包含命中率等統計信息的字典
    """
    return _cache.get_stats()

def reset_cache_stats() -> None:
    """
    重置緩存統計計數器
    """
    _cache.reset_stats()
    logging.info("緩存統計已重置") 