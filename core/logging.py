import logging
import time
import functools
import os
import asyncio
from typing import Callable, Any, Optional, TypeVar, cast
from datetime import datetime

# 確保日誌目錄存在
if not os.path.exists('logs'):
    os.makedirs('logs')

# 配置日誌
logger = logging.getLogger('discord_bot')
logger.setLevel(logging.INFO)

# 控制台處理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_format)

# 文件處理器
log_filename = f"logs/discord_{datetime.now().strftime('%Y%m%d')}.log"
file_handler = logging.FileHandler(filename=log_filename, encoding='utf-8', mode='a')
file_handler.setLevel(logging.INFO)
file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_format)

# 添加處理器
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# 測量函數執行時間的裝飾器
T = TypeVar('T')

def measure_time(func: Callable[..., T]) -> Callable[..., T]:
    """裝飾器：測量並記錄函數執行時間"""
    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            elapsed_time = time.time() - start_time
            logger.info(f"函數 {func.__name__} 執行時間: {elapsed_time:.3f}秒")
            return result
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"函數 {func.__name__} 執行出錯，耗時: {elapsed_time:.3f}秒，錯誤: {e}")
            raise
            
    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed_time = time.time() - start_time
            logger.info(f"函數 {func.__name__} 執行時間: {elapsed_time:.3f}秒")
            return result
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"函數 {func.__name__} 執行出錯，耗時: {elapsed_time:.3f}秒，錯誤: {e}")
            raise
            
    if asyncio.iscoroutinefunction(func):
        return cast(Callable[..., T], async_wrapper)
    return cast(Callable[..., T], sync_wrapper)

def log_command(command_name: Optional[str] = None):
    """裝飾器：記錄命令執行日誌"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cmd = command_name or func.__name__
            user = args[1].author.display_name if len(args) > 1 else "Unknown"
            logger.info(f"命令 {cmd} 被用戶 {user} 調用")
            return await func(*args, **kwargs)
        return wrapper
    return decorator 