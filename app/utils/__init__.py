# ユーティリティモジュール

from flask import request, redirect, url_for

__all__ = [
    "redirect_embedded",
    "allowed_file",
]


ALLOWED_EXTENSIONS = {"csv"}


def redirect_embedded(endpoint: str, **values):
    """`embedded` クエリパラメータを保持したままリダイレクトする"""
    embedded = request.args.get("embedded") or request.form.get("embedded")
    if embedded:
        values["embedded"] = embedded
    return redirect(url_for(endpoint, **values))


def allowed_file(filename: str) -> bool:
    """アップロード許可ファイルか判定"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
