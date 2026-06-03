#!/usr/bin/env python3
"""Set or add SetFontSize in every Show/Hide block of a PoE loot filter file."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BLOCK_HEADER_RE = re.compile(r"^(#)?(Show|Hide)\s")
SET_FONTSIZE_RE = re.compile(r"^(#?\t)SetFontSize \d+\s*$")
ACTION_LINE_RE = re.compile(r"^(#?\t)(Set|Play|Minimap|Custom|Disable|Continue)")


def split_line(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def block_body_prefix(lines: list[str]) -> str:
    for line in lines[1:]:
        content, _ = split_line(line)
        if content.startswith("#\t"):
            return "#\t"
        if content.startswith("\t"):
            return "\t"
    return "\t"


def process_block(lines: list[str], fontsize: int) -> list[str]:
    if not lines or not BLOCK_HEADER_RE.match(split_line(lines[0])[0]):
        return lines

    fontsize_idx: int | None = None
    for i in range(1, len(lines)):
        content, _ = split_line(lines[i])
        if SET_FONTSIZE_RE.match(content):
            fontsize_idx = i
            break

    if fontsize_idx is not None:
        content, ending = split_line(lines[fontsize_idx])
        prefix = SET_FONTSIZE_RE.match(content).group(1)
        lines[fontsize_idx] = f"{prefix}SetFontSize {fontsize}{ending}"
        return lines

    insert_idx = len(lines)
    prefix = block_body_prefix(lines)
    for i in range(1, len(lines)):
        content, _ = split_line(lines[i])
        if ACTION_LINE_RE.match(content):
            insert_idx = i
            prefix = ACTION_LINE_RE.match(content).group(1)
            break

    _, ending = split_line(lines[insert_idx - 1] if insert_idx > 0 else lines[0])
    new_line = f"{prefix}SetFontSize {fontsize}{ending}"
    lines.insert(insert_idx, new_line)
    return lines


def process_filter(text: str, fontsize: int) -> str:
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    block: list[str] = []

    for line in lines:
        content, _ = split_line(line)
        if BLOCK_HEADER_RE.match(content):
            result.extend(process_block(block, fontsize))
            block = [line]
        elif block:
            if content.startswith("\t") or content.startswith("#\t"):
                block.append(line)
            else:
                result.extend(process_block(block, fontsize))
                block = []
                result.append(line)
        else:
            result.append(line)

    result.extend(process_block(block, fontsize))
    return "".join(result)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set SetFontSize for every Show/Hide block in a loot filter file."
    )
    parser.add_argument(
        "-fs",
        "--fontsize",
        type=int,
        required=True,
        metavar="SIZE",
        help="Font size to apply (e.g. 42)",
    )
    parser.add_argument(
        "-src",
        type=Path,
        required=True,
        metavar="PATH",
        help="Source .filter file",
    )
    parser.add_argument(
        "-o",
        dest="des",
        type=Path,
        required=True,
        metavar="PATH",
        help="Destination .filter file",
    )
    args = parser.parse_args()

    if args.fontsize <= 0:
        print("error: fontsize must be a positive integer", file=sys.stderr)
        return 1

    if not args.src.is_file():
        print(f"error: file not found: {args.src}", file=sys.stderr)
        return 1

    text = args.src.read_text(encoding="utf-8")
    updated = process_filter(text, args.fontsize)

    args.des.write_text(updated, encoding="utf-8", newline="")
    print(f"Updated {args.des} (SetFontSize -> {args.fontsize})")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
