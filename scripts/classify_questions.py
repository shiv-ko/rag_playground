"""questions_valid.csv の設問をタグ分類し、ベースラインの理論上限スコアを見積もる。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.utils.question_classifier import classify_question
from src.utils.question_loader import load_questions_csv

# ベースライン（テキストのみ）が原理的に正答できないタグ
UNSUPPORTED_TAGS = {"image_or_graph", "version_diff", "password_protected"}


def main() -> None:
    questions_path = ROOT / "data" / "raw" / "share" / "質問回答" / "questions_valid.csv"
    qa_pairs = load_questions_csv(questions_path)

    tag_counts: dict[str, int] = {}
    supportable = 0
    for qa in qa_pairs:
        tags = classify_question(qa.question)
        for t in tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
        if not (set(tags) & UNSUPPORTED_TAGS):
            supportable += 1

    total = len(qa_pairs)
    print(f"設問総数: {total}")
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        print(f"  {tag}: {count} ({100*count/total:.1f}%)")

    best_case_mean = supportable / total
    print(f"\nベースライン(テキストのみ)で対応可能と推定: {supportable}/{total}")
    print(f"理論上限スコア（対応可能分が全てPerfectと仮定）: {best_case_mean:.3f}")


if __name__ == "__main__":
    main()
