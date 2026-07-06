"""contracts.jsonl extraction tests."""
from __future__ import annotations

from scripts.build_contract_registry import classify_rounding_rule, parse_contract_text


def test_parse_time_and_materials_contract_values() -> None:
    text = """
5. 契約期間
本契約の契約期間は、2025-07-08から2025-08-11までの5週間とする。
6. 報酬および支払条件
本契約の料金モデルは、time_and_materialsとし、実績工数に基づく事後精算（月次精算）とする。
時間単価は25,000円（消費税別）とする。
想定総工数は170時間とする。
見込金額は、税抜4,250,000円、消費税425,000円、税込4,675,000円とする。
作業時間の計上単位は30分とし、30分未満の端数は30分単位に切り上げて計上する。
7. 知的財産
"""
    row = parse_contract_text("テスト社", "契約書.docx", text)
    assert row["contract_type"] == "time_and_materials"
    assert row["rate_yen_per_hour"] == 25000
    assert row["esth_hours"] == 170
    assert row["estimated_amount_incl_tax"] == 4675000
    assert row["rounding_rule"] == "ceiling_to_unit"
    assert row["contract_period_days"] == 35


def test_parse_fixed_contract_values() -> None:
    text = """
5. 契約期間
本契約の契約期間は、2025-10-01から2025-11-11までの6週間とする。
6. 報酬および支払条件
本契約の契約形態は固定価格契約とし、契約金額（税抜）：5,250,000円、
消費税額：525,000円、契約金額（税込）：5,775,000円とする。
支払計画: 着手金50%（期日: 2025-10-08）＋ 検収金50%。
"""
    row = parse_contract_text("固定社", "契約書.docx", text)
    assert row["contract_type"] == "fixed"
    assert row["estimated_amount_incl_tax"] == 5775000
    assert row["advance_payment_amount"] == 2887500


def test_classify_half_unit_bucket_rounding() -> None:
    clause = "工数計上の丸め単位は30分とし、30分未満を0.5時間、30分超60分未満を1.0時間として0.5時間単位で計上する。"
    assert classify_rounding_rule(clause) == "half_unit_bucket"


def test_parse_advance_payment_from_docx_table_row_with_percent_column() -> None:
    # 実データの表形式（京橋信用ソリューションズと同じ列順）:
    # 支払回 | 名目 | 比率 | 金額（税抜） | 消費税額 | 金額（税込） | 支払条件 | 支払期日
    text = """
6. 報酬および支払条件
6.1 契約金額
本契約の契約形態は固定価格契約とし、契約金額（税抜）：5,250,000円、
消費税額：525,000円、契約金額（税込）：5,775,000円とする。
6.2 支払条件
支払回 | 名目 | 比率 | 金額（税抜） | 消費税額 | 金額（税込） | 支払条件 | 支払期日
第1回 | 着手金 | 50% | 2,625,000円 | 262,500円 | 2,887,500円 | 契約締結後5営業日以内 | 2025-10-08
第2回 | 検収金 | 50% | 2,625,000円 | 262,500円 | 2,887,500円 | 検収完了後5営業日以内 | 2025-11-19
"""
    row = parse_contract_text("京橋風", "契約書.docx", text)
    assert row["advance_payment_amount"] == 2_887_500


def test_parse_advance_payment_from_docx_table_row_with_different_column_order() -> None:
    # 実データの表形式（青葉与信マネジメントと同じ列順、支払条件が税抜より前に来る）:
    # 支払回 | 支払名目 | 比率 | 支払条件 | 税抜金額 | 消費税額 | 税込金額 | 支払期日
    text = """
6. 報酬および支払条件
本契約の契約形態は固定価格とし、契約時に金額を固定し、工数実績による事後精算は行わない。
本契約の報酬総額は、税抜4,200,000円、消費税420,000円、税込4,620,000円とする。
支払回 | 支払名目 | 比率 | 支払条件 | 税抜金額 | 消費税額 | 税込金額 | 支払期日
1 | 着手金 | 50% | 契約締結後5営業日以内 | 2,100,000円 | 210,000円 | 2,310,000円 | 2025-04-16
2 | 検収金 | 50% | 検収完了後5営業日以内 | 2,100,000円 | 210,000円 | 2,310,000円 | 2025-06-04
"""
    row = parse_contract_text("青葉与信風", "契約書.docx", text)
    assert row["advance_payment_amount"] == 2_310_000
