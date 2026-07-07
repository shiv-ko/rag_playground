"""StructuredArtifactStore のテスト。"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from src.structured.artifact_store import StructuredArtifactStore


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")


def test_loads_and_filters_highlight_cells(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "highlight_cells.jsonl", [
        {"project_name": "A社", "cell": "A1", "fill_color_name": "yellow"},
        {"project_name": "B社", "cell": "B1", "fill_color_name": "white"},
    ])
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    rows = store.highlight_cells_for("A社")
    assert len(rows) == 1
    assert rows[0]["cell"] == "A1"


def test_missing_artifact_file_returns_empty_list(tmp_path: Path) -> None:
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    assert store.highlight_cells_for("A社") == []
    assert store.schedule_tasks_for("A社") == []
    assert store.office_marks_for("A社") == []
    assert store.train_xlsx_highlight_blocks_for("A社") == []
    assert store.train_xlsx_sheets_for("A社") == []
    assert store.spreadsheet_sheets_for("A社") == []
    assert store.pivot_aggregates_for("A社") == []
    assert store.version_diff_pairs_for("A社") == []


def test_unknown_project_returns_empty_list(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "schedule_tasks.jsonl", [
        {"project_name": "A社", "values": {"タスクID": "T01"}},
    ])
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    assert store.schedule_tasks_for("存在しない案件") == []


def test_project_lookup_normalizes_unicode(tmp_path: Path) -> None:
    nfd_name = unicodedata.normalize("NFD", "京橋信用ソリューションズ株式会社")
    _write_jsonl(tmp_path / "schedule_tasks.jsonl", [
        {"project_name": nfd_name, "values": {"タスクID": "T01"}},
    ])
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    rows = store.schedule_tasks_for("京橋信用ソリューションズ株式会社")
    assert rows[0]["values"]["タスクID"] == "T01"


def test_all_artifact_kinds_load_from_their_own_files(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "schedule_tasks.jsonl", [{"project_name": "A社", "x": 1}])
    _write_jsonl(tmp_path / "office_marks.jsonl", [{"project_name": "A社", "x": 2}])
    _write_jsonl(tmp_path / "train_xlsx_highlight_blocks.jsonl", [{"project_name": "A社", "x": 3}])
    _write_jsonl(tmp_path / "train_xlsx_sheets.jsonl", [{"project_name": "A社", "x": 4}])
    _write_jsonl(tmp_path / "spreadsheet_sheets.jsonl", [{"project_name": "A社", "x": 5}])
    _write_jsonl(tmp_path / "train_xlsx_pivot_aggregates.jsonl", [{"project_name": "A社", "x": 6}])
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    assert store.schedule_tasks_for("A社")[0]["x"] == 1
    assert store.office_marks_for("A社")[0]["x"] == 2
    assert store.train_xlsx_highlight_blocks_for("A社")[0]["x"] == 3
    assert store.train_xlsx_sheets_for("A社")[0]["x"] == 4
    assert store.spreadsheet_sheets_for("A社")[0]["x"] == 5
    assert store.pivot_aggregates_for("A社")[0]["x"] == 6


def test_pivot_aggregates_lookup_normalizes_unicode(tmp_path: Path) -> None:
    nfd_name = unicodedata.normalize("NFD", "京橋信用ソリューションズ株式会社")
    _write_jsonl(tmp_path / "train_xlsx_pivot_aggregates.jsonl", [
        {"project_name": nfd_name, "data_field_source": "Sales"},
    ])
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    assert store.pivot_aggregates_for("京橋信用ソリューションズ株式会社")[0]["data_field_source"] == "Sales"


def test_project_lookup_is_unicode_normalization_insensitive(tmp_path: Path):
    """macOSのファイルパス由来のNFD案件名とNFC案件名が混在しても引けること
    （project_name正規化ズレで構造化パスが全件空振りするのを防ぐ）。"""
    import unicodedata

    nfc_name = "青葉与信マネジメント株式会社"
    nfd_name = unicodedata.normalize("NFD", nfc_name)
    assert nfc_name != nfd_name  # 前提: 分解可能な文字を含む

    _write_jsonl(tmp_path / "schedule_tasks.jsonl", [
        {"project_name": nfd_name, "values": {"タスクID": "T01"}},
    ])
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    assert len(store.schedule_tasks_for(nfc_name)) == 1
    assert len(store.schedule_tasks_for(nfd_name)) == 1


def test_rows_with_null_project_name_do_not_crash(tmp_path: Path):
    _write_jsonl(tmp_path / "office_marks.jsonl", [
        {"project_name": None, "text": "x"},
        {"project_name": "A社", "text": "y"},
    ])
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    assert len(store.office_marks_for("A社")) == 1


def test_version_diff_pairs_loaded_and_filtered_by_project(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "version_diff_poc.jsonl", [
        {"project_name": "A社", "normalized_title": "提案書", "old_version_tag": "v1", "new_version_tag": "final"},
        {"project_name": "B社", "normalized_title": "提案書", "old_version_tag": "old", "new_version_tag": None},
    ])
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    rows = store.version_diff_pairs_for("A社")
    assert len(rows) == 1
    assert rows[0]["old_version_tag"] == "v1"


def test_version_diff_pairs_lookup_normalizes_unicode(tmp_path: Path) -> None:
    nfd_name = unicodedata.normalize("NFD", "京橋信用ソリューションズ株式会社")
    _write_jsonl(tmp_path / "version_diff_poc.jsonl", [
        {"project_name": nfd_name, "normalized_title": "提案書"},
    ])
    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    assert len(store.version_diff_pairs_for("京橋信用ソリューションズ株式会社")) == 1


def test_project_names_deduplicates_nfc_nfd_variants(tmp_path: Path) -> None:
    """同一案件がNFCとNFDの両方の形式で複数レジストリに格納されている場合、
    project_names()は1件に統一して返すこと（重複排除）。

    実データでは、macOSファイルパス由来のNFDと、contracts.jsonlのNFC
    が混在しているため、回帰テストが必要。
    """
    nfc_name = "青葉与信マネジメント株式会社"
    nfd_name = unicodedata.normalize("NFD", nfc_name)
    assert nfc_name != nfd_name  # 前提: 分解可能な文字を含む

    # 同一案件がNFCとNFDで異なるレジストリに格納されるケースを再現
    _write_jsonl(tmp_path / "schedule_tasks.jsonl", [
        {"project_name": nfd_name, "values": {"タスクID": "T01"}},
    ])
    _write_jsonl(tmp_path / "contracts.jsonl", [
        {"project_name": nfc_name, "contract_id": "C001"},
    ])

    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)
    names = store.project_names()

    # 同一案件が1件にまとまっていることを確認
    assert len(names) == 1
    # かつ、返されたのはNFC正規化されたもの
    assert names[0] == nfc_name
