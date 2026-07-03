"""質問文を要求能力タグに分類するヒューリスティック。ベースラインの理論上限スコア見積もりに使う。"""
from __future__ import annotations

IMAGE_KEYWORDS = (".png", ".jpg", "画像", "グラフ", "figure", "マーカー", "折れ線", "図")
VERSION_DIFF_KEYWORDS = ("old", "旧版", "新旧", "更新内容", "実質的な変更", "最新版")
PASSWORD_KEYWORDS = ("パスワード", "password", "保護されたファイル")
MULTI_HOP_KEYWORDS = ("すべての案件", "各案件", "複数の案件", "全案件")


def classify_question(question: str) -> list[str]:
    tags: list[str] = []
    lower = question.lower()
    if any(k.lower() in lower for k in IMAGE_KEYWORDS):
        tags.append("image_or_graph")
    if any(k in question for k in VERSION_DIFF_KEYWORDS):
        tags.append("version_diff")
    if any(k.lower() in lower for k in PASSWORD_KEYWORDS):
        tags.append("password_protected")
    if any(k in question for k in MULTI_HOP_KEYWORDS):
        tags.append("multi_hop")
    if not tags:
        tags.append("text_only")
    return tags
