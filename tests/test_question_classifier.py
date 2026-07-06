"""質問文の要求能力タグ分類のテスト。"""
from __future__ import annotations

from src.utils.question_classifier import classify_question


def test_detects_image_or_graph_question() -> None:
    q = "figure_06.pngにおいて、dayによる件数推移を教えてください。"
    assert "image_or_graph" in classify_question(q)


def test_detects_version_diff_question() -> None:
    q = "提案書old.pptxから提案書.pptxへの更新内容のうち、実質的な変更を挙げてください。"
    assert "version_diff" in classify_question(q)


def test_detects_password_protected_question() -> None:
    q = "契約書のパスワードを教えてください。"
    assert "password_protected" in classify_question(q)


def test_detects_multi_hop_question() -> None:
    q = "すべての案件のうち、契約金額が最大のものはどれですか。"
    assert "multi_hop" in classify_question(q)


def test_plain_question_is_text_only() -> None:
    q = "宿泊費の上限はいくらですか。"
    assert classify_question(q) == ["text_only"]


def test_question_can_have_multiple_tags() -> None:
    q = "old版のfigure_06.pngとの差分を教えてください。"
    tags = classify_question(q)
    assert "image_or_graph" in tags
    assert "version_diff" in tags


def test_detects_version_diff_question_phrased_as_modified_into() -> None:
    q = "提案書_v1.pptxから提案書_v3.pptxに修正されたもののうち、案件遂行に関連する変更を挙げてください。"
    assert "version_diff" in classify_question(q)


def test_detects_version_diff_question_phrased_as_compared_when() -> None:
    q = "スケジュール_r1.xlsxとスケジュール_r2.xlsxを比較したとき、案件遂行に関連する変更点を挙げてください。"
    assert "version_diff" in classify_question(q)


def test_detects_spreadsheet_state_question() -> None:
    assert "spreadsheet_state" in classify_question(
        "東都人材プラットフォームのtrain.xlsxにおいて、trainシートでフィルターで抽出されている条件を教えてください。"
    )
    assert "spreadsheet_state" in classify_question(
        "AOSHIOのM02資料（docx）において、黄色でハイライトされている部分をすべて抜き出してください。"
    )
    assert "spreadsheet_state" in classify_question(
        "青葉与信マネジメントのPLにおいて、探索的分析・仮説整理フェーズに一致するタスクIDをすべて挙げてください。"
    )


def test_detects_office_style_question() -> None:
    assert "office_style" in classify_question(
        "恒一会 かえで総合病院の契約書において、太字で記載されている箇所のうち、日付以外のものをすべて抽出してください。"
    )
    assert "office_style" in classify_question(
        "東都人材プラットフォームの提案書P7において、赤で強調されている箇所の文字列を抜き出してください。"
    )


def test_office_marker_phrase_does_not_trigger_image_tag() -> None:
    tags = classify_question(
        "最終報告における、要因分析のページで、マーカーされている単語をすべて抜き出してください。"
    )
    assert "office_style" in tags
    assert "image_or_graph" not in tags


def test_true_marker_graph_context_keeps_image_tag() -> None:
    tags = classify_question("折れ線グラフのマーカーの色は何ですか。")
    assert "image_or_graph" in tags


def test_pure_image_questions_keep_image_tag() -> None:
    assert "image_or_graph" in classify_question("このグラフの色は何ですか。")
    assert "image_or_graph" in classify_question("画像に写っているものは何ですか。")


def test_detects_spreadsheet_calc_question() -> None:
    assert "spreadsheet_calc" in classify_question(
        "青葉与信マネジメントの分析対象データにおいて、term=3 years、grade=B1、purpose=credit_cardに該当するloan_amntの平均を算出してください。四捨五入して整数値で出してください。"
    )
    assert "spreadsheet_calc" in classify_question(
        "恒一会 かえで総合病院のプロジェクトデータ（train.csv）において、disease=1の女性の中で、ALT_GPTの平均値が最も高い年齢は何歳ですか。"
    )


def test_question_can_have_both_spreadsheet_state_and_highlight_style_tags() -> None:
    tags = classify_question("提案書.pptxで黄色ハイライトされている数値を抜き出してください。")
    assert "office_style" in tags


def test_generic_phrases_alone_do_not_trigger_spreadsheet_calc():
    """「の中で」「該当する」は一般文に頻出するため、単独ではcalcタグを付けない。"""
    assert "spreadsheet_calc" not in classify_question(
        "定例会議の出席者の中で議事録に記載されている決定事項を教えてください。"
    )
    assert "spreadsheet_calc" not in classify_question(
        "この条件に該当する契約条項を教えてください。"
    )
