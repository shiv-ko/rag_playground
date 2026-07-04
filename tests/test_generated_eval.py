"""artifact由来の擬似評価セット生成テスト。"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.build_generated_eval import build_questions, main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")


def test_build_questions_from_artifacts(tmp_path: Path) -> None:
    (tmp_path / "project_registry.json").write_text(
        json.dumps([{"project_name": "A社", "aliases": ["AAA"]}], ensure_ascii=False),
        encoding="utf-8",
    )
    _write_jsonl(tmp_path / "schedule_tasks.jsonl", [
        {"project_name": "A社", "source_path": "x/schedule.xlsx",
         "values": {"タスクID": "T01", "フェーズ名": "探索", "担当者": "山田 太郎"}},
        {"project_name": "A社", "source_path": "x/schedule.xlsx",
         "values": {"タスクID": "T02", "フェーズ名": "探索", "担当者": "佐藤 花子"}},
    ])
    _write_jsonl(tmp_path / "train_xlsx_sheets.jsonl", [
        {"project_name": "A社", "source_path": "x/train.xlsx",
         "filter_columns": [{"header": "gender", "values": ["Male"]}]},
    ])
    _write_jsonl(tmp_path / "train_xlsx_highlight_blocks.jsonl", [
        {"project_name": "A社", "source_path": "x/train.xlsx",
         "fill_color_name": "yellow", "range": "A1", "first_value": "123"},
    ])
    _write_jsonl(tmp_path / "office_marks.jsonl", [
        {"project_name": "A社", "source_path": "x/doc.docx", "file_name": "doc.docx",
         "text": "重要語", "bold": True},
    ])

    questions = build_questions(tmp_path, per_type=10)
    assert {q.type for q in questions} >= {
        "schedule_フェーズ名",
        "spreadsheet_filter_condition",
        "spreadsheet_highlight_value",
        "office_style_太字",
    }
    assert any(q.answer == "T01、T02" for q in questions)
    assert all(q.id.startswith("gen_") for q in questions)


def test_main_writes_separate_generated_eval_files(tmp_path: Path, monkeypatch) -> None:
    artifacts = tmp_path / "artifacts"
    out = tmp_path / "generated_eval"
    artifacts.mkdir()
    (artifacts / "project_registry.json").write_text("[]", encoding="utf-8")
    _write_jsonl(artifacts / "train_xlsx_sheets.jsonl", [
        {"project_name": "A社", "source_path": "x/train.xlsx",
         "filter_columns": [{"header": "x", "values": ["1"]}]},
    ])
    monkeypatch.setattr("sys.argv", [
        "build_generated_eval.py", "--artifacts-dir", str(artifacts), "--out-dir", str(out)
    ])
    main()
    assert (out / "questions.json").exists()
    assert (out / "metadata.jsonl").exists()
