"""質問文中に明示されたファイル名の抽出と、ソースパスとの照合。

抽出は「拡張子付きトークン」の一般則のみ（質問文由来の値だけを使う）。
特定のファイル名・案件名はハードコードしない。
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable

# 空白・和文/欧文の区切り記号で切れる連続文字列＋既知拡張子。
# 「::」はチャンクlocation区切りのため除外対象に含める。
# 助詞かな（の・に・で・と・は・を・が・も・や）は境界記号に含めない —
# 「〜市場の未来予測.pdf」「見積もり一覧.xlsx」のようにファイル名内部に
# これらの文字を含む実在ファイルが切り詰められ、既知basenameとの照合が
# 常に失敗する問題を防ぐため。名指しファイルの主な照合は本モジュールの
# find_named_files（既知basename集合との部分文字列照合）で行い、ゲートは
# question_mentions_extension が担う。この正規表現ベースの抽出
# （extract_file_names / matches_file_name）は現在src/から呼ばれていない
# （境界推測ゆえ助詞かな直後のファイル名を取り逃すため、再利用しないこと）。
_FILE_BOUNDARY_CHARS = r"\s、。，「」『』（）()：:；;・？！?!*/\\"
_FILE_NAME_RE = re.compile(
    rf"[^{_FILE_BOUNDARY_CHARS}]+"
    r"\.(?:xlsx|xlsm|pptx|docx|pdf|csv|ipynb|txt|md)"
    rf"(?=$|[{_FILE_BOUNDARY_CHARS}])",
    re.IGNORECASE,
)

# 「質問文に既知拡張子のトークンが現れているか」を見るだけの軽量ゲート。
# 境界文字に依存しないため、助詞かな直後でも拡張子トークンさえあれば検出できる。
_EXTENSION_TOKEN_RE = re.compile(
    r"\.(?:xlsx|xlsm|pptx|docx|pdf|csv|ipynb|txt|md)", re.IGNORECASE
)


def extract_file_names(question: str) -> list[str]:
    """質問中の拡張子付きファイル名をNFC正規化して出現順に返す（重複除去）。"""
    normalized = unicodedata.normalize("NFC", question)
    seen: list[str] = []
    for match in _FILE_NAME_RE.finditer(normalized):
        name = match.group(0)
        if name not in seen:
            seen.append(name)
    return seen


def matches_file_name(source: str | Path, file_names: list[str]) -> bool:
    """sourceのbasenameが file_names のいずれかとNFC一致するか。"""
    if not file_names:
        return False
    basename = unicodedata.normalize("NFC", Path(str(source)).name)
    return basename in file_names


def question_mentions_extension(question: str) -> bool:
    """質問文に既知拡張子のトークン（.xlsx等）が含まれるかの軽量ゲート。
    抽出精度は問わない（find_named_filesを呼ぶ価値があるかどうかの判定用）。"""
    normalized = unicodedata.normalize("NFC", question)
    return bool(_EXTENSION_TOKEN_RE.search(normalized))


def find_named_files(question: str, known_names: Iterable[str | Path]) -> list[str]:
    """質問文に部分文字列として出現する既知ファイル名(basename)を返す。

    抽出ベースの matches_file_name/extract_file_names と異なり、境界文字に
    依存しない: 既知のbasename集合を先に用意し、それぞれが質問文中に部分
    文字列として現れるかどうかだけで判定するため、ファイル名内部に助詞かな
    (の・に・で・と・は・を・が・も・や 等)を含んでいても切り詰められない。

    複数の既知basenameが互いに部分文字列関係にある場合（例: 「一覧.xlsx」と
    「見積もり一覧.xlsx」）は出現位置で判定する: 短い名前の出現がすべて
    より長い一致名の出現区間の内側にあるなら内部一致とみなして除外し、
    独立した出現が1つでもあれば残す。返り値はNFC正規化済みのbasenameで、
    known_namesの出現順を保つ（重複basenameは最初の1件のみ）。
    """
    question_norm = unicodedata.normalize("NFC", question).casefold()

    ordered_basenames: dict[str, str] = {}
    for name in known_names:
        basename_nfc = unicodedata.normalize("NFC", Path(str(name)).name)
        key = basename_nfc.casefold()
        if not key or key in ordered_basenames:
            continue
        ordered_basenames[key] = basename_nfc

    spans: dict[str, list[tuple[int, int]]] = {}
    for key in ordered_basenames:
        occurrences = [
            (m.start(), m.end()) for m in re.finditer(re.escape(key), question_norm)
        ]
        if occurrences:
            spans[key] = occurrences

    kept_keys = []
    for key, occurrences in spans.items():
        longer_spans = [
            span
            for other, other_occurrences in spans.items()
            if other != key and key in other
            for span in other_occurrences
        ]
        has_independent_occurrence = any(
            not any(o_start <= start and end <= o_end for o_start, o_end in longer_spans)
            for start, end in occurrences
        )
        if has_independent_occurrence:
            kept_keys.append(key)
    return [ordered_basenames[key] for key in kept_keys]


_HINT_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]{1,5}$")
_ASCII_ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")


def _ascii_word_boundary_match(hint: str, stem: str) -> bool:
    """ASCII英数字hintがstem中に語境界付きで現れるかを判定する。
    "Gain"が"再検証_gainful"（境界なしで隣接alnumが続く）には一致せず、
    "report_gain_v1"（前後がアンダースコア等の非alnum）には一致するようにする。"""
    pattern = re.compile(rf"(?<![0-9a-z]){re.escape(hint)}(?![0-9a-z])")
    return bool(pattern.search(stem))


def find_stem_matches(hints: Iterable[str], known_names: Iterable[str | Path]) -> list[str]:
    """用語集展開語（例: "CT"→"契約書"）のヒント文字列が、既知ファイルのstem
    （basenameから拡張子を除いた部分）と関連するものを返す。

    質問文そのものではなくQueryExpanderが実際に適用した展開語のみをhintsに渡すこと
    （質問文中の任意の文字列との偶然一致を避けるため）。マッチ規則は3種類:

    1. hintが拡張子付き（例: "train.xlsx"・"01_eda.ipynb" — term_registryが
       特定の1ファイルを指す展開語）の場合、hintのstemと候補basenameのstemが
       完全一致する場合のみ一致とみなす（部分文字列一致にすると、"01_eda.ipynb"
       が実データで同一プロジェクトに実在する無関係な"eda.py"にも誤ヒットする）。
    2. hintが拡張子なしのASCII英数字のみ（例: term_registry実在の"Lift"・
       "Gain"・"MAE"等の英語メトリック名）の場合、非alnum文字（アンダースコア・
       ハイフン等）で区切られた語境界付きの一致のみ許可する（境界なしだと
       "uplift_model"・"再検証_gainful"・"yamae_note"のような英単語の一部に
       偶然含まれて誤マッチする）。
    3. それ以外（日本語等の非ASCII、またはASCII+非ASCII混在のhint）は、
       stemがhintを含む場合（例: stem="契約書_draft" / hint="契約書"）と
       hintがstemを含む場合の両方向の部分文字列一致を許可する（版違いの
       ファイル群を広く拾うための既存設計。日本語には空白等の語境界が
       無いため、find_named_files同様に境界チェックをしない）。

    2文字以下のhint（例: term_registryの"R2"→"R2"、"RED"→"赤字"等の書式・統計
    用語）は、ファイル名の版数サフィックス（"_r2.xlsx"等の実データ命名慣習）との
    偶然一致リスクが高く、かつ文書種別を表さないため除外する。
    返り値はNFC正規化済みのbasenameで、known_namesの出現順を保つ（重複除去）。
    """
    normalized_hints = [
        unicodedata.normalize("NFC", h).casefold()
        for h in hints
        if h and len(h.strip()) >= 3
    ]
    if not normalized_hints:
        return []

    ordered_basenames: dict[str, str] = {}
    for name in known_names:
        basename_nfc = unicodedata.normalize("NFC", Path(str(name)).name)
        key = basename_nfc.casefold()
        if not key or key in ordered_basenames:
            continue
        ordered_basenames[key] = basename_nfc

    matched: list[str] = []
    for key, basename_nfc in ordered_basenames.items():
        stem = Path(basename_nfc).stem.casefold()
        if not stem:
            continue
        for hint in normalized_hints:
            if _HINT_EXTENSION_RE.search(hint):
                is_match = Path(hint).stem == stem
            elif _ASCII_ALNUM_RE.match(hint):
                is_match = _ascii_word_boundary_match(hint, stem)
            else:
                is_match = hint in stem or stem in hint
            if is_match:
                matched.append(basename_nfc)
                break
    return matched
