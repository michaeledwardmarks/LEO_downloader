#!/usr/bin/env python3
"""Compare two LEO export folders, for example the Python tool's output and the browser extension's output.

    python3 compare_exports.py FOLDER_A FOLDER_B
    python3 compare_exports.py FOLDER_A FOLDER_B --project 26825 --project 26731

Only project folders ("<id> - <title>") are compared. The two tools shorten long project and form names
differently (the extension is shorter, to keep paths inside the Windows limit), so by default files are matched
by project ID, form number and content type, not by name:

    zip              <project id> / <form number> / zip
    letter           <project id> / letters / date stamp / the attachment's own file name
    submitted copy   <project id> / <form number> / date stamp / the attachment's own file name
    note             <project id> / <form number> / note name

Use --strict to require identical paths instead. For each file the result is one of:

    same         present in both with identical content (names may differ, see above)
    only in A    present in A but not in B
    only in B    present in B but not in A
    differs      present in both, content differs (for a zip: the list of files inside, with sizes and CRCs)

Zips are compared by what is inside them, not by their bytes, because LEO builds a new zip on every request.
The text notes ("Form never submitted.txt", "No files held in LEO.txt") are compared without their "Checked:" line.
Files of zero size and zips that cannot be opened are listed as problems, whichever folder they are in.

Needs only Python 3.8 or later. A full report is written to compare_report.csv.
"""

import argparse
import csv
import hashlib
import re
import sys
import zipfile
from pathlib import Path

SKIP_DIRS = {".browser_profile", "_tidy_removed", "_debug"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}
STAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{4}|undated) - ")
COPY_STAMP_RE = re.compile(r" submitted form (\d{4}-\d{2}-\d{2} \d{4}|undated) - ")
STAMP = r"(\d{4}-\d{2}-\d{2} \d{4}|undated)"
LETTER_RE = re.compile(rf"^{STAMP} - .* - (.+)$")
COPY_RE = re.compile(rf"^.* - submitted form {STAMP} - (.+)$")
NOTE_NAMES = {"Form never submitted.txt", "No files held in LEO.txt"}


def match_key(rel, ignore_dates):
    """Identify a file by what it is, so that differently shortened names still match."""
    parts = rel.split("/")
    pid = re.match(r"(\d+) - ", parts[0])[1]
    name = parts[-1]
    stamp = (lambda s: "") if ignore_dates else (lambda s: s)
    if len(parts) == 2:
        return (pid, "", name)
    if parts[1] == "Approval letters":
        m = LETTER_RE.match(name)
        return (pid, "letters", stamp(m[1]), m[2]) if m else (pid, "letters", name)
    m = re.match(r"^(\d+) - ", parts[1])
    form = m[1] if m else parts[1]
    if name.endswith(" - all documents.zip"):
        return (pid, form, "zip")
    if name in NOTE_NAMES:
        return (pid, form, name)
    m = COPY_RE.match(name)
    if m:
        return (pid, form, "copy", stamp(m[1]), m[2])
    return (pid, form, name)


def collect(root, projects, ignore_dates, strict):
    """key -> (relative path, file path), for files inside project folders only."""
    grouped = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if len(rel.parts) < 2 or rel.parts[0] in SKIP_DIRS or p.name in SKIP_FILES:
            continue
        m = re.match(r"^(\d+) - ", rel.parts[0])
        if not m or (projects and m[1] not in projects):
            continue
        relpath = rel.as_posix()
        if strict:
            head, _, name = relpath.rpartition("/")
            if ignore_dates:
                name = STAMP_RE.sub("", name, count=1)
                name = COPY_STAMP_RE.sub(" submitted form - ", name, count=1)
            key = (f"{head}/{name}",)
        else:
            key = match_key(relpath, ignore_dates)
        grouped.setdefault(key, []).append((relpath, p))
    found = {}
    for key, items in grouped.items():
        for i, item in enumerate(sorted(items)):
            found[key if i == 0 else key + (f"#{i + 1}",)] = item
    return found


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(path):
    """(kind, value): equal fingerprints mean the same content. A problem is reported as kind 'bad'."""
    if path.stat().st_size == 0:
        return ("bad", "zero-byte file")
    if path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as z:
                return ("zip", tuple(sorted((i.filename, i.file_size, i.CRC) for i in z.infolist() if not i.filename.endswith("/"))))
        except zipfile.BadZipFile:
            return ("bad", "zip cannot be opened")
    if path.suffix.lower() == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace")
        return ("txt", "\n".join(l for l in text.splitlines() if not l.startswith("Checked:")))
    return ("file", sha256(path))


def describe_difference(fa, fb):
    if fa[0] == "bad" or fb[0] == "bad":
        return " | ".join(f"{label}: {f[1]}" for label, f in (("A", fa), ("B", fb)) if f[0] == "bad")
    if fa[0] == "zip" and fb[0] == "zip":
        a = {n: (s, c) for n, s, c in fa[1]}
        b = {n: (s, c) for n, s, c in fb[1]}
        only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
        changed = sorted(n for n in set(a) & set(b) if a[n] != b[n])
        parts = [f"{len(a)} files in A, {len(b)} in B"]
        if only_a:
            parts.append("only in A: " + "; ".join(only_a[:3]) + (" ..." if len(only_a) > 3 else ""))
        if only_b:
            parts.append("only in B: " + "; ".join(only_b[:3]) + (" ..." if len(only_b) > 3 else ""))
        if changed:
            parts.append("different content: " + "; ".join(changed[:3]) + (" ..." if len(changed) > 3 else ""))
        return " | ".join(parts)
    return "content differs"


def main():
    ap = argparse.ArgumentParser(description="Compare two LEO export folders.", epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", help="first export folder (A)")
    ap.add_argument("b", help="second export folder (B)")
    ap.add_argument("--project", action="append", default=[], metavar="ID", help="only this Project ID (repeat for several)")
    ap.add_argument("--strict", action="store_true", help="require identical paths (names) as well as identical content")
    ap.add_argument("--ignore-dates", action="store_true",
                    help="ignore the date stamp at the start of letter names, for comparing an export made before the date fix")
    ap.add_argument("--report", default="compare_report.csv", help="where to write the full report (default compare_report.csv)")
    ap.add_argument("--all", action="store_true", help="print every difference, not only the first 15 of each kind")
    args = ap.parse_args()

    ra, rb = Path(args.a).expanduser().resolve(), Path(args.b).expanduser().resolve()
    for r in (ra, rb):
        if not r.is_dir():
            print(f"{r} is not a folder.")
            return 1
    projects = set(args.project)
    fa, fb = collect(ra, projects, args.ignore_dates, args.strict), collect(rb, projects, args.ignore_dates, args.strict)

    rows, counts = [], {"same": 0, "only in A": 0, "only in B": 0, "differs": 0}
    problems, renamed = [], []
    for key in sorted(set(fa) | set(fb), key=str):
        ra_, rb_ = (fa[key][0] if key in fa else ""), (fb[key][0] if key in fb else "")
        if key in fa and key not in fb:
            status, detail = "only in A", ""
        elif key in fb and key not in fa:
            status, detail = "only in B", ""
        else:
            pa, pb = fingerprint(fa[key][1]), fingerprint(fb[key][1])
            if pa == pb and pa[0] != "bad":
                status, detail = "same", ""
                if ra_ != rb_:
                    renamed.append((ra_, rb_))
            else:
                status, detail = "differs", describe_difference(pa, pb)
        counts[status] += 1
        rows.append((ra_ or rb_, status, ra_, rb_, detail))
        for label, table in (("A", fa), ("B", fb)):
            if key in table:
                kind, value = fingerprint(table[key][1])
                if kind == "bad":
                    problems.append((label, table[key][0], value))

    with open(args.report, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["path", "status", "path_in_A", "path_in_B", "detail"])
        w.writerows(rows)

    pa_ids = {re.match(r"^(\d+)", v[0].split("/")[0])[1] for v in fa.values()}
    pb_ids = {re.match(r"^(\d+)", v[0].split("/")[0])[1] for v in fb.values()}
    print(f"A: {ra}\n   {len(fa)} files in {len(pa_ids)} projects")
    print(f"B: {rb}\n   {len(fb)} files in {len(pb_ids)} projects")
    if projects:
        print(f"Restricted to project(s): {', '.join(sorted(projects))}")
    print(f"\nsame: {counts['same']}" + (f" (of which {len(renamed)} under a different name or folder)" if renamed else "") + f" | differs: {counts['differs']} | only in A: {counts['only in A']} | only in B: {counts['only in B']} | problems: {len(problems)}")
    limit = None if args.all else 15
    for status in ("differs", "only in A", "only in B"):
        sel = [r for r in rows if r[1] == status]
        if sel:
            print(f"\n{status} ({len(sel)}):")
            for path, _, _, _, detail in sel[:limit]:
                print(f"  {path}" + (f"\n      {detail}" if detail else ""))
            if limit and len(sel) > limit:
                print(f"  ... {len(sel) - limit} more in {args.report}")
    if renamed and not args.strict:
        print(f"\nExamples of files matched under a different name (A -> B):")
        for a_, b_ in renamed[:3]:
            print(f"  {a_}\n  -> {b_}")
    if problems:
        print(f"\nproblems ({len(problems)}):")
        for label, key, value in problems[:limit]:
            print(f"  [{label}] {key}: {value}")
    print(f"\nFull report: {args.report}")
    return 0 if not (counts["differs"] or counts["only in A"] or counts["only in B"] or problems) else 2


if __name__ == "__main__":
    sys.exit(main())
