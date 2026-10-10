"""Wrap user-visible Chinese string literals in ``tr(...)``.

A mechanical refactor is safer than hand-editing hundreds of literals: this
script parses each module with ``ast``, finds every string constant that

* contains a Han character,
* is not a docstring,
* is not already the argument of ``tr(...)``,

and rewrites exactly that source span.  The matching ``from ...i18n import tr``
line is inserted automatically.

    python tools\\i18n_codemod.py --dry-run
    python tools\\i18n_codemod.py
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(PROJECT, "app")
BACKUP = os.path.join(PROJECT, ".buildcache", "app_backup_before_i18n")

HAN = re.compile(r"[\u4e00-\u9fff]")

#: never touch these
SKIP_FILES = {
    os.path.join(APP, "i18n.py"),
}


def docstring_nodes(tree: ast.AST) -> set:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                found.add(id(body[0].value))
    return found


def tr_argument_spans(tree: ast.AST) -> set:
    """ids of constants already wrapped in tr(...)"""
    wrapped = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "tr":
            for arg in node.args:
                if isinstance(arg, ast.Constant):
                    wrapped.add(id(arg))
    return wrapped


def import_line_for(path: str) -> str:
    relative = os.path.relpath(path, PROJECT)
    parts = relative.split(os.sep)
    dots = "." * (len(parts) - 1)
    return "from %si18n import tr" % dots


def ensure_import(source: str, path: str) -> str:
    line = import_line_for(path)
    if line in source:
        return source
    lines = source.splitlines(keepends=True)
    insert_at = 0
    for index, text in enumerate(lines[:40]):
        stripped = text.strip()
        if stripped.startswith("from __future__"):
            insert_at = index + 1
            break
    else:
        # after a leading module docstring, if any
        tree = ast.parse(source)
        if tree.body and isinstance(tree.body[0], ast.Expr) and \
                isinstance(tree.body[0].value, ast.Constant):
            insert_at = tree.body[0].end_lineno
    lines.insert(insert_at, "\n" + line + "\n")
    return "".join(lines)


def process(path: str, dry_run: bool) -> int:
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source)

    docstrings = docstring_nodes(tree)
    wrapped = tr_argument_spans(tree)

    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstrings or id(node) in wrapped:
            continue
        if not HAN.search(node.value):
            continue
        spans.append((node.lineno, node.col_offset, node.end_lineno, node.end_col_offset))

    if not spans:
        return 0

    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    def absolute(line_no: int, byte_column: int) -> int:
        """Convert (line, UTF-8 **byte** column) to a character offset.

        CPython reports ``col_offset`` as a byte offset into the UTF-8 encoded
        line, so any line containing non-ASCII text needs converting before it
        can be used to slice a ``str``.
        """
        try:
            line = lines[line_no - 1]
        except IndexError:
            return len(source)
        if byte_column <= 0:
            return offsets[line_no - 1]
        prefix = line.encode("utf-8")[:byte_column]
        while prefix:
            try:
                return offsets[line_no - 1] + len(prefix.decode("utf-8"))
            except UnicodeDecodeError:
                prefix = prefix[:-1]
        return offsets[line_no - 1]

    spans.sort(key=lambda item: absolute(item[0], item[1]), reverse=True)
    result = source
    for start_line, start_col, end_line, end_col in spans:
        start = absolute(start_line, start_col)
        end = absolute(end_line, end_col)
        literal = result[start:end]
        result = result[:start] + "tr(%s)" % literal + result[end:]

    result = ensure_import(result, path)

    # verify the file still parses before writing
    try:
        ast.parse(result)
    except SyntaxError as exc:  # pragma: no cover - safety net
        print("  !! %s 改写后语法错误，已跳过: %s" % (os.path.basename(path), exc))
        return 0

    if not dry_run:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(result)
    return len(spans)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", action="store_true",
                        help="从备份恢复 app 目录")
    args = parser.parse_args()

    if args.restore:
        if not os.path.isdir(BACKUP):
            print("没有备份: %s" % BACKUP)
            return 2
        shutil.rmtree(APP)
        shutil.copytree(BACKUP, APP)
        print("已从备份恢复 %s" % APP)
        return 0

    if not args.dry_run and not os.path.isdir(BACKUP):
        os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
        shutil.copytree(APP, BACKUP)
        print("已备份 app -> %s" % BACKUP)

    total = 0
    for root, _dirs, files in os.walk(APP):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            if path in SKIP_FILES:
                continue
            count = process(path, args.dry_run)
            if count:
                relative = os.path.relpath(path, PROJECT)
                print("  %-46s %3d 处%s" % (relative, count,
                                            " (dry-run)" if args.dry_run else ""))
                total += count
    print("\n共 %d 处%s" % (total, "（未写入）" if args.dry_run else "已改写"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
