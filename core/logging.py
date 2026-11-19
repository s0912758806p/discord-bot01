"""
集中式日誌設定（全專案只在這裡設定一次）。

- handler 掛在 root logger：discord.py 自己的 'discord' logger 與本專案的
  'discord_bot' logger 都會輸出到同一組 handler，且每行只印一次。
- 檔案：logs/discord.log，RotatingFileHandler（LOG_MAX_BYTES，預設 5MB；
  LOG_BACKUP_COUNT，預設 5 份），不會每次啟動多一個檔案。
- 等級：LOG_LEVEL（預設 INFO）。
"""
import logging
import time
import functools
import os
import asyncio
from logging.handlers import RotatingFileHandler
from typing import Callable, Any, Optional, TypeVar, cast

LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'discord.log')
_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
_FILE_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _configure_root() -> str:
    log_level_name = os.environ.get('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    root = logging.getLogger()
    if getattr(root, '_discord_bot_configured', False):
        return log_level_name
    root.setLevel(log_level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(console_handler)

    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=_int_env('LOG_MAX_BYTES', 5 * 1024 * 1024),
        backupCount=_int_env('LOG_BACKUP_COUNT', 5),
        encoding='utf-8',
    )
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    root.addHandler(file_handler)

    # discord.py 的 DEBUG 會印出每個 gateway 封包，除非明確要求否則壓到 INFO
    if log_level < logging.INFO:
        logging.getLogger('discord').setLevel(logging.INFO)

    root._discord_bot_configured = True  # type: ignore[attr-defined]
    return log_level_name


_level_name = _configure_root()
logger = logging.getLogger('discord_bot')
logger.info("日誌系統初始化完成，級別: %s, 文件: %s", _level_name, LOG_FILE)

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
            logger.error(f"函數 {func.__name__} 執行出錯，耗時: {elapsed_time:.3f}秒，錯誤: {e}", exc_info=True)
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
            logger.error(f"函數 {func.__name__} 執行出錯，耗時: {elapsed_time:.3f}秒，錯誤: {e}", exc_info=True)
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
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"命令 {cmd} 執行出錯: {e}", exc_info=True)
                raise
        return wrapper
    return decorator 