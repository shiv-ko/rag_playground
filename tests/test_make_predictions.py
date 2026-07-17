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


def test_main_conservative_flag_passes_to_stabilizer(monkeypatch, tmp_path):
    """--conservativeはstabilize_answersのconservativeモードに配線される。"""
    captured: dict[str, object] = {}

    class FakeResult:
        def __init__(self, question_id, answer):
            self.question_id = question_id
            self.answer = answer

    class FakePipeline:
        def __init__(self, **kwargs):
            pass

        def build_index(self):
            pass

        def run(self, qa_pairs):
            return [FakeResult("0", "回答A")]

    class FakeQA:
        question_id = "0"

    monkeypatch.setattr(make_predictions, "Pipeline", FakePipeline)
    monkeypatch.setattr(make_predictions, "load_questions_csv", lambda path: [FakeQA()])
    monkeypatch.setattr(make_predictions, "ROOT", tmp_path)  # 監査JSONをリポジトリ外へ

    real_stabilize = make_predictions.stabilize_answers

    def spy(**kwargs):
        captured.update(kwargs)
        return real_stabilize(**kwargs)

    monkeypatch.setattr(make_predictions, "stabilize_answers", spy)
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
            "--runs",
            "2",
            "--conservative",
        ],
    )

    make_predictions.main()

    assert captured["conservative"] is True
