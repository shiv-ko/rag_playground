from __future__ import annotations

import json
from pathlib import Path

from src.generator.analysis_answerer import AnalysisAnswerer
from src.structured.artifact_store import StructuredArtifactStore
from src.utils.question_classifier import classify_question


def _store(tmp_path: Path, rows: list[dict]) -> StructuredArtifactStore:
    (tmp_path / "analysis_records.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8"
    )
    return StructuredArtifactStore.from_artifacts_dir(tmp_path)


def _row(kind: str, payload: dict, path: str = "src/modeling.py") -> dict:
    return {"project_name": "A社", "kind": kind, "source_path": path, "payload": payload}


def test_sparse_output_false_model_is_derived_from_comparison(tmp_path: Path) -> None:
    store = _store(tmp_path, [_row("python", {"assignments": [], "comparisons": [], "calls": [
        {"function": "build_preprocessor", "args": [], "keywords": {
            "sparse_output": {"expression": "model_key != 'hist_gradient_boosting'"}
        }}
    ]})])
    answer = AnalysisAnswerer().answer(
        "modeling.pyで前処理器のsparse_outputがFalseになるmodel_typeは何ですか", "A社", store
    )
    assert answer is not None
    assert answer.text == "hist_gradient_boosting"
    assert answer.confidence == 0.95
    assert answer.source_docs[0].document.source_path == Path("src/modeling.py")


def test_cat_condition_reports_actual_dtype_candidates_and_operator(tmp_path: Path) -> None:
    payload = {
        "assignments": [],
        "comparisons": [{"left": "unique_count", "operators": ["GtE"], "comparators": [{"name": "limit"}]}],
        "calls": [
            {"function": "pd.api.types.is_object_dtype", "args": [{"name": "series"}], "keywords": {}},
            {"function": "pd.api.types.is_string_dtype", "args": [{"name": "series"}], "keywords": {}},
            {"function": "pd.api.types.is_categorical_dtype", "args": [{"name": "series"}], "keywords": {}},
        ],
    }
    store = _store(tmp_path, [_row("python", payload, "src/features.py")])
    answer = AnalysisAnswerer().answer("CATはdtypeとユニーク数の条件でどのように判定しますか", "A社", store)
    assert answer is not None
    assert answer.text == "object・string・categorical型で、かつ unique_count < limit の列をCATと判定します。"


def test_runtime_model_defaults_merge_code_and_config(tmp_path: Path) -> None:
    config = _row("json", {"model_type": "gradient_boosting", "model_params": {}, "random_state": 42}, "configs/project_config.json")
    code = _row("python", {
        "assignments": [
            {"target": "n_estimators", "value": {"expression": "to_int(model_params.get('n_estimators'), 300)"}},
            {"target": "learning_rate", "value": {"expression": "to_float(model_params.get('learning_rate'), 0.1)"}},
        ],
        "comparisons": [],
        "calls": [{"function": "GradientBoostingClassifier", "args": [], "keywords": {
            "n_estimators": {"name": "n_estimators"}, "learning_rate": {"name": "learning_rate"},
            "random_state": {"name": "random_state"}
        }}],
    })
    store = _store(tmp_path, [config, code])
    answer = AnalysisAnswerer().answer(
        "勾配ブースティング法に実際に渡されるn_estimators、learning_rate、random_stateはそれぞれいくつですか", "A社", store
    )
    assert answer is not None
    assert answer.text == "n_estimators=300、learning_rate=0.1、random_state=42"


def test_metrics_json_path_and_generated_interaction_columns(tmp_path: Path) -> None:
    metrics = _row("json", {
        "model_params": {"max_depth": 12},
        "feature_selection": {"selected_columns": ["a", "a__x__b", "b__x__c"]},
    }, "analysis_outputs/metrics.json")
    code = _row("python", {
        "assignments": [{"target": "feature_name", "value": {"expression": "f'{left}__x__{right}'"}}],
        "comparisons": [], "calls": [],
    }, "src/features.py")
    store = _store(tmp_path, [metrics, code])
    answer = AnalysisAnswerer().answer("最良モデルのパラメータmax_depthはいくらですか", "A社", store)
    assert answer is not None and answer.text == "12"
    listed = AnalysisAnswerer().answer(
        "feature_selection.selected_columnsに含まれる生成された数値交互作用特徴量をすべて答えてください", "A社", store
    )
    assert listed is not None and listed.text == "a__x__b、b__x__c"


def test_ambiguous_or_missing_evidence_returns_none(tmp_path: Path) -> None:
    rows = [
        _row("json", {"model_params": {"max_depth": 3}}, "a/metrics.json"),
        _row("json", {"model_params": {"max_depth": 4}}, "b/metrics.json"),
    ]
    store = _store(tmp_path, rows)
    assert AnalysisAnswerer().answer("max_depthはいくらですか", "A社", store) is None
    assert AnalysisAnswerer().answer("無関係な質問", "A社", store) is None


def test_classifier_adds_only_narrow_analysis_tags() -> None:
    assert "analysis_code" in classify_question("modeling.pyのsparse_outputがFalseになる条件は何ですか")
    assert "analysis_json" in classify_question("metrics.jsonのmodel_params.max_depthはいくらですか")
    assert "analysis_json" in classify_question("最良モデルのパラメータであるmax_depthはいくらですか")
    assert classify_question("分析結果について説明してください") == ["text_only"]


def test_notebook_text_output_top_n_smallest_is_verified_against_csv(tmp_path: Path) -> None:
    import pandas as pd

    project_dir = tmp_path / "A社" / "04.分析" / "analysis_project"
    (project_dir / "data").mkdir(parents=True)
    pd.DataFrame({"target": [1, 2, 3, 4, 5], "a": [1, 2, 3, 4, 5], "b": [2, 3, 4, 6, 8], "c": [5, 4, 3, 2, 1]}).to_csv(project_dir / "data/train.csv", index=False)
    rows = [
        _row("json", {"data_csv": "data/train.csv", "target_column": "target"}, "A社/04.分析/analysis_project/configs/project_config.json"),
        _row("notebook", {"cells": [{"cell_number": 1, "cell_type": "code", "source": "corr_s.abs().sort_values(ascending=False).head(3)", "outputs": [{"output_type": "stream", "text": "目的変数との相関 上位3\na  1.000000\nc  1.000000\nb  0.984798\nName: target, dtype: float64\n"}]}]}, "A社/04.分析/analysis_project/notebooks/01_eda.ipynb"),
    ]
    answer = AnalysisAnswerer(data_dir=tmp_path).answer(
        "NB01_eda.ipynbの相関 上位3の中で相関係数が最も小さいカラム名", "A社", _store(tmp_path, rows)
    )
    assert answer is not None and answer.text == "b"


def test_notebook_source_recomputes_heatmap_top_n_smallest(tmp_path: Path) -> None:
    import pandas as pd

    project_dir = tmp_path / "A社" / "04.分析" / "analysis_project"
    (project_dir / "data").mkdir(parents=True)
    pd.DataFrame({"target": [1, 2, 3, 4, 5], "a": [1, 2, 3, 4, 5], "b": [2, 3, 4, 6, 8], "c": [5, 4, 3, 2, 1]}).to_csv(project_dir / "data/train.csv", index=False)
    rows = [
        _row("json", {"data_csv": "data/train.csv", "target_column": "target"}, "A社/04.分析/analysis_project/configs/project_config.json"),
        _row("notebook", {"cells": [{"cell_number": 1, "cell_type": "code", "source": "target_corr_abs = frame.corrwith(frame[target]).abs().sort_values(ascending=False)\ntop_cols = target_corr_abs.head(3).index.tolist()\nsns.heatmap(frame[top_cols].corr())", "outputs": []}]}, "A社/04.分析/analysis_project/notebooks/01_eda.ipynb"),
    ]
    answer = AnalysisAnswerer(data_dir=tmp_path).answer(
        "01_eda.ipynbの特徴量相関ヒートマップで可視化された特徴量のうち、targetとの相関係数の絶対値が最も小さい特徴量", "A社", _store(tmp_path, rows)
    )
    assert answer is not None and answer.text == "b"


def test_notebook_correlation_returns_none_for_tie_or_axis_ticks(tmp_path: Path) -> None:
    import pandas as pd

    project_dir = tmp_path / "A社" / "04.分析" / "analysis_project"
    (project_dir / "data").mkdir(parents=True)
    pd.DataFrame({"target": [1, 2, 3], "a": [1, 2, 3], "b": [3, 2, 1]}).to_csv(project_dir / "data/train.csv", index=False)
    rows = [
        _row("json", {"data_csv": "data/train.csv", "target_column": "target"}, "A社/04.分析/analysis_project/configs/project_config.json"),
        _row("notebook", {"cells": [{"cell_number": 1, "cell_type": "code", "source": "corr.abs().sort_values(ascending=False).head(2)", "outputs": []}]}, "A社/04.分析/analysis_project/notebooks/01_eda.ipynb"),
    ]
    answerer = AnalysisAnswerer(data_dir=tmp_path)
    store = _store(tmp_path, rows)
    assert answerer.answer("01_eda.ipynbで目的変数との相関が最も高い特徴量", "A社", store) is None
    assert answerer.answer("01_eda.ipynbのy軸目盛りの最大値", "A社", store) is None


def test_heatmap_spec_is_not_contaminated_by_other_correlation_cell(tmp_path: Path) -> None:
    import pandas as pd

    project_dir = tmp_path / "A社" / "04.分析" / "analysis_project"
    (project_dir / "data").mkdir(parents=True)
    pd.DataFrame({"target": [1, 2, 3, 4, 5], "a": [1, 2, 3, 4, 5], "b": [1, 1, 2, 2, 3], "c": [5, 3, 4, 1, 2]}).to_csv(project_dir / "data/train.csv", index=False)
    rows = [
        _row("json", {"data_csv": "data/train.csv", "target_column": "target"}, "A社/04.分析/analysis_project/configs/project_config.json"),
        _row("notebook", {"cells": [
            {"cell_number": 1, "cell_type": "code", "source": "corr = frame.corr()\nsns.heatmap(corr)", "outputs": []},
            {"cell_number": 2, "cell_type": "code", "source": "corr_s.abs().sort_values(ascending=False).head(1)", "outputs": [{"output_type": "stream", "text": "目的変数との相関 上位1\na 1.0"}]},
        ]}, "A社/04.分析/analysis_project/notebooks/01_eda.ipynb"),
    ]
    answer = AnalysisAnswerer(data_dir=tmp_path).answer(
        "01_eda.ipynbの相関ヒートマップにある特徴量のうち、targetとの相関が最も小さい特徴量", "A社", _store(tmp_path, rows)
    )
    assert answer is not None and answer.text == "c"
