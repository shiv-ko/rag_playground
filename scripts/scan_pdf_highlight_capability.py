"""共有ドライブ配下の全PDFをスキャンし、ハイライト機構の適用範囲を集計する。
- ハイライト注釈（/Highlight）の有無
- ベクタ矩形塗り（re + f/f*/F 系オペレータ）とテキスト共存の有無（簡易ヒューリスティック）
- ページ全面を覆う画像XObject（=ラスタ化ページ）の有無
"""
import json
import unicodedata
from pathlib import Path

import pypdf
from pypdf.generic import ContentStream

ROOT = Path("/Users/shiv/P/rag_comp")
SHARE_ROOT = ROOT / "data" / "raw" / "share" / "共有ドライブ"

FILL_OPS = {b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}
TEXT_OPS = {b"Tj", b"TJ", b"'", b'"'}


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def analyze_pdf(path: Path) -> dict:
    result = {
        "path": nfc(str(path.relative_to(ROOT))),
        "error": None,
        "num_pages": 0,
        "highlight_annot_pages": 0,
        "total_highlight_annots": 0,
        "vector_rect_with_text_pages": 0,
        "fullpage_image_pages": 0,
        "text_pages": 0,  # pages with extract_text() len > 20
        "empty_text_pages": 0,
    }
    try:
        reader = pypdf.PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001
        result["error"] = repr(exc)
        return result

    result["num_pages"] = len(reader.pages)

    for page in reader.pages:
        # --- annotations ---
        annots = page.get("/Annots")
        if annots:
            for a in annots:
                try:
                    obj = a.get_object()
                except Exception:  # noqa: BLE001
                    continue
                if obj.get("/Subtype") == "/Highlight":
                    result["total_highlight_annots"] += 1
            if result["total_highlight_annots"] > 0:
                result["highlight_annot_pages"] += 1

        # --- text extraction ---
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        if len(text.strip()) > 20:
            result["text_pages"] += 1
        else:
            result["empty_text_pages"] += 1

        # --- full-page image xobject (rasterized page indicator) ---
        try:
            mediabox = page.mediabox
            pw, ph = float(mediabox.width), float(mediabox.height)
            res = page.get("/Resources", {})
            xobj = res.get("/XObject", {}) if res else {}
            has_fullpage_image = False
            for v in xobj.values():
                obj = v.get_object()
                if obj.get("/Subtype") == "/Image":
                    w, h = obj.get("/Width", 0), obj.get("/Height", 0)
                    if w and h:
                        # very rough: any image present + little/no text => likely rasterized page
                        has_fullpage_image = True
            if has_fullpage_image and len(text.strip()) <= 20:
                result["fullpage_image_pages"] += 1
        except Exception:  # noqa: BLE001
            pass

        # --- vector rect fill + text co-occurrence (heuristic) ---
        try:
            contents = page.get_contents()
            if contents is not None:
                cs = ContentStream(contents, reader)
                pending_rect = False
                found = False
                for operands, operator in cs.operations:
                    if operator == b"re":
                        pending_rect = True
                    elif operator in FILL_OPS and pending_rect:
                        pending_rect = False
                        # mark: a filled rect happened; check if any text op follows later in same page
                    elif operator in TEXT_OPS:
                        found_text_op = True
                if any(op == b"re" for _, op in cs.operations) and any(
                    op in FILL_OPS for _, op in cs.operations
                ) and any(op in TEXT_OPS for _, op in cs.operations):
                    found = True
                if found:
                    result["vector_rect_with_text_pages"] += 1
        except Exception:  # noqa: BLE001
            pass

    return result


def main():
    pdf_paths = sorted(SHARE_ROOT.rglob("*.pdf"))
    results = []
    for p in pdf_paths:
        r = analyze_pdf(p)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False))

    out = Path(__file__).parent / "pdf_scan_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    n = len(results)
    n_highlight = sum(1 for r in results if r["highlight_annot_pages"] > 0)
    n_vecrect = sum(1 for r in results if r["vector_rect_with_text_pages"] > 0)
    n_rasterized = sum(
        1 for r in results if r["fullpage_image_pages"] > 0 and r["text_pages"] == 0
    )
    n_texty = sum(1 for r in results if r["text_pages"] > 0)
    n_error = sum(1 for r in results if r["error"])

    print("=== summary ===")
    print(f"total_pdfs={n}")
    print(f"pdfs_with_highlight_annot={n_highlight}")
    print(f"pdfs_with_vector_rect_and_text_candidate={n_vecrect}")
    print(f"pdfs_fully_rasterized_no_text={n_rasterized}")
    print(f"pdfs_with_some_extractable_text={n_texty}")
    print(f"pdfs_with_read_error={n_error}")


if __name__ == "__main__":
    main()
