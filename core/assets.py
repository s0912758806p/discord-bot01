"""圖片資源路徑。

以「檔名」引用圖片（不要用 setting.json 的 IMAGE 索引：清單插入一張圖就會全部錯位），
並轉成以專案根目錄為基準的絕對路徑，與啟動時的工作目錄無關。
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = PROJECT_ROOT / 'assets' / 'img'


def img(name: str) -> str:
    """assets/img/ 底下的檔案（可含子目錄，例如 'puqian/large_lucky.png'）的絕對路徑。"""
    return str(IMG_DIR / name)
