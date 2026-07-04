"""artifactsから機械採点可能な擬似評価質問を生成する。

本物valid/testとは混ぜない。出力は data/generated_eval/ 配下のみ。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


@dataclass
class GeneratedQuestion:
    id: str
    question: str
    answer: str
    type: str
    source_path: str


def _load_json(path: Path) -> Any:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _short_project_name(project_name: str, aliases_by_project: dict[str, list[str]]) -> str:
    aliases = [a for a in aliases_by_project.get(project_name, []) if 2 <= len(str(a)) <= 16]
    return str(aliases[0]) if aliases else project_name


def _clean_task_value(value: object) -> str:
    text = str(value or "").strip()
    return re.sub(r"^\s*\d+\s*[\.．]\s*", "", text)


def _task_ids(rows: list[dict]) -> str:
    ids = sorted({str(r.get("values", {}).get("タスクID")) for r in rows if r.get("values", {}).get("タスクID")})
    return "、".join(ids)


def _schedule_questions(rows: list[dict], aliases: dict[str, list[str]], per_type: int) -> list[GeneratedQuestion]:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        values = row.get("values") or {}
        project = row.get("project_name") or ""
        for key in ("フェーズ名", "フェーズ", "ステータス", "成果物"):
            value = _clean_task_value(values.get(key))
            if value and value != key:
                groups[(project, key, value)].append(row)
        for person in re.split(r"[/、,]", str(values.get("担当者") or "")):
            person = person.strip()
            if len(person) >= 2:
                groups[(project, "担当者", person)].append(row)

    questions = []
    for (project, key, value), matched in sorted(groups.items()):
        if not project or not (1 <= len(matched) <= 8):
            continue
        name = _short_project_name(project, aliases)
        if key in ("フェーズ名", "フェーズ"):
            q = f"{name}案件で、{value}フェーズに一致するタスクIDをすべて挙げてください。"
        elif key == "担当者":
            q = f"{name}案件で、{value}さんが担当しているタスクIDをすべて挙げてください。"
        elif key == "ステータス":
            q = f"{name}案件で、ステータスが{value}のタスクIDをすべて挙げてください。"
        else:
            q = f"{name}案件で、成果物に「{value}」を含むタスクIDをすべて挙げてください。"
        questions.append(GeneratedQuestion(
            id=f"gen_schedule_{len(questions):04d}",
            question=q,
            answer=_task_ids(matched),
            type=f"schedule_{key}",
            source_path=str(matched[0].get("source_path") or ""),
        ))
        if len(questions) >= per_type:
            break
    return questions


def _filter_condition_text(sheet: dict) -> str:
    parts = []
    for fc in sheet.get("filter_columns") or []:
        header = fc.get("header") or f"列{fc.get('col_id')}"
        values = fc.get("values") or []
        if values:
            parts.append(f"{header}={ '/'.join(str(v) for v in values) }")
        for custom in fc.get("custom") or []:
            parts.append(f"{header}{custom.get('operator')}{custom.get('val')}")
    return "、".join(parts)


def _filter_questions(rows: list[dict], aliases: dict[str, list[str]], per_type: int) -> list[GeneratedQuestion]:
    questions = []
    for sheet in rows:
        if not sheet.get("filter_columns"):
            continue
        project = sheet.get("project_name") or ""
        answer = _filter_condition_text(sheet)
        if not project or not answer:
            continue
        name = _short_project_name(project, aliases)
        questions.append(GeneratedQuestion(
            id=f"gen_filter_{len(questions):04d}",
            question=f"{name}案件のtrain.xlsxで、フィルターで抽出されている条件を教えてください。",
            answer=answer,
            type="spreadsheet_filter_condition",
            source_path=str(sheet.get("source_path") or ""),
        ))
        if len(questions) >= per_type:
            break
    return questions


def _highlight_questions(rows: list[dict], aliases: dict[str, list[str]], per_type: int) -> list[GeneratedQuestion]:
    questions = []
    for block in rows:
        project = block.get("project_name") or ""
        value = str(block.get("first_value") or "").strip()
        color = str(block.get("fill_color_name") or "").strip()
        cell_range = str(block.get("range") or "").strip()
        # THEME色など質問文として不自然な色名は、まず明示色だけを回帰対象にする。
        if not project or not value or color not in {"yellow", "red", "blue", "green", "orange"} or not cell_range:
            continue
        name = _short_project_name(project, aliases)
        questions.append(GeneratedQuestion(
            id=f"gen_highlight_{len(questions):04d}",
            question=f"{name}案件のtrain.xlsxで、{cell_range}の{color}ハイライトされているセルの値を教えてください。",
            answer=value,
            type="spreadsheet_highlight_value",
            source_path=str(block.get("source_path") or ""),
        ))
        if len(questions) >= per_type:
            break
    return questions


def _office_questions(rows: list[dict], aliases: dict[str, list[str]], per_type: int) -> list[GeneratedQuestion]:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for mark in rows:
        text = str(mark.get("text") or "").strip()
        if not text or len(text) < 2 or not re.search(r"[A-Za-z0-9一-龥ぁ-んァ-ヶ]", text):
            continue
        if text in {"。", "、", ".", ","}:
            continue
        style = ""
        if mark.get("bold"):
            style = "太字"
        elif mark.get("underline"):
            style = "下線"
        elif mark.get("italic"):
            style = "イタリック"
        elif "YELLOW" in str(mark.get("highlight_color") or "").upper():
            style = "黄色ハイライト"
        if style:
            groups[(mark.get("project_name") or "", mark.get("file_name") or "", style)].append(mark)

    questions = []
    for (project, file_name, style), marks in sorted(groups.items()):
        if not project or not file_name or not (1 <= len(marks) <= 6):
            continue
        name = _short_project_name(project, aliases)
        answer = "、".join(str(m.get("text")).strip() for m in marks)
        if len(answer) > 240:
            continue
        questions.append(GeneratedQuestion(
            id=f"gen_office_{len(questions):04d}",
            question=f"{name}案件の{file_name}において、{style}で記載されている部分をすべて抜き出してください。",
            answer=answer,
            type=f"office_style_{style}",
            source_path=str(marks[0].get("source_path") or ""),
        ))
        if len(questions) >= per_type:
            break
    return questions


def build_questions(artifacts_dir: Path, per_type: int = 20) -> list[GeneratedQuestion]:
    projects = _load_json(artifacts_dir / "project_registry.json")
    aliases = {p.get("project_name", ""): p.get("aliases", []) for p in projects}
    questions: list[GeneratedQuestion] = []
    questions += _schedule_questions(_load_jsonl(artifacts_dir / "schedule_tasks.jsonl"), aliases, per_type)
    questions += _filter_questions(_load_jsonl(artifacts_dir / "train_xlsx_sheets.jsonl"), aliases, per_type)
    questions += _highlight_questions(_load_jsonl(artifacts_dir / "train_xlsx_highlight_blocks.jsonl"), aliases, per_type)
    questions += _office_questions(_load_jsonl(artifacts_dir / "office_marks.jsonl"), aliases, per_type)
    return questions


def main() -> None:
    parser = argparse.ArgumentParser(description="artifact由来の擬似評価セットを生成")
    parser.add_argument("--artifacts-dir", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "generated_eval")
    parser.add_argument("--per-type", type=int, default=20)
    args = parser.parse_args()

    questions = build_questions(args.artifacts_dir, per_type=args.per_type)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    payload = [{"id": q.id, "question": q.question, "answer": q.answer} for q in questions]
    (args.out_dir / "questions.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out_dir / "metadata.jsonl").write_text(
        "\n".join(json.dumps(asdict(q), ensure_ascii=False) for q in questions) + "\n",
        encoding="utf-8",
    )
    print(f"generated_eval questions: {len(questions)} -> {args.out_dir / 'questions.json'}")


if __name__ == "__main__":
    main()
