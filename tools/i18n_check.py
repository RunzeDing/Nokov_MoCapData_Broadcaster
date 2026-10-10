"""Report Chinese UI strings that are not covered by the translation table.

    python tools\\i18n_check.py
    python tools\\i18n_check.py --missing-only

Two kinds of finding are reported:

* **未包裹** - a Chinese literal that is never passed to ``tr()``, so it will
  always render in Chinese.
* **未翻译** - a literal that is wrapped but missing from ``app/i18n.py``; it
  falls back to Chinese.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(PROJECT, "app")
HAN = re.compile(r"[\u4e00-\u9fff]")

#: files whose Chinese text is developer-facing and deliberately untranslated
SKIP_PATHS = {
    os.path.join(APP, "i18n.py"),
}


def docstrings(tree: ast.AST) -> set:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                found.add(id(body[0].value))
    return found


def wrapped_ids(tree: ast.AST) -> set:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "tr":
            for arg in node.args:
                if isinstance(arg, ast.Constant):
                    found.add(id(arg))
    return found


def load_table() -> set:
    sys.path.insert(0, PROJECT)
    from app.i18n import EN
    return set(EN.keys())


def duplicate_keys() -> dict:
    """Keys defined more than once in the EN literal.

    A duplicated key silently overrides the earlier one, which is how the
    "stop broadcast" button once ended up labelled "Broadcast stopped".
    """
    import collections

    path = os.path.join(APP, "i18n.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    literal = None
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "EN":
            literal = node.value
        elif isinstance(node, ast.Assign) and \
                any(getattr(t, "id", None) == "EN" for t in node.targets):
            literal = node.value
    if literal is None:
        return {}
    counts = collections.Counter(
        key.value for key in literal.keys if isinstance(key, ast.Constant)
    )
    return {key: count for key, count in counts.items() if count > 1}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--missing-only", action="store_true",
                        help="只报告已包裹但表中缺失的字符串")
    args = parser.parse_args()

    table = load_table()
    print("翻译表条目: %d" % len(table))

    duplicates = duplicate_keys()
    if duplicates:
        print("\n!! 翻译表中有 %d 个重复键（后者会覆盖前者）:" % len(duplicates))
        for key, count in sorted(duplicates.items(), key=lambda item: -item[1]):
            print("   %d 次 | %s" % (count, key))
    else:
        print("重复键: 0")
    print()

    unwrapped = {}
    missing = {}
    total = 0

    for root, _dirs, files in os.walk(APP):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            if path in SKIP_PATHS:
                continue
            relative = os.path.relpath(path, os.path.dirname(APP))
            tree = ast.parse(open(path, encoding="utf-8").read())
            doc_ids = docstrings(tree)
            wrapped = wrapped_ids(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                if id(node) in doc_ids or not HAN.search(node.value):
                    continue
                total += 1
                if id(node) in wrapped:
                    if node.value not in table:
                        missing.setdefault(relative, []).append((node.lineno, node.value))
                else:
                    unwrapped.setdefault(relative, []).append((node.lineno, node.value))

    if not args.missing_only:
        print("=" * 72)
        print("未包裹 tr() 的中文字面量（共 %d 条）"
              % sum(len(v) for v in unwrapped.values()))
        print("=" * 72)
        for relative, items in sorted(unwrapped.items()):
            print("\n-- %s (%d)" % (relative, len(items)))
            for lineno, value in items:
                print("  %5d | %s" % (lineno, value.replace("\n", "\\n")[:110]))

    print()
    print("=" * 72)
    print("已包裹但翻译表缺失（共 %d 条）" % sum(len(v) for v in missing.values()))
    print("=" * 72)
    for relative, items in sorted(missing.items()):
        print("\n-- %s (%d)" % (relative, len(items)))
        for lineno, value in items:
            print("  %5d | %r" % (lineno, value[:110]))

    print("\n统计: 中文字面量 %d 条，未包裹 %d 条，未翻译 %d 条"
          % (total, sum(len(v) for v in unwrapped.values()),
             sum(len(v) for v in missing.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
