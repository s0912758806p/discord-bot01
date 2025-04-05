#!/usr/bin/env python3
"""
Discord Bot 測試運行器
用於運行所有測試或指定類型的測試
"""
import os
import sys
import argparse
import unittest
import importlib
import importlib.util
from pathlib import Path

# 確保目錄結構在路徑中
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

# 導入測試配置
from tests.test_config import setup_test_environment

def discover_tests(test_type=None):
    """發現並載入測試模組
    
    Args:
        test_type: 測試類型，可以是'unit', 'integration', 'system'或None(所有測試)
        
    Returns:
        TestSuite: 包含所有發現的測試的測試套件
    """
    test_loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    if test_type:
        # 運行指定類型的測試
        test_dir = os.path.join(PROJECT_ROOT, 'tests', test_type)
        if os.path.exists(test_dir):
            suite.addTests(test_loader.discover(test_dir, pattern='test_*.py'))
        else:
            print(f"錯誤: 找不到測試目錄 {test_dir}")
            sys.exit(1)
    else:
        # 運行所有測試
        for test_dir in ['unit', 'integration', 'system']:
            test_path = os.path.join(PROJECT_ROOT, 'tests', test_dir)
            if os.path.exists(test_path):
                suite.addTests(test_loader.discover(test_path, pattern='test_*.py'))
    
    return suite

def display_help_message():
    """顯示幫助信息"""
    print("Discord Bot 測試運行器")
    print("用法: python run_tests.py [選項]")
    print("\n選項:")
    print("  -t, --type TYPE    運行指定類型的測試 (unit, integration, system)")
    print("  -v, --verbose      輸出詳細的測試結果")
    print("  -f, --failfast     在第一個測試失敗後停止")
    print("  -h, --help         顯示此幫助信息")
    print("\n示例:")
    print("  python run_tests.py                  # 運行所有測試")
    print("  python run_tests.py -t unit          # 僅運行單元測試")
    print("  python run_tests.py -t integration   # 僅運行整合測試")
    print("  python run_tests.py -v -f            # 運行所有測試，詳細輸出並在第一個失敗後停止")

def run_tests(test_type=None, verbose=1, failfast=False):
    """運行測試
    
    Args:
        test_type: 測試類型，可以是'unit', 'integration', 'system'或None(所有測試)
        verbose: 輸出詳細程度，0-3
        failfast: 是否在第一個測試失敗後停止
        
    Returns:
        bool: 測試是否全部通過
    """
    # 設置測試環境
    setup_test_environment()
    
    # 發現測試
    suite = discover_tests(test_type)
    
    # 運行測試
    runner = unittest.TextTestRunner(verbosity=verbose, failfast=failfast)
    result = runner.run(suite)
    
    # 返回測試是否全部通過
    return result.wasSuccessful()

def main():
    """主函數"""
    # 解析命令行參數
    parser = argparse.ArgumentParser(description='Discord Bot 測試運行器', add_help=False)
    parser.add_argument('-t', '--type', choices=['unit', 'integration', 'system'], 
                        help='運行指定類型的測試')
    parser.add_argument('-v', '--verbose', action='count', default=1,
                        help='輸出詳細的測試結果')
    parser.add_argument('-f', '--failfast', action='store_true',
                        help='在第一個測試失敗後停止')
    parser.add_argument('-h', '--help', action='store_true',
                        help='顯示幫助信息')
    
    args = parser.parse_args()
    
    # 顯示幫助信息
    if args.help:
        display_help_message()
        return 0
        
    # 計算詳細程度
    verbose = min(args.verbose, 3)  # 最高為3
    
    # 顯示運行信息
    test_type_str = args.type if args.type else '所有'
    print(f"運行{test_type_str}測試...")
    
    # 運行測試
    success = run_tests(args.type, verbose, args.failfast)
    
    # 返回退出碼
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main()) 