"""社内用語集.docx（提供データ）の表から用語・案件エイリアスを実行時に抽出する。

docx読み込み自体は呼び出し側（scripts/build_registries.py）が行い、
ここでは "表 = list[行] / 行 = list[セル文字列]" という抽出結果だけを受け取る。
用語・エイリアスをコードに手入力しない（competition.md のハードコード禁止事項）ための
唯一のデータソースがこのdocxであり、新しい用語集の版が来ても同じロジックで動く。
"""
from __future__ import annotations

_TERM_HEADER = ["正式名称", "社内用語", "補足"]
_ALIAS_HEADER_PREFIX = ["案件名", "主略称", "別名候補"]


def _clean(text: str) -> str:
    return text.replace("\xa0", " ").strip()


def parse_term_entries(tables: list[list[list[str]]]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for table in tables:
        if not table or [c.strip() for c in table[0]] != _TERM_HEADER:
            continue
        for row in table[1:]:
            if len(row) < 3:
                continue
            expansion, term, note = (_clean(c) for c in row[:3])
            if not term or term in seen:
                continue
            seen.add(term)
            entries.append({"term": term, "expansion": expansion, "note": note})
    return entries


def _split_aliases(text: str) -> list[str]:
    return [a for a in (_clean(part) for part in text.split(",")) if a]


def parse_project_aliases(tables: list[list[list[str]]]) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for table in tables:
        if not table:
            continue
        header = [c.strip() for c in table[0]]
        if header[: len(_ALIAS_HEADER_PREFIX)] != _ALIAS_HEADER_PREFIX:
            continue
        for row in table[1:]:
            if len(row) < 2:
                continue
            name = _clean(row[0])
            primary = _clean(row[1])
            alternates = _split_aliases(row[2]) if len(row) > 2 else []
            if not name:
                continue
            values = [v for v in ([primary] + alternates) if v]
            aliases[name] = sorted(set(values))
    return aliases


def parse_project_primary_aliases(tables: list[list[list[str]]]) -> dict[str, str]:
    """案件名→「主略称」（社内用語集の`主略称`列そのもの）を1件ずつ返す。

    parse_project_aliases()はalternatesと合わせてソート済みの集合を返すため、
    「主略称」の情報が失われる（sorted()後の先頭要素はアルファベット順1位に過ぎず、
    実際の主略称と一致するとは限らない）。cross_project一覧の回答（Q15型）で
    「主略称」を答えるには、primary列を単独で保持するこの関数が必要。
    """
    primaries: dict[str, str] = {}
    for table in tables:
        if not table:
            continue
        header = [c.strip() for c in table[0]]
        if header[: len(_ALIAS_HEADER_PREFIX)] != _ALIAS_HEADER_PREFIX:
            continue
        for row in table[1:]:
            if len(row) < 2:
                continue
            name = _clean(row[0])
            primary = _clean(row[1])
            if not name or not primary:
                continue
            primaries[name] = primary
    return primaries
