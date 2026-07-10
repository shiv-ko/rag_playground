"""Contract calculation and approval-rule tests."""
from __future__ import annotations

from pathlib import Path
import unicodedata

from src.generator.approval_rule import determine_apr_level
from src.generator.contract_calc import (
    ContractCalcAnswerer,
    billed_amount_incl_tax,
    paid_amount_incl_tax,
    parse_hours,
)
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


def _apr_m1_completed_row(
    project: str,
    n_rows: int,
    tmp_path: Path,
    final_amount: int | None = 4_000_000,
    has_final_report: bool = True,
) -> dict:
    # APR-M1: 3,000,000円以上5,000,000円未満（非医療・fixed）
    nfd_project = unicodedata.normalize("NFD", project)
    data_dir = tmp_path / nfd_project / "03.データ"
    data_dir.mkdir(parents=True, exist_ok=True)
    rows_text = "\n".join(["a"] + [str(i) for i in range(n_rows)]) + "\n"
    (data_dir / "train.csv").write_text(rows_text, encoding="utf-8")
    row: dict = {
        "project_name": project,
        "status": "ok",
        "contract_type": "fixed",
        "estimated_amount_incl_tax": 4_000_000,
        "has_final_report": has_final_report,
    }
    if final_amount is not None:
        row["final_amount_incl_tax"] = final_amount
    return row


def test_apr_m1_completed_row_threshold_returns_matching_project(tmp_path: Path) -> None:
    row = _apr_m1_completed_row("完了済APRM1社", 10_000, tmp_path)
    answerer = ContractCalcAnswerer(data_dir=tmp_path)
    answer = answerer.answer(
        "完了案件のうち、社内管理のAPRでAPR-M1に該当し、かつ顧客データのサンプル数が"
        "10000行以上の案件を、案件略称ですべて挙げてください。",
        None,
        _store([row]),
        {"完了済APRM1社": "DONEM1"},
        {},
    )
    assert not answer.was_gated
    assert answer.text == "DONEM1"


def test_apr_m1_completed_row_threshold_excludes_non_m1_level(tmp_path: Path) -> None:
    row = _apr_m1_completed_row("非M1社", 10_000, tmp_path)
    row["estimated_amount_incl_tax"] = 8_500_000  # APR-M3帯
    answerer = ContractCalcAnswerer(data_dir=tmp_path)
    answer = answerer.answer(
        "完了案件のうち、社内管理のAPRでAPR-M1に該当し、かつ顧客データのサンプル数が"
        "10000行以上の案件を、案件略称ですべて挙げてください。",
        None,
        _store([row]),
        {"非M1社": "NOTM1"},
        {},
    )
    assert answer.was_gated


def test_apr_m1_completed_row_threshold_excludes_row_count_under_threshold(tmp_path: Path) -> None:
    row = _apr_m1_completed_row("行数不足社", 9_999, tmp_path)
    answerer = ContractCalcAnswerer(data_dir=tmp_path)
    answer = answerer.answer(
        "完了案件のうち、社内管理のAPRでAPR-M1に該当し、かつ顧客データのサンプル数が"
        "10000行以上の案件を、案件略称ですべて挙げてください。",
        None,
        _store([row]),
        {"行数不足社": "SHORTROWS"},
        {},
    )
    assert answer.was_gated


def test_apr_m1_completed_row_threshold_excludes_unknown_completion_status(tmp_path: Path) -> None:
    # has_final_report（06.報告書配下にoldを除くファイルが存在するか）が偽＝完了未確定 → 対象外
    row = _apr_m1_completed_row("未完了社", 10_000, tmp_path, has_final_report=False)
    answerer = ContractCalcAnswerer(data_dir=tmp_path)
    answer = answerer.answer(
        "完了案件のうち、社内管理のAPRでAPR-M1に該当し、かつ顧客データのサンプル数が"
        "10000行以上の案件を、案件略称ですべて挙げてください。",
        None,
        _store([row]),
        {"未完了社": "UNKNOWNDONE"},
        {},
    )
    assert answer.was_gated


def test_apr_m1_completed_row_threshold_includes_fixed_price_without_final_amount_when_report_exists(
    tmp_path: Path,
) -> None:
    # 実データで判明したバグの回帰テスト（青葉与信/固定価格・APR-M1該当）:
    # 固定価格契約は最終報告書で金額を再掲しない/言い回しが違うため
    # final_amount_incl_taxは常にnullになるが、報告ファイル自体は提出済み
    # （has_final_report=True）なら完了案件として扱うべき。
    row = _apr_m1_completed_row(
        "固定価格完了社", 10_000, tmp_path, final_amount=None, has_final_report=True
    )
    answerer = ContractCalcAnswerer(data_dir=tmp_path)
    answer = answerer.answer(
        "完了案件のうち、社内管理のAPRでAPR-M1に該当し、かつ顧客データのサンプル数が"
        "10000行以上の案件を、案件略称ですべて挙げてください。",
        None,
        _store([row]),
        {"固定価格完了社": "FIXEDDONE"},
        {},
    )
    assert not answer.was_gated
    assert answer.text == "FIXEDDONE"


def test_apr_m1_completed_row_threshold_missing_when_no_matches_at_all() -> None:
    answerer = ContractCalcAnswerer()
    answer = answerer.answer(
        "完了案件のうち、社内管理のAPRでAPR-M1に該当し、かつ顧客データのサンプル数が"
        "10000行以上の案件を、案件略称ですべて挙げてください。",
        None,
        _store([]),
        {},
        {},
    )
    assert answer.was_gated


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


# --- paid_amount_incl_tax / 全案件消費税総額（Q3型） ---


def test_paid_amount_incl_tax_uses_estimated_for_fixed_contract() -> None:
    contract = {"contract_type": "fixed", "estimated_amount_incl_tax": 5_775_000}
    assert paid_amount_incl_tax(contract) == 5_775_000


def test_paid_amount_incl_tax_prefers_final_amount_for_tm_contract() -> None:
    contract = {
        "contract_type": "time_and_materials",
        "estimated_amount_incl_tax": 4_675_000,
        "final_amount_incl_tax": 3_850_000,
    }
    assert paid_amount_incl_tax(contract) == 3_850_000


def test_paid_amount_incl_tax_falls_back_to_billed_amount_when_no_final_amount() -> None:
    contract = _tm("株式会社青嶺不動産アセットマネジメント")
    contract["actual_hours"] = 184.5
    # final_amount_incl_taxが無い場合はbilled_amount_incl_taxで計算（既存関数を再利用）
    assert paid_amount_incl_tax(contract) == billed_amount_incl_tax(contract, 184.5)


def test_paid_amount_incl_tax_none_when_tm_contract_missing_all_sources() -> None:
    # 青潮のように実績工数・最終請求額のいずれも取れないケース(OCR未実装で解決不能)
    contract = {"contract_type": "time_and_materials", "estimated_amount_incl_tax": 4_000_000}
    assert paid_amount_incl_tax(contract) is None


def test_answer_tax_total_sums_across_all_contracts_at_uniform_tax_rate() -> None:
    # 実データ(plan §1.1)の京橋(固定・estimated)とかえで(T&M・final)の2件を模した合成値。
    rows = [
        {
            "project_name": "京橋風",
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 5_775_000,
            "tax_rate": 0.10,
        },
        {
            "project_name": "かえで風",
            "status": "ok",
            "contract_type": "time_and_materials",
            "estimated_amount_incl_tax": 4_675_000,
            "final_amount_incl_tax": 3_850_000,
            "tax_rate": 0.10,
        },
    ]
    answer = ContractCalcAnswerer().answer(
        "全案件で支払った税込金額をもとに、消費税額の総額を計算してください。",
        None,
        _store(rows),
    )
    assert not answer.was_gated
    assert answer.text == "875,000円"


def test_answer_tax_total_missing_when_any_contract_unresolvable() -> None:
    # 1件でもpaid_amount_incl_taxがNoneならMissineへフォールバック（正答化より安全化優先）
    rows = [
        {
            "project_name": "京橋風",
            "status": "ok",
            "contract_type": "fixed",
            "estimated_amount_incl_tax": 5_775_000,
            "tax_rate": 0.10,
        },
        {
            "project_name": "青潮風",
            "status": "ok",
            "contract_type": "time_and_materials",
            "estimated_amount_incl_tax": 4_000_000,
            "tax_rate": 0.10,
            # final_amount_incl_taxもactual_hoursも無い＝算出不能
        },
    ]
    answer = ContractCalcAnswerer().answer(
        "全案件で支払った税込金額をもとに、消費税額の総額を計算してください。",
        None,
        _store(rows),
    )
    assert answer.was_gated


def test_answer_tax_total_missing_when_no_contracts() -> None:
    answer = ContractCalcAnswerer().answer(
        "全案件で支払った税込金額をもとに、消費税額の総額を計算してください。",
        None,
        _store([]),
    )
    assert answer.was_gated
