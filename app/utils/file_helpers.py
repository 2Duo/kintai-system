import os
import time
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import zipfile

def sanitize_filename(filename: str) -> str:
    """ファイル名をサニタイズ"""
    import re
    
    if not filename:
        return "unnamed"
    
    # 危険な文字を除去
    safe_name = re.sub(r'[<>:"/\\|?*]', '', filename)
    
    # 制御文字を除去
    safe_name = ''.join(char for char in safe_name if ord(char) >= 32)
    
    # 先頭・末尾の空白とピリオドを除去
    safe_name = safe_name.strip('. ')
    
    # 長さ制限（255文字）
    if len(safe_name) > 255:
        name, ext = os.path.splitext(safe_name)
        safe_name = name[:255-len(ext)] + ext
    
    # 空文字列の場合はデフォルト名
    if not safe_name:
        safe_name = "unnamed"
    
    return safe_name

def delete_old_exports(base_dir: str = 'exports', days: int = 30) -> int:
    """古いエクスポートファイルを削除"""
    if not os.path.exists(base_dir):
        return 0
    
    threshold = datetime.now() - timedelta(days=days)
    deleted_count = 0
    
    try:
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                file_path = os.path.join(root, file)
                
                try:
                    # ファイルの更新時刻をチェック
                    if os.path.isfile(file_path):
                        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                        if file_time < threshold:
                            os.remove(file_path)
                            deleted_count += 1
                except OSError:
                    # ファイル削除に失敗した場合は継続
                    continue
            
            # 空のディレクトリを削除
            try:
                if not os.listdir(root) and root != base_dir:
                    os.rmdir(root)
            except OSError:
                # ディレクトリ削除に失敗した場合は継続
                continue
                
    except Exception:
        # エラーが発生しても処理を継続
        pass
    
    return deleted_count

def ensure_directory_exists(directory_path: str) -> bool:
    """ディレクトリの存在を確認し、なければ作成"""
    try:
        os.makedirs(directory_path, exist_ok=True)
        return True
    except Exception:
        return False

def validate_file_path(file_path: str, allowed_extensions: list = None) -> tuple[bool, str]:
    """ファイルパスの妥当性を検証"""
    try:
        # パスの正規化
        normalized_path = os.path.normpath(file_path)
        
        # パストラバーサル攻撃の検出
        if '..' in normalized_path or normalized_path.startswith('/'):
            return False, "不正なファイルパスです"
        
        # ファイル拡張子のチェック
        if allowed_extensions:
            _, ext = os.path.splitext(normalized_path.lower())
            if ext not in [f'.{ext.lower()}' for ext in allowed_extensions]:
                return False, f"許可されていないファイル形式です。許可形式: {', '.join(allowed_extensions)}"
        
        return True, ""
        
    except Exception as e:
        return False, f"ファイルパスの検証に失敗しました: {str(e)}"

def secure_file_download(file_path: str, base_directory: str) -> tuple[bool, str]:
    """安全なファイルダウンロードのためのパス検証"""
    try:
        # 絶対パスに変換
        abs_file_path = os.path.abspath(file_path)
        abs_base_dir = os.path.abspath(base_directory)
        
        # ベースディレクトリ内にあるかチェック
        if not abs_file_path.startswith(abs_base_dir):
            return False, "アクセス拒否: ファイルがベースディレクトリ外にあります"
        
        # ファイルの存在チェック
        if not os.path.exists(abs_file_path):
            return False, "ファイルが見つかりません"
        
        # 通常のファイルかチェック（シンボリックリンクは拒否）
        if not os.path.isfile(abs_file_path) or os.path.islink(abs_file_path):
            return False, "不正なファイルタイプです"
        
        return True, abs_file_path
        
    except Exception as e:
        return False, f"ファイル検証エラー: {str(e)}"

def create_temp_file(suffix: str = '', prefix: str = 'temp_', directory: str = None) -> str:
    """一時ファイルを作成"""
    try:
        fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=directory)
        os.close(fd)  # ファイルディスクリプタを閉じる
        return temp_path
    except Exception as e:
        raise Exception(f"一時ファイルの作成に失敗しました: {str(e)}")

def create_temp_directory(prefix: str = 'temp_', directory: str = None) -> str:
    """一時ディレクトリを作成"""
    try:
        return tempfile.mkdtemp(prefix=prefix, dir=directory)
    except Exception as e:
        raise Exception(f"一時ディレクトリの作成に失敗しました: {str(e)}")

def copy_file_safely(source: str, destination: str) -> bool:
    """ファイルを安全にコピー"""
    try:
        # コピー先ディレクトリを作成
        dest_dir = os.path.dirname(destination)
        ensure_directory_exists(dest_dir)
        
        # ファイルをコピー
        shutil.copy2(source, destination)
        return True
        
    except Exception:
        return False

def get_file_size(file_path: str) -> int:
    """ファイルサイズを取得"""
    try:
        return os.path.getsize(file_path)
    except Exception:
        return 0

def get_file_extension(filename: str) -> str:
    """ファイル拡張子を取得"""
    _, ext = os.path.splitext(filename)
    return ext.lower()

def is_allowed_file_type(filename: str, allowed_types: list) -> bool:
    """許可されたファイルタイプかチェック"""
    ext = get_file_extension(filename)
    return ext in [f'.{t.lower()}' for t in allowed_types]

def create_zip_archive(files: list, zip_path: str, compression_level: int = 6) -> bool:
    """ZIPアーカイブを作成"""
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=compression_level) as zipf:
            for file_info in files:
                if isinstance(file_info, tuple):
                    file_path, arcname = file_info
                else:
                    file_path = file_info
                    arcname = os.path.basename(file_path)
                
                if os.path.exists(file_path):
                    zipf.write(file_path, arcname)
        
        return True
        
    except Exception:
        return False

def calculate_directory_size(directory: str) -> int:
    """ディレクトリのサイズを計算"""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, IOError):
                    continue
    except Exception:
        pass
    
    return total_size

def cleanup_temp_files(temp_dir: str, max_age_hours: int = 24) -> int:
    """一時ファイルをクリーンアップ"""
    if not os.path.exists(temp_dir):
        return 0
    
    threshold = time.time() - (max_age_hours * 3600)
    deleted_count = 0
    
    try:
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            
            try:
                if os.path.getmtime(item_path) < threshold:
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        deleted_count += 1
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        deleted_count += 1
            except OSError:
                continue
                
    except Exception:
        pass
    
    return deleted_count