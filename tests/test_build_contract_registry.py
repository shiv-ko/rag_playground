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
