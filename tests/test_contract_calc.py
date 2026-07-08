"""Contract calculation and approval-rule tests."""
from __future__ import annotations

from pathlib import Path
import unicodedata

from src.generator.approval_rule import determine_apr_level
from src.generator.contract_calc import ContractCalcAnswerer, billed_amount_incl_tax, parse_hours
from src.structured.artifact_store import StructuredArtifactStore
from src.utils.question_classifier import classify_question


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


def test_determine_apr_level_normal_bracket_boundaries() -> None:
    # 社内管理_決裁基準.md: 5,000,000円以上8,000,000円未満は部長承認(APR-M2)、
    # 8,000,000円以上で初めて本部長承認(APR-M3)。7,480,000円は部長承認のまま。
    assert determine_apr_level(7_480_000, False, False) == "APR-M2"
    assert determine_apr_level(7_999_999, False, False) == "APR-M2"
    assert determine_apr_level(8_000_000, False, False) == "APR-M3"


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
    # 実データのQ37の文言そのもの（「時間単価」という語は含まれず「1時間あたり」表記）
    row = _tm("株式会社青葉バイオメディカル機器")
    row["estimated_amount_incl_tax"] = 3_740_000
    row["final_amount_incl_tax"] = 3_443_000
    row["esth_hours"] = 170.0
    row["actual_hours"] = 156.5
    answer = ContractCalcAnswerer().answer(
        "AOBMにおいて、見込金額（税込）と確定金額（税込）の差を、ESTHとACTHの差で"
        "割った1時間あたりの減少金額を計算してください。",
        "株式会社青葉バイオメディカル機器",
        _store([row]),
    )
    assert not answer.was_gated
    assert answer.text == "22,000円"


def test_answer_rate_and_hour_delta_from_actual_billed_amount() -> None:
    # 実データのQ76の文言そのもの（"ACTH-11.2h"/"+2000"のような記法ではなく自然文）。
    # 基準は見込(ESTH/見込金額)ではなく「実際の税込請求金額」＝実績工数(ACTH)ベース。
    row = _tm("株式会社青嶺不動産アセットマネジメント")
    row["actual_hours"] = 184.5
    answer = ContractCalcAnswerer().answer(
        "AOMINEの契約条件において、契約単価が現状よりも2,000円高く、実績工数が"
        "11.2時間少なかった場合、税込請求金額は、実際の税込請求金額と比べて"
        "いくら変動しますか。",
        "株式会社青嶺不動産アセットマネジメント",
        _store([row]),
    )
    assert not answer.was_gated
    assert answer.text == "79,200円増額"


def test_answer_apr_m3_list_and_total_uses_primary_aliases() -> None:
    rows = [
        _tm("医療法人社団 蒼泉会 ひがし丘総合病院"),
        {
            # 7,480,000円は決裁基準上まだ部長承認(APR-M2)であり、APR-M3ではない
            # (7,000,000円を閾値にすると誤ってAPR-M3扱いになるリグレッションガード)
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
        {
            "project_name": "本部長承認案件株式会社",
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 8500000,
        },
    ]
    answerer = ContractCalcAnswerer()
    answer = answerer.answer(
        "APR-M3必要案件を主略称ですべて挙げ契約金額合計を答えてください。",
        None,
        _store(rows),
        {
            "医療法人社団 蒼泉会 ひがし丘総合病院": "SOHK",
            "白峰信用リスク評価株式会社": "SHIRAMINE",
            "本部長承認案件株式会社": "HONBU",
        },
        {},
    )
    assert not answer.was_gated
    assert answer.text == "HONBU、合計8,500,000円"


def test_primary_alias_lookup_normalizes_nfd_keys() -> None:
    project = "白峰信用リスク評価株式会社"
    answer = ContractCalcAnswerer().answer(
        "APR-M3必要案件を主略称ですべて挙げ契約金額合計を答えてください。",
        None,
        _store([{
            "project_name": project,
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 8500000,
        }]),
        {unicodedata.normalize("NFD", project): "SHIRAMINE"},
        {},
    )
    assert not answer.was_gated
    assert answer.text == "SHIRAMINE、合計8,500,000円"


def test_answer_overlap_parses_iso_dates_and_uses_own_period_length() -> None:
    # 実データのQ26の文言そのもの（"2025年8月15日"ではなくISO形式"2025-08-15"）。
    # 「契約期間が重なっている」＝指定期間との重複有無、「契約期間が40日を超えている」＝
    # 案件自体の契約期間の長さ、という別々の条件（重複期間の長さが40日超、ではない）。
    rows = [
        {
            # 指定期間と重複し、契約期間自体も40日超 → 該当
            "project_name": "重複かつ長期契約株式会社",
            "status": "ok",
            "start_date": "2025-08-20",
            "end_date": "2025-10-10",
            "contract_period_days": 52,
        },
        {
            # 指定期間と重複するが契約期間自体は40日以下 → 非該当
            "project_name": "重複だが短期契約株式会社",
            "status": "ok",
            "start_date": "2025-08-25",
            "end_date": "2025-09-01",
            "contract_period_days": 8,
        },
        {
            # 契約期間は40日超だが指定期間と重複しない → 非該当
            "project_name": "長期だが重複なし株式会社",
            "status": "ok",
            "start_date": "2025-01-01",
            "end_date": "2025-03-01",
            "contract_period_days": 60,
        },
    ]
    answer = ContractCalcAnswerer().answer(
        "2025-08-15 から 2025-09-07 の間に契約期間が重なっている案件の中で、"
        "契約期間が 40日 を超えている案件を、主略称ですべて挙げてください。",
        None,
        _store(rows),
        {
            "重複かつ長期契約株式会社": "MATCH",
            "重複だが短期契約株式会社": "SHORT",
            "長期だが重複なし株式会社": "NOOVERLAP",
        },
        {},
    )
    assert not answer.was_gated
    assert answer.text == "MATCH"


def test_fixed_per_row_uses_project_train_csv(tmp_path: Path) -> None:
    # 実データのQ31は「主略称と1行あたりの金額」の両方、かつ金額は円単位切り上げを要求する
    data_dir = tmp_path / "data"
    nfd_project = unicodedata.normalize("NFD", "固定社")
    (data_dir / nfd_project / "03.データ").mkdir(parents=True)
    (data_dir / nfd_project / "03.データ" / "train.csv").write_text("a\n1\n2\n3\n", encoding="utf-8")
    answerer = ContractCalcAnswerer(data_dir=data_dir)
    answer = answerer.answer(
        "固定金額契約の中で、分析データ1行あたりの契約金額（税込）が最も高い案件を、"
        "主略称と1行あたりの金額で答えてください。1行あたりの金額は円単位で切り上げてください。",
        None,
        _store([{
            "project_name": "固定社",
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 1000,
        }]),
    )
    assert not answer.was_gated
    # 1000円 / 3行 = 333.33... 円単位で切り上げ → 334円
    assert answer.text == "固定社、334円"


def _write_train_csv(data_dir: Path, project: str, n_rows: int) -> None:
    proj_dir = data_dir / project / "03.データ"
    proj_dir.mkdir(parents=True)
    content = "a\n" + "\n".join(str(i) for i in range(n_rows)) + "\n"
    (proj_dir / "train.csv").write_text(content, encoding="utf-8")


def test_q87_style_question_gets_contract_rule_tag() -> None:
    # Q87型の実際の文言そのもの。src側にこの文言をハードコードしていないことを、
    # ここでのみ使用することで担保する（ルーティングは汎用キーワード条件）。
    question = (
        "完了案件のうち、社内管理のAPRでAPR-M1に該当し、かつ顧客データのサンプル数が"
        "10000行以上の案件を、案件略称ですべて挙げてください。"
    )
    assert "contract_rule" in classify_question(question)


def test_answer_apr_row_threshold_list_filters_completed_apr_and_sample_size(tmp_path: Path) -> None:
    # 該当2件のうち、行数不足1件・未完了1件・APRレベル違い1件がそれぞれ別理由で除外される
    # ことを確認する判別テスト。
    data_dir = tmp_path / "data"
    _write_train_csv(data_dir, "APR一致完了大量株式会社", 10500)
    _write_train_csv(data_dir, "APR一致完了少量株式会社", 200)
    _write_train_csv(data_dir, "APR一致未完了株式会社", 10500)
    _write_train_csv(data_dir, "APRレベル違い完了大量株式会社", 10500)

    rows = [
        {
            "project_name": "APR一致完了大量株式会社",
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 4_000_000,
            "final_amount_incl_tax": 3_900_000,
        },
        {
            # 行数不足（200行 < 10000行）で除外
            "project_name": "APR一致完了少量株式会社",
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 4_000_000,
            "final_amount_incl_tax": 3_900_000,
        },
        {
            # 報告書由来フィールドが無く未完了扱いのため除外
            "project_name": "APR一致未完了株式会社",
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 4_000_000,
        },
        {
            # 600万円はAPR-M2（APR-M1ではない）のため除外
            "project_name": "APRレベル違い完了大量株式会社",
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 6_000_000,
            "final_amount_incl_tax": 5_900_000,
        },
    ]
    answerer = ContractCalcAnswerer(data_dir=data_dir)
    answer = answerer.answer(
        "完了案件のうち、社内管理のAPRでAPR-M1に該当し、かつ顧客データのサンプル数が"
        "10000行以上の案件を、案件略称ですべて挙げてください。",
        None,
        _store(rows),
        {
            "APR一致完了大量株式会社": "MATCH",
            "APR一致完了少量株式会社": "SMALL",
            "APR一致未完了株式会社": "INCOMPLETE",
            "APRレベル違い完了大量株式会社": "WRONGLEVEL",
        },
        {},
    )
    assert not answer.was_gated
    assert answer.text == "MATCH"


def test_answer_apr_row_threshold_list_no_matches_returns_missing(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_train_csv(data_dir, "APR一致完了少量株式会社", 2)
    rows = [{
        "project_name": "APR一致完了少量株式会社",
        "status": "ok",
        "contract_type": "fixed",
        "estimated_amount_incl_tax": 4_000_000,
        "final_amount_incl_tax": 3_900_000,
    }]
    answerer = ContractCalcAnswerer(data_dir=data_dir)
    answer = answerer.answer(
        "完了案件のうち、社内管理のAPRでAPR-M1に該当し、かつ顧客データのサンプル数が"
        "10000行以上の案件を、案件略称ですべて挙げてください。",
        None,
        _store(rows),
        {},
        {},
    )
    assert answer.was_gated


def test_answer_apr_row_threshold_list_missing_threshold_returns_missing() -> None:
    # 「行以上」のようなしきい値パターンが無ければパース不能としてMissingになる
    answerer = ContractCalcAnswerer()
    answer = answerer._answer_apr_row_threshold_list(
        "完了案件のうちAPR-M1に該当する案件を挙げてください。",
        _store([]),
        {},
        {},
    )
    assert answer.was_gated


def test_answer_apr_row_threshold_list_missing_level_returns_missing() -> None:
    # APRレベルのパターンが無ければパース不能としてMissingになる
    answerer = ContractCalcAnswerer()
    answer = answerer._answer_apr_row_threshold_list(
        "顧客データのサンプル数が10000行以上の案件を挙げてください。",
        _store([]),
        {},
        {},
    )
    assert answer.was_gated


def test_answer_apr_row_threshold_list_supports_other_level_and_threshold(tmp_path: Path) -> None:
    # レベル・しきい値が異なる別パターンでも汎用的にパースできることを確認する
    data_dir = tmp_path / "data"
    _write_train_csv(data_dir, "M2一致完了株式会社", 600)
    rows = [{
        "project_name": "M2一致完了株式会社",
        "status": "ok",
        "contract_type": "fixed",
        "estimated_amount_incl_tax": 6_000_000,
        "actual_hours": 100.0,
    }]
    answerer = ContractCalcAnswerer(data_dir=data_dir)
    answer = answerer.answer(
        "完了案件のうち、APR-M2に該当し、かつサンプル数が500行以上の案件を、案件略称ですべて挙げてください。",
        None,
        _store(rows),
        {"M2一致完了株式会社": "M2ALIAS"},
        {},
    )
    assert not answer.was_gated
    assert answer.text == "M2ALIAS"
