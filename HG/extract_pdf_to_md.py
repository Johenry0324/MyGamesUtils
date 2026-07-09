#!/usr/bin/env python3
"""Extract HK IPO prospectus PDF to chapter-structured Markdown with tables."""

import re
import fitz
from pathlib import Path
from collections import defaultdict

PDF_PATH = Path(__file__).parent / "sehk26070300013_c.pdf"
OUT_PATH = Path(__file__).parent / "sehk26070300013_c.md"

# Main chapters from document TOC (page numbers are document footer numbers)
CHAPTERS = [
    ("封面及警告", None, "i"),
    ("預期時間表", "i", "ii"),
    ("目錄", "ii", "1"),
    ("概要", "1", "19"),
    ("釋義", "19", "29"),
    ("技術詞彙表", "29", "36"),
    ("前瞻性陳述", "36", "37"),
    ("風險因素", "37", "63"),
    ("豁免及免除", "63", "71"),
    ("有關本文件及全球發售的資料", "71", "75"),
    ("董事及參與全球發售的各方", "75", "78"),
    ("公司資料", "78", "80"),
    ("歷史、發展及公司架構", "80", "106"),
    ("行業概覽", "106", "118"),
    ("監管概覽", "118", "136"),
    ("業務", "136", "201"),
    ("與控股股東的關係", "201", "205"),
    ("關連交易", "205", "208"),
    ("董事及高級管理層", "208", "220"),
    ("股本", "220", "222"),
    ("主要股東", "222", "225"),
    ("財務資料", "225", "261"),
    ("未來計劃及所得款項用途", "261", "264"),
    ("承銷", "264", "275"),
    ("全球發售的架構", "275", "284"),
    ("如何申請香港發售股份", "284", "I-1"),
    ("附錄一 — 會計師報告", "I-1", "II-1"),
    ("附錄二 — 未經審計備考財務資料", "II-1", "III-1"),
    ("附錄三 — 稅項及外匯", "III-1", "IV-1"),
    ("附錄四 — 主要法律及監管條文概要", "IV-1", "V-1"),
    ("附錄五 — 公司章程概要", "V-1", "VI-1"),
    ("附錄六 — 法定及一般資料", "VI-1", "VII-1"),
    ("附錄七 — 送呈香港公司註冊處處長及展示文件及備查文件", "VII-1", None),
]

SKIP_LINES = {
    "重要提示",
    "本文件為草擬本。所載資料並不完整及可能會作出重大變動。",
    "閱讀本文件內任何資料時，請一併細閱本文件封底「警告」一節。",
    "本文件為草擬本。其所載資料並不完整及可作更改。閱讀本文件有關資料時，必須一併細閱本文件首頁「警告」一節。",
}

PAGE_FOOTER_RE = re.compile(r"^[\u2013\-–—]\s*(.+?)\s*[\u2013\-–—]$")
SUBHEADING_RE = re.compile(r"^#{1,4}\s")


def normalize(text: str) -> str:
    text = text.replace("\u2002", " ").replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def page_num_key(num: str) -> tuple:
    """Sortable key for document page numbers (1, 19, I-1, etc.)."""
    num = num.strip()
    if re.match(r"^[IVXLC]+-\d+$", num):
        roman, n = num.split("-")
        roman_map = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7}
        return (2, roman_map.get(roman, 99), int(n))
    roman_map = {"i": 0, "ii": 1, "iii": 2, "iv": 3}
    if num in roman_map:
        return (0, roman_map[num], 0)
    if num.isdigit():
        return (1, int(num), 0)
    return (3, num, 0)


def build_page_map(doc: fitz.Document) -> dict[str, int]:
    mapping = {}
    for idx in range(len(doc)):
        for line in doc[idx].get_text().split("\n"):
            line = line.strip()
            m = PAGE_FOOTER_RE.match(line)
            if m:
                mapping[m.group(1).strip()] = idx
                break
    return mapping


def page_range_indices(page_map: dict, start: str | None, end: str | None, total: int) -> range:
    if start is None:
        start_idx = 0
    else:
        start_idx = page_map.get(start, 0)
    if end is None:
        end_idx = total
    else:
        end_idx = page_map.get(end, total)
    return range(start_idx, end_idx)


def cluster_rows(spans: list[tuple[float, float, str]], y_tol: float = 4.0) -> list[list[tuple[float, str]]]:
    """Group text spans into rows by y coordinate."""
    if not spans:
        return []
    spans = sorted(spans, key=lambda s: (s[1], s[0]))
    rows: list[list[tuple[float, str]]] = []
    current_y = None
    current_row: list[tuple[float, str]] = []
    for x, y, text in spans:
        if not text.strip():
            continue
        if current_y is None or abs(y - current_y) <= y_tol:
            current_row.append((x, text))
            if current_y is None:
                current_y = y
        else:
            if current_row:
                rows.append(sorted(current_row, key=lambda c: c[0]))
            current_row = [(x, text)]
            current_y = y
    if current_row:
        rows.append(sorted(current_row, key=lambda c: c[0]))
    return rows


def row_to_table_line(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def detect_table_blocks(rows: list[list[tuple[float, str]]]) -> list[str]:
    """Convert multi-column rows into markdown tables when layout suggests tabular data."""
    if not rows:
        return []

    multi_col_rows = [r for r in rows if len(r) >= 2]
    if len(multi_col_rows) < 3:
        return [" ".join(c[1] for c in r) for r in rows]

    # Determine column x positions from rows with most cells
    col_counts = defaultdict(int)
    for r in rows:
        col_counts[len(r)] += 1
    target_cols = max(col_counts, key=lambda k: k if k >= 2 else 0)
    if target_cols < 2:
        return [" ".join(c[1] for c in r) for r in rows]

    # Collect x anchors from rows matching target column count
    x_samples = []
    for r in rows:
        if len(r) == target_cols:
            x_samples.append([c[0] for c in r])
    if not x_samples:
        return [" ".join(c[1] for c in r) for r in rows]

    col_x = [sum(xs[i] for xs in x_samples) / len(x_samples) for i in range(target_cols)]

    def assign_col(x: float) -> int:
        return min(range(len(col_x)), key=lambda i: abs(x - col_x[i]))

    output = []
    table_buffer: list[list[str]] = []
    in_table = False

    def flush_table():
        nonlocal table_buffer, in_table, output
        if not table_buffer:
            in_table = False
            return
        col_n = max(len(r) for r in table_buffer)
        for r in table_buffer:
            while len(r) < col_n:
                r.append("")
        output.append(row_to_table_line(table_buffer[0]))
        output.append(row_to_table_line(["---"] * col_n))
        for r in table_buffer[1:]:
            output.append(row_to_table_line(r))
        output.append("")
        table_buffer = []
        in_table = False

    for r in rows:
        if len(r) >= 2 and len(r) <= target_cols + 1:
            cells = [""] * target_cols
            for x, text in r:
                ci = assign_col(x)
                if ci < target_cols:
                    cells[ci] = (cells[ci] + " " + text).strip() if cells[ci] else text
            table_buffer.append(cells)
            in_table = True
        else:
            flush_table()
            line = " ".join(c[1] for c in r)
            if line:
                output.append(line)
    flush_table()
    return output


def extract_page_content(page: fitz.Page) -> str:
    """Extract page text; join same-line spans to preserve table rows."""
    blocks = page.get_text("dict")["blocks"]
    spans: list[tuple[float, float, str]] = []
    for block in blocks:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                t = normalize(span["text"])
                if t:
                    spans.append((span["bbox"][0], span["bbox"][1], t))

    lines: list[str] = []
    for row in cluster_rows(spans):
        joined = " ".join(c[1] for c in row)
        if not joined or joined in SKIP_LINES:
            continue
        if PAGE_FOOTER_RE.match(joined):
            continue
        if joined == "HOSIN Global Electronics Co , Ltd":
            continue
        if joined in ("深圳宏芯宇電子股份有限公司", "（於中華人民共和國註冊成立的股份有限公司）"):
            continue
        lines.append(joined)
    return "\n".join(lines)


def merge_paragraphs(text: str) -> str:
    """Join PDF line breaks into continuous paragraphs."""
    lines = text.split("\n")
    merged: list[str] = []
    buf = ""

    def flush():
        nonlocal buf
        if buf:
            merged.append(buf)
            buf = ""

    for line in lines:
        s = line.strip()
        if not s:
            flush()
            continue
        if s.startswith("|") or PAGE_FOOTER_RE.match(s):
            flush()
            merged.append(s)
            continue
        if is_table_like_line(s) or is_heading_line(s):
            flush()
            merged.append(s)
            continue
        if not buf:
            buf = s
            continue
        if should_merge(buf, s):
            buf += s
        else:
            flush()
            buf = s
    flush()
    return "\n\n".join(merged)


def is_table_like_line(s: str) -> bool:
    if s.startswith("|"):
        return True
    if re.search(r"\.{4,}", s) and re.search(r"[\d,]{4,}", s):
        return True
    if re.match(r"^(附註|20\d{2}年|人民幣千元|（未經審計）)", s):
        return True
    if re.match(r"^[\(（]?[\d,\.\-\(\)]+[\)）]?\s*[\(（]?[\d,\.\-\(\)]+", s):
        return True
    return False


def is_heading_line(s: str) -> bool:
    if len(s) > 60:
        return False
    if s.endswith(("。", "；", "：", "!", "?", "！", "？")):
        return False
    if re.match(r"^[\(（][a-z\d]+[\)）]", s, re.I):
        return False
    if re.match(r"^(附錄[一二三四五六七八九十\d]+|第[一二三四五六七八九十\d]+[章节節])", s):
        return True
    keywords = (
        "概覽", "綜合損益表", "綜合全面收入表", "綜合財務狀況表", "綜合現金流量表",
        "綜合權益變動表", "非流動資產", "流動資產", "流動負債", "非流動負債",
    )
    return s in keywords or any(s.startswith(k) and len(s) < len(k) + 20 for k in keywords)


def should_merge(prev: str, curr: str) -> bool:
    if re.match(r"^[\(（][a-zivx\d]+[\)）]", curr, re.I):
        return False
    if re.match(r"^[•·●\-\*]", curr):
        return False
    if re.match(r"^\d+\.", curr):
        return False
    if prev.endswith(("。", "；", "：", "！", "？", ".", ";", "!", "?", "」", "』", "）", ")")):
        return False
    if re.match(r"^[\d,\(\)\-\.\s%]+$", curr):
        return False
    if len(prev) < 25 and not prev.endswith(("，", ",", "、")):
        return False
    return True


def parse_table_row(s: str) -> list[str] | None:
    if not (re.search(r"(?:\.\s*){4,}", s) or len(re.findall(r"[\d,]+", s)) >= 3):
        return None
    tokens = s.split()
    num_tokens: list[str] = []
    for t in reversed(tokens):
        if re.match(r"^\(?\-?[\d,]+\)?$", t):
            num_tokens.insert(0, t)
        elif t in ("—", "-", "–"):
            num_tokens.insert(0, t)
        else:
            break
    if len(num_tokens) >= 2:
        label = s[: s.rfind(num_tokens[0])].strip()
        label = re.sub(r"(?:\s*\.\s*)+$", "", label).strip()
        if label:
            return [label] + num_tokens
    return None


def format_financial_tables(text: str) -> str:
    """Convert inline financial statement rows into markdown tables."""
    lines = text.split("\n")
    out: list[str] = []
    table_buf: list[list[str]] = []
    header_buf: list[str] = []

    def flush_table():
        nonlocal table_buf, header_buf
        if len(table_buf) < 2:
            out.extend(header_buf)
            for row in table_buf:
                out.append(" ".join(row))
        else:
            out.extend(header_buf)
            col_n = max(len(r) for r in table_buf)
            for r in table_buf:
                while len(r) < col_n:
                    r.append("")
            out.append("")
            out.append(row_to_table_line(table_buf[0]))
            out.append(row_to_table_line(["---"] * col_n))
            for r in table_buf[1:]:
                out.append(row_to_table_line(r))
            out.append("")
        table_buf = []
        header_buf = []

    for line in lines:
        s = line.strip()
        if not s:
            flush_table()
            out.append("")
            continue

        row = parse_table_row(s)
        if row:
            table_buf.append(row)
            continue

        if table_buf and re.match(r"^(附註|20\d{2}年|人民幣千元|（未經審計）|截至|於 \d)", s):
            header_buf.append(s)
            continue

        if table_buf and is_heading_line(s):
            flush_table()
            out.append(s)
            continue

        if table_buf:
            flush_table()
        out.append(s)

    flush_table()
    return "\n".join(out)


def postprocess_chapter(text: str) -> str:
    text = merge_paragraphs(text)
    # Financial table markdown conversion only for statement-heavy sections
    if "綜合損益表" in text or "綜合財務狀況表" in text or "附錄一" in text:
        text = format_financial_tables(text)
    return text


def table_to_md(table: list[list]) -> str:
    rows = [[normalize(str(c) if c else "") for c in row] for row in table]
    rows = [r for r in rows if any(c for c in r)]
    if len(rows) < 2:
        return ""
    col_n = max(len(r) for r in rows)
    for r in rows:
        while len(r) < col_n:
            r.append("")
    md = [row_to_table_line(rows[0]), row_to_table_line(["---"] * col_n)]
    md.extend(row_to_table_line(r) for r in rows[1:])
    return "\n".join(md)


def extract_all() -> str:
    parts = [
        "# 深圳宏芯宇電子股份有限公司（HOSIN Global Electronics Co., Ltd）",
        "",
        "## 港股上市申請書（申請版本）",
        "",
    ]

    with fitz.open(PDF_PATH) as doc:
        total = len(doc)
        page_map = build_page_map(doc)
        parts.append(f"> 來源：`sehk26070300013_c.pdf`（共 {total} 頁）")
        parts.extend(["", "---", "", "## 目錄", ""])
        for title, _, _ in CHAPTERS:
            anchor = re.sub(r"\s+", "-", title)
            parts.append(f"- [{title}](#{anchor})")
        parts.extend(["", "---", ""])

        for title, start, end in CHAPTERS:
            indices = page_range_indices(page_map, start, end, total)
            parts.append(f"## {title}")
            parts.append("")
            if start or end:
                pg_label = f"{start or '1'} – {end or '末'}"
                parts.append(f"*頁次：{pg_label}*")
                parts.append("")

            chapter_text = []
            for idx in indices:
                content = extract_page_content(doc[idx])
                if content.strip():
                    chapter_text.append(content)

            body = merge_paragraphs("\n\n".join(chapter_text))
            parts.append(body)
            parts.append("")
            parts.append("---")
            parts.append("")

    return "\n".join(parts)


if __name__ == "__main__":
    print(f"Extracting {PDF_PATH} ...")
    md = extract_all()
    OUT_PATH.write_text(md, encoding="utf-8")
    print(f"Written {OUT_PATH}")
    print(f"  Size: {OUT_PATH.stat().st_size:,} bytes")
    print(f"  Chapters: {len(CHAPTERS)}")
