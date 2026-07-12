from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from src.structured.analysis_artifacts import build_analysis_records, write_analysis_records
from src.structured.artifact_store import StructuredArtifactStore


def _analysis_dir(root: Path, project: str) -> Path:
    path = root / unicodedata.normalize("NFD", "プロジェクト") / project / "04.分析"
    path.mkdir(parents=True)
    return path


def test_json_records_normalize_project_and_preserve_paths(tmp_path: Path) -> None:
    project = unicodedata.normalize("NFD", "京橋信用ソリューションズ株式会社")
    analysis = _analysis_dir(tmp_path, project)
    (analysis / "metrics.json").write_text('{"score": 0.9}', encoding="utf-8")
    (analysis / "project" / "config").mkdir(parents=True)
    (analysis / "project" / "config" / "project_config.json").write_text(
        '{"target": "y"}', encoding="utf-8"
    )
    (analysis / "project" / "metrics.json").write_text('{"score": 0.8}', encoding="utf-8")

    rows = build_analysis_records(tmp_path)

    assert [row["source_path"] for row in rows] == sorted(row["source_path"] for row in rows)
    assert {row["project_name"] for row in rows} == {
        "京橋信用ソリューションズ株式会社"
    }
    assert {row["source_path"] for row in rows} == {
        "プロジェクト/京橋信用ソリューションズ株式会社/04.分析/metrics.json",
        "プロジェクト/京橋信用ソリューションズ株式会社/04.分析/project/config/project_config.json",
        "プロジェクト/京橋信用ソリューションズ株式会社/04.分析/project/metrics.json",
    }
    assert [row["payload"] for row in rows if row["source_path"].endswith("metrics.json")] == [
        {"score": 0.9},
        {"score": 0.8},
    ]
    assert all(row["generated_by"] == "scripts/build_analysis_artifacts.py" for row in rows)
    assert all(row["do_not_edit"] is True for row in rows)


def test_notebook_keeps_text_outputs_but_not_images(tmp_path: Path) -> None:
    analysis = _analysis_dir(tmp_path, "A社")
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "source": ["# title\n", "body\n", "![plot](data:image/png;base64,AAAA)"],
                "metadata": {},
            },
            {
                "cell_type": "code",
                "source": ["print('ok')"],
                "outputs": [
                    {"output_type": "stream", "name": "stdout", "text": ["ok\n"]},
                    {
                        "output_type": "execute_result",
                        "data": {"text/plain": ["value\n"], "image/png": "AAAA"},
                    },
                ],
            },
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (analysis / "eda.ipynb").write_text(json.dumps(notebook), encoding="utf-8")

    row = build_analysis_records(tmp_path)[0]

    assert row["kind"] == "notebook"
    assert row["payload"]["cells"][0] == {
        "cell_number": 1,
        "cell_type": "markdown",
        "source": "# title\nbody\n![plot]([embedded-image-removed])",
        "outputs": [],
    }
    assert row["payload"]["cells"][1]["outputs"] == [
        {"output_type": "stream", "name": "stdout", "text": "ok\n"},
        {"output_type": "execute_result", "text/plain": "value\n"},
    ]
    assert "AAAA" not in json.dumps(row, ensure_ascii=False)


def test_python_ast_records_assignments_comparisons_and_call_keywords(tmp_path: Path) -> None:
    analysis = _analysis_dir(tmp_path, "A社")
    (analysis / "model.py").write_text(
        "LIMIT = 10\ncols = ['a', 'b']\nflag = kind != 'hist'\nfit(depth=3, random_state=seed)\n",
        encoding="utf-8",
    )

    payload = build_analysis_records(tmp_path)[0]["payload"]

    assert {item["target"]: item["value"] for item in payload["assignments"]} == {
        "LIMIT": 10,
        "cols": ["a", "b"],
    }
    assert payload["comparisons"] == [
        {"left": "kind", "operators": ["NotEq"], "comparators": ["hist"]}
    ]
    assert payload["calls"] == [
        {
            "function": "fit",
            "keywords": {"depth": 3, "random_state": {"name": "seed"}},
        }
    ]


def test_python_syntax_error_becomes_failure_and_scan_continues(tmp_path: Path) -> None:
    analysis = _analysis_dir(tmp_path, "A社")
    (analysis / "bad.py").write_text("if:\n", encoding="utf-8")
    (analysis / "good.json").write_text('{"ok": true}', encoding="utf-8")

    rows = build_analysis_records(tmp_path)

    assert [row["kind"] for row in rows] == ["failure", "json"]
    assert rows[0]["payload"]["source_kind"] == "python"
    assert rows[0]["payload"]["error_type"] == "SyntaxError"


def test_python_dict_unpack_and_non_json_constants_do_not_stop_writer(tmp_path: Path) -> None:
    analysis = _analysis_dir(tmp_path, "A社")
    (analysis / "valid.py").write_text(
        "cfg = {**base, 'x': 1}\nmagic = b'abc'\nnumber = 1j\n", encoding="utf-8"
    )

    rows = build_analysis_records(tmp_path)
    output = tmp_path / "records.jsonl"
    write_analysis_records(output, rows)

    loaded = json.loads(output.read_text(encoding="utf-8"))
    assignments = {item["target"]: item["value"] for item in loaded["payload"]["assignments"]}
    assert assignments["cfg"] == {"**": {"name": "base"}, "x": 1}
    assert assignments["magic"] == {"literal": "b'abc'"}
    assert assignments["number"] == {"literal": "1j"}


def test_writer_and_store_filter_analysis_records(tmp_path: Path) -> None:
    output = tmp_path / "analysis_records.jsonl"
    write_analysis_records(
        output,
        [
            {"project_name": "A社", "kind": "json", "source_path": "a.json", "payload": {}},
            {"project_name": "A社", "kind": "python", "source_path": "a.py", "payload": {}},
            {"project_name": "B社", "kind": "json", "source_path": "b.json", "payload": {}},
        ],
    )

    store = StructuredArtifactStore.from_artifacts_dir(tmp_path)

    assert len(store.analysis_records_for("A社")) == 2
    assert [row["kind"] for row in store.analysis_records_for("A社", "json")] == ["json"]
