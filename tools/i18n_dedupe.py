"""Remove duplicate keys from the EN literal in app/i18n.py.

Duplicates are harmless when the values match, but they hide mistakes: whichever
entry comes last silently wins.  This keeps the first occurrence of each key and
deletes later ones (which only happens when the values are identical).

    python tools\\i18n_dedupe.py [--dry-run]
"""

from __future__ import annotations

import argparse
import ast
import io
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(PROJECT, "app", "i18n.py")


def line_offsets(text: str):
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def char_column(text: str, line_no: int, byte_column: int) -> int:
    line = text.splitlines(keepends=True)[line_no - 1]
    if byte_column <= 0:
        return 0
    prefix = line.encode("utf-8")[:byte_column]
    while prefix:
        try:
            return len(prefix.decode("utf-8"))
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    text = io.open(PATH, encoding="utf-8").read()
    tree = ast.parse(text)

    literal = None
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "EN":
            literal = node.value
        elif isinstance(node, ast.Assign) and \
                any(getattr(t, "id", None) == "EN" for t in node.targets):
            literal = node.value
    if literal is None:
        print("未找到 EN 字典")
        return 2

    seen = {}
    removals = []
    for key_node, value_node in zip(literal.keys, literal.values):
        if not isinstance(key_node, ast.Constant):
            continue
        key = key_node.value
        if key in seen:
            old_value = seen[key]
            if not (isinstance(old_value, ast.Constant) and
                    isinstance(value_node, ast.Constant) and
                    old_value.value == value_node.value):
                print("  !! %s 的两次取值不同，保留不动" % key)
                continue
            removals.append((key_node, value_node))
        else:
            seen[key] = value_node

    if not removals:
        print("没有需要删除的重复键")
        return 0

    offsets = line_offsets(text)
    spans = []
    for key_node, value_node in removals:
        start_line, start_byte = key_node.lineno, key_node.col_offset
        # include the trailing comma
        end_line, end_byte = value_node.end_lineno, value_node.end_col_offset
        start = offsets[start_line - 1] + char_column(text, start_line, start_byte)
        end = offsets[end_line - 1] + char_column(text, end_line, end_byte)
        while end < len(text) and text[end] in " \t":
            end += 1
        if end < len(text) and text[end] == ",":
            end += 1
        while end < len(text) and text[end] == "\n":
            end += 1
        spans.append((start, end, key_node.value))

    for start, end, key in sorted(spans, reverse=True):
        print("  删除重复键: %s" % key)
        text = text[:start] + text[end:]

    ast.parse(text)  # fail loudly rather than write broken source
    if not args.dry_run:
        io.open(PATH, "w", encoding="utf-8").write(text)
        print("已写入 %s" % PATH)
    else:
        print("(dry-run，未写入)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
