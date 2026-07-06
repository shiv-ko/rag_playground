"""Contract calculation and approval-rule tests."""
from __future__ import annotations

from pathlib import Path
import unicodedata

from src.generator.approval_rule import determine_apr_level
from src.generator.contract_calc import ContractCalcAnswerer, billed_amount_incl_tax, parse_hours
from src.structured.artifact_store import StructuredArtifactStore


def _store(rows: list[dict]) -> StructuredArtifactStore:
    by_project: dict[str, list[dict]] = {}
    for row in rows:
        by_project.setdefault(row["project_name"], []).append(row)
    return StructuredArtifactStore({"contracts": by_project})


def _tm(project: str = "医療法人社団 蒼泉会 ひがし丘総合病院") -> dict:
    return {
        "project_name": project,
        "status": "ok",
        "contract_type": "time_and_materials",
        "rate_yen_per_hour": 25000,
        "esth_hours": 170.0,
        "estimated_amount_incl_tax": 4675000,
        "tax_rate": 0.10,
        "rounding_unit_minutes": 30,
        "rounding_rule": "ceiling_to_unit",
        "start_date": "2025-07-08",
        "end_date": "2025-08-11",
        "actual_hours": 155.5,
    }


def test_determine_apr_level_applies_medical_and_tm_minimum() -> None:
    assert determine_apr_level(4_620_000, False, False) == "APR-M1"
    assert determine_apr_level(4_675_000, True, True) == "APR-M2"
    assert determine_apr_level(5_775_000, True, False) == "APR-M3"
    assert determine_apr_level(3_300_000, False, True) == "APR-M2"


def test_billed_amount_rounds_to_half_hour_ceiling() -> None:
    assert billed_amount_incl_tax(_tm(), 155 + 10 / 60) == 4_276_250


def test_parse_hours_accepts_japanese_and_acth_tokens() -> None:
    assert parse_hours("ACTH=155h10mだった場合") == 155 + 10 / 60
    assert parse_hours("155時間10分だった場合") == 155 + 10 / 60


def test_answer_amount_difference_from_estimate() -> None:
    answerer = ContractCalcAnswerer()
    answer = answerer.answer(
        "ひがし丘のACTH=155h10mなら見込税込と比べて何円減額ですか。",
        "医療法人社団 蒼泉会 ひがし丘総合病院",
        _store([_tm()]),
    )
    assert not answer.was_gated
    assert answer.text == "398,750円減額"


def test_answer_final_difference_from_report_value() -> None:
    row = _tm()
    row["final_amount_incl_tax"] = 4_276_250
    answer = ContractCalcAnswerer().answer(
        "ひがし丘の見込税込金額と最終請求金額の差額はいくらですか。",
        "医療法人社団 蒼泉会 ひがし丘総合病院",
        _store([row]),
    )
    assert not answer.was_gated
    assert answer.text == "398,750円減額"


def test_answer_derived_hourly_rate_from_amount_and_hour_gap() -> None:
    row = _tm()
    row["estimated_amount_incl_tax"] = 3_740_000
    row["final_amount_incl_tax"] = 3_443_000
    row["esth_hours"] = 170.0
    row["actual_hours"] = 156.5
    answer = ContractCalcAnswerer().answer(
        "見込税込-確定税込をESTH-ACTHの差で割った時間単価はいくらですか。",
        "医療法人社団 蒼泉会 ひがし丘総合病院",
        _store([row]),
    )
    assert not answer.was_gated
    assert answer.text == "22,000円"


def test_answer_apr_m3_list_and_total_uses_primary_aliases() -> None:
    rows = [
        _tm("医療法人社団 蒼泉会 ひがし丘総合病院"),
        {
            "project_name": "白峰信用リスク評価株式会社",
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 7480000,
        },
        {
            "project_name": "青葉与信マネジメント株式会社",
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 4620000,
        },
    ]
    answerer = ContractCalcAnswerer()
    answer = answerer.answer(
        "APR-M3必要案件を主略称ですべて挙げ契約金額合計を答えてください。",
        None,
        _store(rows),
        {"医療法人社団 蒼泉会 ひがし丘総合病院": "SOHK", "白峰信用リスク評価株式会社": "SHIRAMINE"},
        {},
    )
    assert not answer.was_gated
    assert answer.text == "SHIRAMINE、合計7,480,000円"


def test_primary_alias_lookup_normalizes_nfd_keys() -> None:
    project = "白峰信用リスク評価株式会社"
    answer = ContractCalcAnswerer().answer(
        "APR-M3必要案件を主略称ですべて挙げ契約金額合計を答えてください。",
        None,
        _store([{
            "project_name": project,
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 7480000,
        }]),
        {unicodedata.normalize("NFD", project): "SHIRAMINE"},
        {},
    )
    assert not answer.was_gated
    assert answer.text == "SHIRAMINE、合計7,480,000円"


def test_fixed_per_row_uses_project_train_csv(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    nfd_project = unicodedata.normalize("NFD", "固定社")
    (data_dir / nfd_project / "03.データ").mkdir(parents=True)
    (data_dir / nfd_project / "03.データ" / "train.csv").write_text("a\n1\n2\n", encoding="utf-8")
    answerer = ContractCalcAnswerer(data_dir=data_dir)
    answer = answerer.answer(
        "固定金額契約中、分析データ1行あたり契約金額最高の案件はどれですか。",
        None,
        _store([{
            "project_name": "固定社",
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 1000,
        }]),
    )
    assert not answer.was_gated
    assert answer.text == "固定社"
