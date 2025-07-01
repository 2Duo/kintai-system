#!/usr/bin/env python3
"""勤怠管理システムのメインエントリーポイント"""

import sys
import os
from app import create_app

def main():
    """メイン関数"""
    # 引数の処理
    if len(sys.argv) > 1:
        if sys.argv[1] == '--clear-audit-log':
            from app.utils.audit import clear_audit_log
            if clear_audit_log():
                print("監査ログをクリアしました")
            else:
                print("監査ログのクリアに失敗しました")
            return
        elif sys.argv[1] == '--help':
            print("勤怠管理システム")
            print("使用方法:")
            print("  python run.py                  - アプリケーションを開始")
            print("  python run.py --clear-audit-log - 監査ログをクリア")
            print("  python run.py --help           - このヘルプを表示")
            return
    
    # Flaskアプリケーションを作成
    app = create_app()
    
    # デバッグモードの設定
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # ホストとポートの設定
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 8000))
    
    print(f"勤怠管理システムを開始します...")
    print(f"URL: http://{host}:{port}")
    print(f"デバッグモード: {debug_mode}")
    
    # アプリケーションを起動
    app.run(host=host, port=port, debug=debug_mode)

if __name__ == '__main__':
    main()