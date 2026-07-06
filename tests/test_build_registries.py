"""project_registry.jsonへの primary_alias フィールド追加（Task 0）のテスト。

aliases_for()と同様、案件名のNFC正規化つき突き合わせをprimary_alias_for()でも
行うことを確認する（macOSのNFD分解ディレクトリ名対策）。
"""
from __future__ import annotations

import unicodedata

from scripts.build_registries import primary_alias_for


def test_primary_alias_for_returns_primary_column_value():
    project_primary_aliases = {"京橋信用ソリューションズ株式会社": "KSS"}
    assert primary_alias_for("京橋信用ソリューションズ株式会社", project_primary_aliases) == "KSS"


def test_primary_alias_for_normalizes_nfd_project_names():
    """ディレクトリ名がNFD分解（例: パ→ハ+濁点）でも、NFC同士で突き合わせられること。"""
    nfd_name = unicodedata.normalize("NFD", "株式会社東都人材プラットフォーム")
    project_primary_aliases = {"株式会社東都人材プラットフォーム": "TOTO"}
    assert primary_alias_for(nfd_name, project_primary_aliases) == "TOTO"


def test_primary_alias_for_returns_none_when_not_found():
    assert primary_alias_for("未知の案件", {}) is None
