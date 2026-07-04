"""run間flip分析。前回runとの差分（改善/悪化した問題）を出す。"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.models import CRAGLabel


def _score(label: str) -> float:
    try:
        return CRAGLabel(label).score
    except ValueError:
        return 0.0


@dataclass
class FlipReport:
    base_name: str
    new_name: str
    base_mean: float
    new_mean: float
    improved: list[dict] = field(default_factory=list)
    worsened: list[dict] = field(default_factory=list)
    unchanged_count: int = 0

    def report(self) -> str:
        lines = [
            f"=== flip分析: {self.base_name} → {self.new_name} ===",
            f"mean: {self.base_mean:.4f} → {self.new_mean:.4f} "
            f"({self.new_mean - self.base_mean:+.4f})",
            f"改善 {len(self.improved)} / 悪化 {len(self.worsened)} / 不変 {self.unchanged_count}",
        ]
        if self.improved:
            lines.append("\n[改善]")
            for f in self.improved:
                lines.append(f"  {f['question_id']}: {f['base_label']} → {f['new_label']}  {f['question'][:50]}")
        if self.worsened:
            lines.append("\n[悪化]")
            for f in self.worsened:
                lines.append(f"  {f['question_id']}: {f['base_label']} → {f['new_label']}  {f['question'][:50]}")
                lines.append(f"    新回答: {f.get('new_answer', '')[:80]}")
        return "\n".join(lines)


def compare_runs(
    base: dict, new: dict, base_name: str = "base", new_name: str = "new"
) -> FlipReport:
    base_by_id = {r["question_id"]: r for r in base["results"]}
    new_by_id = {r["question_id"]: r for r in new["results"]}
    common_ids = [qid for qid in base_by_id if qid in new_by_id]

    base_scores = [_score(base_by_id[q]["judge_label"]) for q in common_ids]
    new_scores = [_score(new_by_id[q]["judge_label"]) for q in common_ids]

    report = FlipReport(
        base_name=base_name,
        new_name=new_name,
        base_mean=sum(base_scores) / len(base_scores) if base_scores else 0.0,
        new_mean=sum(new_scores) / len(new_scores) if new_scores else 0.0,
    )

    for qid in common_ids:
        b, n = base_by_id[qid], new_by_id[qid]
        bs, ns = _score(b["judge_label"]), _score(n["judge_label"])
        entry = {
            "question_id": qid,
            "question": n["question"],
            "base_label": b["judge_label"],
            "new_label": n["judge_label"],
            "new_answer": n.get("answer", ""),
        }
        if ns > bs:
            report.improved.append(entry)
        elif ns < bs:
            report.worsened.append(entry)
        else:
            report.unchanged_count += 1
    return report
