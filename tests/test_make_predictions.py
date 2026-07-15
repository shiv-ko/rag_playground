from pathlib import Path

import scripts.make_predictions as make_predictions


def test_main_passes_persistent_cache_to_pipeline(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def build_index(self):
            pass

        def run(self, qa_pairs):
            return []

    monkeypatch.setattr(make_predictions, "Pipeline", FakePipeline)
    monkeypatch.setattr(make_predictions, "load_questions_csv", lambda path: [])
    monkeypatch.setattr(
        "sys.argv",
        [
            "make_predictions.py",
            "--data-dir",
            str(tmp_path / "data"),
            "--questions",
            str(tmp_path / "questions.csv"),
            "--out",
            str(tmp_path / "predictions.csv"),
        ],
    )

    make_predictions.main()

    assert captured["cache_dir"] == Path(make_predictions.ROOT) / ".cache"


def test_main_can_disable_persistent_cache(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def build_index(self):
            pass

        def run(self, qa_pairs):
            return []

    monkeypatch.setattr(make_predictions, "Pipeline", FakePipeline)
    monkeypatch.setattr(make_predictions, "load_questions_csv", lambda path: [])
    monkeypatch.setattr(
        "sys.argv",
        [
            "make_predictions.py",
            "--data-dir",
            str(tmp_path / "data"),
            "--questions",
            str(tmp_path / "questions.csv"),
            "--out",
            str(tmp_path / "predictions.csv"),
            "--no-cache",
        ],
    )

    make_predictions.main()

    assert captured["cache_dir"] is None
