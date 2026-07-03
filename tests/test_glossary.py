"""社内用語集.docx の表データから用語・案件エイリアスを抽出するロジックのテスト（TDD）。

docx読み込み自体はテストしない（scripts/build_registries.py 側のI/Oグルー）。
ここでは "表 = list[行] / 行 = list[セル文字列]" というpython-docxのTable抽出結果に
相当する構造だけを渡して、純粋関数の抽出ロジックを検証する。
"""
from __future__ import annotations

from src.utils.glossary import parse_project_aliases, parse_term_entries

TERM_TABLE = [
    ["正式名称", "社内用語", "補足"],
    ["提案書", "PP", "Proposal Pack / Proposal Presentation"],
    ["契約書", "CT", "Contract"],
]

OTHER_TERM_TABLE = [
    ["正式名称", "社内用語", "補足"],
    ["目的変数", "TG", "Target"],
    ["提案書", "PP", "重複エントリ（先勝ちで無視される）"],
]

NON_TERM_TABLE = [
    ["列A", "列B"],
    ["x", "y"],
]

ALIAS_TABLE = [
    ["案件名", "主略称", "別名候補", "補足"],
    ["京橋信用ソリューションズ株式会社", "KSS", "京ソ,\xa0京橋,\xa0京ソリ,\xa0KYO", "KSS を正式"],
    ["案件横断", "CROSS", "横断,\xa0案件横断", "将来変動あり"],
]


def test_parse_term_entries_extracts_term_and_expansion():
    entries = parse_term_entries([TERM_TABLE])
    assert entries == [
        {"term": "PP", "expansion": "提案書", "note": "Proposal Pack / Proposal Presentation"},
        {"term": "CT", "expansion": "契約書", "note": "Contract"},
    ]


def test_parse_term_entries_ignores_non_matching_tables():
    entries = parse_term_entries([NON_TERM_TABLE])
    assert entries == []


def test_parse_term_entries_dedupes_by_term_first_wins():
    entries = parse_term_entries([TERM_TABLE, OTHER_TERM_TABLE])
    terms = [e["term"] for e in entries]
    assert terms.count("PP") == 1
    pp_entry = next(e for e in entries if e["term"] == "PP")
    assert pp_entry["note"] == "Proposal Pack / Proposal Presentation"


def test_parse_term_entries_across_multiple_tables():
    entries = parse_term_entries([TERM_TABLE, OTHER_TERM_TABLE])
    terms = {e["term"] for e in entries}
    assert terms == {"PP", "CT", "TG"}


def test_parse_project_aliases_splits_comma_separated_with_nbsp():
    aliases = parse_project_aliases([ALIAS_TABLE])
    assert aliases["京橋信用ソリューションズ株式会社"] == sorted(
        {"KSS", "京ソ", "京橋", "京ソリ", "KYO"}
    )


def test_parse_project_aliases_includes_meta_rows():
    aliases = parse_project_aliases([ALIAS_TABLE])
    assert "CROSS" in aliases["案件横断"]


def test_parse_project_aliases_ignores_non_alias_tables():
    aliases = parse_project_aliases([TERM_TABLE, NON_TERM_TABLE])
    assert aliases == {}


def test_parse_project_aliases_ignores_term_tables_mixed_in():
    aliases = parse_project_aliases([TERM_TABLE, ALIAS_TABLE])
    assert set(aliases) == {"京橋信用ソリューションズ株式会社", "案件横断"}
