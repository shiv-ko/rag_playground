"""retrieval_eval の純粋関数テスト。実データ・実インデックスは使わない。"""
import unicodedata
from pathlib import Path

from src.evaluator.retrieval_eval import (
    CandidateSet,
    QuestionLabel,
    candidate_files,
    evaluate_one,
    load_labels,
    resolve_projects,
    summarize_records,
)
from src.models import Document, ScoredDocument

PROJECT_REGISTRY = [
    {"project_name": "株式会社東都人材プラットフォーム",
     "aliases": ["TOTO", "東都", "東都人材プラットフォーム", "株式会社東都人材プラットフォーム"]},
    {"project_name": "京橋信用ソリューションズ株式会社",
     "aliases": ["KSS", "京橋", "京橋信用ソリューションズ"]},
]

DOC_REGISTRY = [
    {"source_path": "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/00.提案/提案書.pptx",
     "project_name": "株式会社東都人材プラットフォーム", "section": "00.提案"},
    {"source_path": "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/06.報告書/最終報告書.pptx",
     "project_name": "株式会社東都人材プラットフォーム", "section": "06.報告書"},
    {"source_path": "data/raw/share/共有ドライブ/プロジェクト/京橋信用ソリューションズ株式会社/06.報告書/最終報告書.pptx",
     "project_name": "京橋信用ソリューションズ株式会社", "section": "06.報告書"},
]


def _label(question, section, index="0"):
    return QuestionLabel(split="valid", index=index, question=question,
                         primary_type="single_text",
                         source_section=section.split(";") if section else [])


def test_load_labels(tmp_path):
    csv_path = tmp_path / "labels.csv"
    csv_path.write_text(
        "split,index,question,primary_type,secondary_types,source_section,"
        "answer_shape,risk,required_extractor,notes\n"
        "valid,0,質問A,single_text,,06.報告書,single_text,low,text_retriever,x\n"
        "valid,1,質問B,internal_terms,list_extraction,02.計画;06.報告書,list,high,term_registry,x\n"
        "test,0,質問C,single_text,,unknown,single_text,low,text_retriever,x\n",
        encoding="utf-8",
    )
    labels = load_labels(csv_path, split="valid")
    assert len(labels) == 2
    assert labels[1].source_section == ["02.計画", "06.報告書"]


def test_resolve_projects_alias():
    assert resolve_projects("TOTOのPLについて", PROJECT_REGISTRY) == ["株式会社東都人材プラットフォーム"]
    assert resolve_projects("東都人材プラットフォームの提案書", PROJECT_REGISTRY) == ["株式会社東都人材プラットフォーム"]
    assert resolve_projects("該当なしの質問", PROJECT_REGISTRY) == []


def test_candidate_files_project_and_section():
    label = _label("東都の最終報告書について", "06.報告書")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)
    assert cand.measurable is True
    assert cand.files == frozenset({
        "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/06.報告書/最終報告書.pptx"
    })


def test_candidate_files_section_only():
    """案件が特定できなくてもセクションがあれば全案件の該当セクションが候補。"""
    label = _label("すべての最終報告書を確認", "06.報告書")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)
    assert cand.measurable is True
    assert len(cand.files) == 2


def test_candidate_files_unmeasurable():
    label = _label("全案件の消費税合計は", "cross_project")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)
    assert cand.measurable is False


def test_candidate_files_unknown_section_with_project():
    """sectionがunknownでも案件が特定できれば案件全ファイルが候補。"""
    label = _label("東都の何か", "unknown")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)
    assert cand.measurable is True
    assert len(cand.files) == 2  # 東都の2ファイル


def test_evaluate_one_hit_and_rank():
    label = _label("東都の最終報告書について", "06.報告書")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)

    from src.utils.paths import ROOT
    hit_path = ROOT / "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/06.報告書/最終報告書.pptx"
    miss_path = ROOT / "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/00.提案/提案書.pptx"

    def fake_search(query, top_k):
        return [
            ScoredDocument(document=Document(text="x", source_path=miss_path), score=2.0),
            ScoredDocument(document=Document(text="y", source_path=hit_path), score=1.0),
        ]

    rec = evaluate_one(fake_search, label, cand, top_k=5)
    assert rec.hit is True
    assert rec.first_hit_rank == 2


def test_evaluate_one_miss():
    label = _label("京橋の最終報告書", "06.報告書")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)

    from src.utils.paths import ROOT
    other = ROOT / "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/00.提案/提案書.pptx"

    def fake_search(query, top_k):
        return [ScoredDocument(document=Document(text="x", source_path=other), score=1.0)]

    rec = evaluate_one(fake_search, label, cand, top_k=5)
    assert rec.hit is False
    assert rec.first_hit_rank == 0


def test_evaluate_one_hit_despite_nfd_vs_nfc_mismatch():
    """document_registry.jsonlのsource_pathがNFDで、実ファイルパス(NFC)と
    ユニコード正規化形式が異なっていても、正規化後の文字列一致でhitすること。
    （macOSファイルシステムはパスをNFDで返すため実運用で発生する）"""
    nfd_registry = [
        {
            "source_path": unicodedata.normalize(
                "NFD",
                "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/06.報告書/最終報告書.pptx",
            ),
            "project_name": "株式会社東都人材プラットフォーム",
            "section": "06.報告書",
        },
    ]
    label = _label("東都の最終報告書について", "06.報告書")
    cand = candidate_files(label, nfd_registry, PROJECT_REGISTRY)
    assert cand.measurable is True

    from src.utils.paths import ROOT
    # 実ファイルパス側はNFC正規化済みとして与える（合成済み文字）
    hit_path = ROOT / unicodedata.normalize(
        "NFC",
        "data/raw/share/共有ドライブ/プロジェクト/株式会社東都人材プラットフォーム/06.報告書/最終報告書.pptx",
    )

    def fake_search(query, top_k):
        return [ScoredDocument(document=Document(text="x", source_path=hit_path), score=1.0)]

    rec = evaluate_one(fake_search, label, cand, top_k=5)
    assert rec.hit is True
    assert rec.first_hit_rank == 1


def test_resolve_projects_alias_nfd_question():
    """質問文がNFD正規化された文字列でもエイリアス照合がヒットすること。"""
    nfd_question = unicodedata.normalize("NFD", "東都人材プラットフォームの提案書")
    assert resolve_projects(nfd_question, PROJECT_REGISTRY) == ["株式会社東都人材プラットフォーム"]


def test_summarize_records_contains_type_table():
    label = _label("東都の最終報告書について", "06.報告書")
    cand = candidate_files(label, DOC_REGISTRY, PROJECT_REGISTRY)

    def fake_search(query, top_k):
        return []

    rec = evaluate_one(fake_search, label, cand, top_k=5)
    text = summarize_records([rec])
    assert "single_text" in text
    assert "0/1" in text or "0.0" in text
