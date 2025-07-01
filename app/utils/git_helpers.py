import subprocess
import os
import json
from datetime import datetime

def run_git_command(command: list, timeout: int = 30) -> tuple[bool, str, str]:
    """Git コマンドを安全に実行"""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )
        
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        
    except subprocess.TimeoutExpired:
        return False, "", "コマンドがタイムアウトしました"
    except Exception as e:
        return False, "", f"コマンド実行エラー: {str(e)}"

def get_git_commits() -> dict:
    """Git コミット情報を取得"""
    try:
        # リモートから最新情報を取得
        success, stdout, stderr = run_git_command(['git', 'fetch', 'origin'])
        if not success:
            return {'error': f"fetch失敗: {stderr}"}
        
        # 現在のブランチを取得
        success, current_branch, stderr = run_git_command(['git', 'branch', '--show-current'])
        if not success:
            current_branch = 'main'
        
        # ローカルの最新コミット
        success, local_commit, stderr = run_git_command(['git', 'rev-parse', 'HEAD'])
        if not success:
            return {'error': f"ローカルコミット取得失敗: {stderr}"}
        
        # リモートの最新コミット
        success, remote_commit, stderr = run_git_command(['git', 'rev-parse', f'origin/{current_branch}'])
        if not success:
            return {'error': f"リモートコミット取得失敗: {stderr}"}
        
        # 未プルのコミット一覧
        behind_commits = []
        if local_commit != remote_commit:
            success, log_output, stderr = run_git_command([
                'git', 'log', '--oneline', '--no-merges', 
                f'{local_commit}..origin/{current_branch}'
            ])
            
            if success and log_output:
                behind_commits = [
                    {
                        'hash': line.split()[0],
                        'message': ' '.join(line.split()[1:])
                    }
                    for line in log_output.split('\n') if line.strip()
                ]
        
        # 最新のコミット履歴（表示用）
        success, recent_log, stderr = run_git_command([
            'git', 'log', '--oneline', '--no-merges', '-10'
        ])
        
        recent_commits = []
        if success and recent_log:
            recent_commits = [
                {
                    'hash': line.split()[0],
                    'message': ' '.join(line.split()[1:])
                }
                for line in recent_log.split('\n') if line.strip()
            ]
        
        return {
            'current_branch': current_branch,
            'local_commit': local_commit[:8],
            'remote_commit': remote_commit[:8],
            'behind': behind_commits,
            'recent': recent_commits,
            'has_updates': len(behind_commits) > 0
        }
        
    except Exception as e:
        return {'error': f"Git情報取得エラー: {str(e)}"}

def update_system() -> dict:
    """システムを更新"""
    try:
        # 現在のブランチを確認
        success, current_branch, stderr = run_git_command(['git', 'branch', '--show-current'])
        if not success:
            return {'success': False, 'error': f"ブランチ確認失敗: {stderr}"}
        
        # 作業ディレクトリの状態を確認
        success, status_output, stderr = run_git_command(['git', 'status', '--porcelain'])
        if not success:
            return {'success': False, 'error': f"ステータス確認失敗: {stderr}"}
        
        if status_output.strip():
            return {'success': False, 'error': "作業ディレクトリに未コミットの変更があります"}
        
        # リモートから最新情報を取得
        success, stdout, stderr = run_git_command(['git', 'fetch', 'origin'])
        if not success:
            return {'success': False, 'error': f"fetch失敗: {stderr}"}
        
        # Fast-forward マージで更新
        success, pull_output, stderr = run_git_command(['git', 'pull', '--ff-only', 'origin', current_branch])
        if not success:
            if "not possible to fast-forward" in stderr:
                return {'success': False, 'error': "Fast-forwardマージができません。手動でマージしてください"}
            else:
                return {'success': False, 'error': f"pull失敗: {stderr}"}
        
        return {
            'success': True,
            'message': "システムを更新しました",
            'output': pull_output
        }
        
    except Exception as e:
        return {'success': False, 'error': f"システム更新エラー: {str(e)}"}

def get_git_status() -> dict:
    """Git ステータスを取得"""
    try:
        # ブランチ情報
        success, branch_info, stderr = run_git_command(['git', 'branch', '-v'])
        if not success:
            return {'error': f"ブランチ情報取得失敗: {stderr}"}
        
        # ステータス情報
        success, status_info, stderr = run_git_command(['git', 'status', '--porcelain'])
        if not success:
            return {'error': f"ステータス取得失敗: {stderr}"}
        
        # 未追跡ファイル
        untracked_files = []
        modified_files = []
        staged_files = []
        
        for line in status_info.split('\n'):
            if line.strip():
                status_code = line[:2]
                filename = line[3:]
                
                if status_code == '??':
                    untracked_files.append(filename)
                elif status_code[0] != ' ':
                    staged_files.append(filename)
                elif status_code[1] != ' ':
                    modified_files.append(filename)
        
        return {
            'branch_info': branch_info,
            'untracked_files': untracked_files,
            'modified_files': modified_files,
            'staged_files': staged_files,
            'clean': len(untracked_files) == 0 and len(modified_files) == 0 and len(staged_files) == 0
        }
        
    except Exception as e:
        return {'error': f"Git ステータス取得エラー: {str(e)}"}

def check_git_repository() -> bool:
    """Git リポジトリかどうかを確認"""
    try:
        success, stdout, stderr = run_git_command(['git', 'rev-parse', '--git-dir'])
        return success
    except Exception:
        return False

def get_current_commit_info() -> dict:
    """現在のコミット情報を取得"""
    try:
        # コミットハッシュ
        success, commit_hash, stderr = run_git_command(['git', 'rev-parse', 'HEAD'])
        if not success:
            return {'error': f"コミットハッシュ取得失敗: {stderr}"}
        
        # コミット情報
        success, commit_info, stderr = run_git_command([
            'git', 'log', '-1', '--pretty=format:%H|%an|%ae|%ad|%s', '--date=iso'
        ])
        
        if not success:
            return {'error': f"コミット情報取得失敗: {stderr}"}
        
        parts = commit_info.split('|')
        if len(parts) >= 5:
            return {
                'hash': parts[0][:8],
                'author_name': parts[1],
                'author_email': parts[2],
                'date': parts[3],
                'message': parts[4]
            }
        else:
            return {'error': "コミット情報の解析に失敗しました"}
            
    except Exception as e:
        return {'error': f"コミット情報取得エラー: {str(e)}"}

def validate_git_environment() -> tuple[bool, str]:
    """Git 環境の妥当性を確認"""
    try:
        # Git がインストールされているかチェック
        success, version, stderr = run_git_command(['git', '--version'])
        if not success:
            return False, "Git がインストールされていません"
        
        # Git リポジトリかチェック
        if not check_git_repository():
            return False, "現在のディレクトリはGitリポジトリではありません"
        
        # リモートリポジトリの設定をチェック
        success, remote_info, stderr = run_git_command(['git', 'remote', '-v'])
        if not success or not remote_info:
            return False, "リモートリポジトリが設定されていません"
        
        return True, f"Git環境は正常です ({version})"
        
    except Exception as e:
        return False, f"Git環境チェックエラー: {str(e)}"

def backup_before_update() -> tuple[bool, str]:
    """更新前のバックアップを作成"""
    try:
        # 現在のコミットハッシュを取得
        success, current_commit, stderr = run_git_command(['git', 'rev-parse', 'HEAD'])
        if not success:
            return False, f"現在のコミット取得失敗: {stderr}"
        
        # バックアップタグを作成
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_tag = f"backup_before_update_{timestamp}"
        
        success, tag_output, stderr = run_git_command(['git', 'tag', backup_tag, current_commit])
        if not success:
            return False, f"バックアップタグ作成失敗: {stderr}"
        
        return True, f"バックアップタグ '{backup_tag}' を作成しました"
        
    except Exception as e:
        return False, f"バックアップ作成エラー: {str(e)}"