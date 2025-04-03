import json
import os
from typing import Any, Dict, Union

# 緩存已加載的配置
_config_cache: Dict[str, Dict[str, Any]] = {}

def load_config(file_path: str, reload: bool = False) -> Dict[str, Any]:
    """
    加載配置文件
    
    Args:
        file_path: 配置文件路徑
        reload: 是否強制重新加載，而不使用緩存
        
    Returns:
        配置數據字典
    """
    # 如果已經在緩存中且不需要重新加載，直接返回
    if not reload and file_path in _config_cache:
        return _config_cache[file_path]
        
    # 確保文件存在
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"配置文件 {file_path} 不存在")
        
    # 讀取JSON文件
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件 {file_path} 格式錯誤: {e}")
        
    # 更新緩存
    _config_cache[file_path] = config
    
    return config
    
def save_config(file_path: str, config: Dict[str, Any]) -> None:
    """
    保存配置到文件
    
    Args:
        file_path: 配置文件路徑
        config: 配置數據
    """
    # 確保目錄存在，只有當file_path包含目錄路徑時才創建
    dirname = os.path.dirname(file_path)
    if dirname:  # 只有當dirname非空時才創建目錄
        os.makedirs(dirname, exist_ok=True)
    
    # 寫入JSON文件
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
        
    # 更新緩存
    _config_cache[file_path] = config

def get_config_value(file_path: str, key: str, default: Any = None) -> Any:
    """
    獲取配置中的指定值
    
    Args:
        file_path: 配置文件路徑
        key: 配置鍵
        default: 如果鍵不存在，返回的默認值
        
    Returns:
        配置值或默認值
    """
    config = load_config(file_path)
    return config.get(key, default)
    
def set_config_value(file_path: str, key: str, value: Any, save: bool = True) -> None:
    """
    設置配置中的指定值
    
    Args:
        file_path: 配置文件路徑
        key: 配置鍵
        value: 配置值
        save: 是否立即保存到文件
    """
    config = load_config(file_path)
    config[key] = value
    
    if save:
        save_config(file_path, config)
    else:
        _config_cache[file_path] = config 