#!/usr/bin/env python3
"""
Export every project from LSHTM Ethics Online (Infonetica LEO) before decommissioning.

For each project in All Projects, for each form in the project tree:
  * Documents tab -> tick all -> "Download Selected" (saved as the form's zip)
  * History tab   -> the attachment on each row that records an approval (favourable opinion,
                     amendment approved by the RGIO, response to a provisional letter approved)
                     (change with --history-pattern, or --history-all); identical files are kept once

Output layout (default, --layout structured):

  <out>/
    34352 - SNAP EOS Survey/
      01 - Ethics Application & CARE Form/
        Ethics Application & CARE Form - all documents.zip
      02 - Amendment Form - 01/
        Amendment Form - 01 - all documents.zip
      03 - Annual Report Form 1/            (forms that share a name are numbered 1, 2, 3 ...)
        Annual Report Form 1 - all documents.zip
      Approval letters/                     (every form's approval letters, newest last)
        2026-10-08 1433 - Ethics Application & CARE Form - Favourable opinion letter.pdf
    export_log.csv      one row per download or problem; also what lets an interrupted run resume
    projects_index.csv  the All Projects list

--layout flat keeps the original layout (everything side by side in the project folder).
--restructure moves an existing flat export into the structured layout without downloading anything.

You log in yourself in the browser window the script opens (SSO/MFA works as normal). Once you are
logged in the window closes and the run continues in a hidden browser with the same session, so nothing
pops up on screen; it reopens only if LEO asks for a login again. Use --headed to keep the window.
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

DEFAULT_BASE = "https://leo.lshtm.ac.uk"
LETTERS_DIR = "Approval letters"                # all approval letters of a project, collated
OTHER_DIR = "Other History attachments"         # restructure only: non-approval and duplicate letters
ALL_DOCS = "all documents"
# When a form's Documents tab lists nothing (LEO says "There are currently no documents listed", as it does for
# closed End of Study forms), the form's own content is only reachable from its History rows. The "Form submitted"
# attachment is then saved into the form's folder as well: (label used in the file name, pattern for the description).
FORM_COPY_ROWS = (("submitted form", re.compile(r"^\s*Form submitted\b", re.I)),)
# History rows are downloaded only when their description matches this (case-insensitive).
# Three wordings record a final approval in LEO's notifications:
#   "... has received a favourable opinion"                       ("(?<!un)" excludes "unfavourable")
#   "Your amendment has been assessed and approved by the RGIO"   (amendment approvals)
#   "Your response to the provisional letter has been approved"   (approval after a provisional opinion)
#   "Form status changed from ... to Study Closed"                (the approval of an End of Study form)
#   "... provisionally approved"                                   (provisional approval letters)
#   "... further clarification has been requested"                 (the committee's provisional opinion letter)
DEFAULT_HISTORY_PATTERN = (r"(?<!un)favourable opinion"
                           r"|approved by the RGIO"
                           r"|response to the provisional letter has been approved"
                           r"|\bto Study Closed\b"
                           r"|provisionally approved"
                           r"|further clarification has been requested")
# Annual Report and Protocol Deviation forms record their outcome as a status change to "Favourable" (or an RGIO
# acceptance) with the letter attached, rather than a "favourable opinion" notification.
STATUS_OUTCOME_FORMS = re.compile(r"^\s*(Annual Report|Protocol Deviation)", re.I)
STATUS_OUTCOME_ROWS = re.compile(r"\bto Favourable\.?\s*$|reviewed and accepted by the RGIO", re.I)

# ---------------------------------------------------------------- file names

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def sanitise(name, maxlen=80):
    """Make a string safe as a file or folder name on Windows, macOS and Linux."""
    name = _BAD.sub("_", " ".join((name or "").split())).strip(" .")
    if len(name) > maxlen:
        name = name[:maxlen].rstrip(" .")
    if name.split(".")[0].upper() in _RESERVED:
        name = "_" + name
    return name or "unnamed"


def sanitise_filename(filename, maxlen=90):
    stem, dot, ext = (filename or "file").rpartition(".")
    if not dot:
        return sanitise(filename, maxlen)
    return sanitise(stem, maxlen - len(ext) - 1) + "." + sanitise(ext, 10)


_WRITTEN = set()


def unique_path(path):
    """Files left by an earlier run are overwritten (a retry replaces its own output);
    a name already written during this run gets ' (2)', ' (3)' ... so nothing is lost."""
    n = 1
    candidate = path
    while str(candidate).lower() in _WRITTEN:
        n += 1
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
    _WRITTEN.add(str(candidate).lower())
    return candidate


def form_display_names(forms):
    """Name each form for its folder and zip. Forms that share a name (for example several
    'Annual Report Form') get ' 1', ' 2', ... in project-tree order. Adds 'display' and 'folder'."""
    counts = {}
    for f in forms:
        base = sanitise(f["name"], 50)
        counts[base] = counts.get(base, 0) + 1
    seen = {}
    for i, f in enumerate(forms, 1):
        base = sanitise(f["name"], 50)
        if counts[base] > 1:
            seen[base] = seen.get(base, 0) + 1
            f["display"] = f"{base} {seen[base]}"
        else:
            f["display"] = base
        f["folder"] = f"{i:02d} - {f['display']}"
    return forms


def date_tag(text):
    """'08/10/2026 14:33' (dd/mm/yyyy) -> '2026-10-08_1433'."""
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})", text or "")
    return f"{m[3]}-{m[2]}-{m[1]}_{m[4]}{m[5]}" if m else "undated"


# ---------------------------------------------------------------- logging / state


class RunLog:
    """export_log.csv is both the record of the run and the resume point: a 'form' row with status
    'complete' or 'needs_review' is written when each form finishes. (Older versions kept this in
    state.json; if that file is present it is read once and copied into the log.)"""
    FIELDS = ["time", "project_id", "project_title", "form_id", "form_name", "item", "file", "status", "detail"]

    def __init__(self, out):
        self.path = out / "export_log.csv"
        self.state = {}
        self.docs = {}          # form id -> status of its last Documents result (ok, empty, error, ...)
        self.docs_project = {}  # form id -> project id
        from_log = {}
        if self.path.exists():
            with open(self.path, newline="", encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    if r.get("item") == "form" and r.get("form_id"):
                        from_log[r["form_id"]] = r["status"]  # later rows win
                    elif r.get("item") == "documents" and r.get("form_id"):
                        self.docs[r["form_id"]] = r["status"]
                        self.docs_project[r["form_id"]] = r["project_id"]
        else:
            with open(self.path, "w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow(self.FIELDS)
        self.state = dict(from_log)

        legacy = out / "state.json"
        if legacy.exists():
            try:
                old = json.loads(legacy.read_text())
            except Exception:
                old = {}
            copied = 0
            for form_id, status in old.items():
                if form_id not in from_log:
                    self.state[form_id] = status
                    self.row({"id": "", "title": ""}, {"id": form_id, "name": ""}, "form", "", status, "copied from state.json")
                    copied += 1
            if copied:
                print(f"Progress for {copied} form(s) copied from state.json into export_log.csv. "
                      "state.json is no longer used and can be deleted.")

    def row(self, project, form, item, file, status, detail=""):
        with open(self.path, "a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow([
                datetime.now().isoformat(timespec="seconds"), project["id"], project["title"],
                form["id"] if form else "", form["name"] if form else "", item, file, status, detail,
            ])
        if item == "documents" and form:
            self.docs[form["id"]] = status
            self.docs_project[form["id"]] = project["id"]
        if status not in ("ok", "info", "scan", "scansummary", "complete"):
            print(f"    [{status}] {item}: {detail}")

    def empty_project_ids(self):
        """Projects holding at least one form whose last Documents result was 'empty'."""
        return {self.docs_project[f] for f, st in self.docs.items() if st == "empty" and f in self.docs_project}

    def set_state(self, project, form, status):
        self.state[form["id"]] = status
        self.row(project, form, "form", "", status)


# ---------------------------------------------------------------- site helpers

BACKGROUND = {"on": False}  # True while running in the hidden browser (no window to type in)


class SessionExpired(Exception):
    """The site sent us to a login page; the browser has to be reopened for a fresh login."""


def looks_like_login(page):
    url = page.url.lower()
    if any(k in url for k in ("login", "signin", "microsoftonline", "adfs", "shibboleth", "/idp", "/saml")):
        return True
    try:
        return page.locator("input[type=password]").count() > 0
    except Exception:
        return False


def wait_for_login(page, base, wait_seconds=600):
    """Return once the signed-in navigation is visible. Polls while the user logs in;
    falls back to an Enter prompt if that takes longer than wait_seconds."""
    nav = "a[href*='/ActivityForm/FolderProjectList/0']"
    page.goto(f"{base}/ActivityForm/Index")
    announced, last_nudge = False, 0.0
    while True:
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if page.locator(nav).count() > 0:
                return
            if not announced:
                print("Log in to LEO in the browser window. The script continues by itself once you are in.")
                announced = True
            # after SSO the site can land on a page other than the Work Area
            if page.url.startswith(base) and "/ActivityForm/Index" not in page.url and time.time() - last_nudge > 8:
                last_nudge = time.time()
                page.goto(f"{base}/ActivityForm/Index")
            page.wait_for_timeout(1000)
        input("\nStill not logged in. Log in in the browser window, then press Enter here... ")
        page.goto(f"{base}/ActivityForm/Index")


def list_projects(page, base):
    """Read every row of All Projects, clicking through the DataTables pagination."""
    page.goto(f"{base}/ActivityForm/FolderProjectList/0")
    page.wait_for_selector("#projectTableView tbody tr.project-row")
    projects = {}
    while True:
        rows = page.locator("#projectTableView tbody tr.project-row")
        first_id = rows.first.get_attribute("data-projectid")
        for i in range(rows.count()):
            r = rows.nth(i)
            pid = r.get_attribute("data-projectid")
            projects[pid] = {
                "id": pid,
                "form_id": r.get_attribute("data-userprojectformid"),
                "title": " ".join(r.locator("a.project-link").inner_text().split()),
                "owner": " ".join(r.locator("td").nth(3).inner_text().split()),
                "is_owner": r.get_attribute("data-owner") == "True",
                "can_access": r.get_attribute("data-canaccess") == "True",
            }
        nxt = page.locator("#projectTableView_next")
        if nxt.count() == 0 or "disabled" in (nxt.get_attribute("class") or ""):
            break
        nxt.click()
        page.wait_for_function(
            "([sel, old]) => { const r = document.querySelector(sel); return r && r.dataset.projectid !== old; }",
            arg=["#projectTableView tbody tr.project-row", first_id],
        )
    info = page.locator("#projectTableView_info").inner_text()
    m = re.search(r"of ([\d,]+) entries", info)
    if m and int(m[1].replace(",", "")) != len(projects):
        print(f"WARNING: table says {m[1]} entries but {len(projects)} were read.")
    return list(projects.values())


def read_tree(page):
    """Forms in the project tree, parent before child. Tree root (ProjectView link) is not a form."""
    items = page.eval_on_selector_all(
        "div.well.tree a[href*='/Project/Index/']",
        """els => els.map(a => {
               let depth = 0, e = a;
               while (e) { if (e.tagName === 'UL') depth++; e = e.parentElement; }
               return {href: a.href, name: a.textContent.trim(), depth};
           })""",
    )
    forms, seen = [], set()
    for it in items:
        m = re.search(r"/Project/Index/(\d+)", it["href"])
        if m and m[1] not in seen:
            seen.add(m[1])
            forms.append({"id": m[1], "name": re.sub(r"[\s\-]+$", "", " ".join(it["name"].split())), "depth": it["depth"] - 2})
    return forms


def open_form(page, base, form_id, retried=False):
    page.goto(f"{base}/Project/Index/{form_id}")
    try:
        page.wait_for_selector("#documents_tab", timeout=20000)
    except PWTimeout:
        if BACKGROUND["on"]:
            if looks_like_login(page):
                raise SessionExpired()
            raise
        if retried:
            raise
        input("\nThe form page did not load (session expired?). Log in again in the browser, then press Enter... ")
        open_form(page, base, form_id, retried=True)


def show_all_entries(container):
    """If the table has a 'show N entries' selector, choose the largest option."""
    sel = container.locator("select[name$='_length']")
    if sel.count() == 0:
        return
    values = sel.first.locator("option").evaluate_all("o => o.map(x => x.value)")
    nums = [int(v) for v in values if re.fullmatch(r"-?\d+", v)]
    if nums:
        best = "-1" if -1 in nums else str(max(nums))
        sel.first.select_option(best)
        container.page.wait_for_timeout(500)


def total_entries(container):
    info = container.locator(".dataTables_info")
    if info.count():
        m = re.search(r"of ([\d,]+) entries", info.first.inner_text())
        if m:
            return int(m[1].replace(",", ""))
    return None


# ---------------------------------------------------------------- downloads

_DOWNLOADS = []


def _on_download(download):
    _DOWNLOADS.append(download)


def install_download_listener(ctx):
    """Collect download events from every tab, including popups opened by a button."""
    for pg in ctx.pages:
        pg.on("download", _on_download)
    ctx.on("page", lambda pg: pg.on("download", _on_download))


def capture_download(page, trigger, timeout_s):
    """Run trigger() (a click) and return the Download it starts, from whichever tab."""
    _DOWNLOADS.clear()
    trigger()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _DOWNLOADS:
            d = _DOWNLOADS.pop(0)
            for pg in list(page.context.pages):
                if pg is not page:
                    try:
                        pg.close()
                    except Exception:
                        pass
            return d
        page.wait_for_timeout(200)
    raise PWTimeout(f"no download started within {timeout_s}s")


NO_ITEMS_RE = re.compile(r"\b(no|not)\b.*\b(documents?|data|records?|attachments?|entries)\b", re.I)


def open_tab(page, tab_selector, container_selector, waits=(8000, 12000, 20000)):
    """Click a tab and wait for its table. If nothing loads (for example the click arrived before
    LEO's own script was ready), click again. Returns (container, loaded, text shown instead)."""
    cont = page.locator(container_selector)
    for wait in waits:
        page.click(tab_selector)
        try:
            cont.locator("table").first.wait_for(state="visible", timeout=wait)
            return cont, True, ""
        except PWTimeout:
            try:
                text = " ".join(cont.inner_text().split())[:120]
            except Exception:
                text = ""
            if NO_ITEMS_RE.search(text):  # the tab says there is nothing: no need to click again
                return cont, False, text
    try:
        text = " ".join(cont.inner_text().split())[:120]
    except Exception:
        text = ""
    return cont, False, text


def download_documents(page, args, dest_for):
    """Documents tab: tick everything, click Download Selected, save the result."""
    cont, loaded, text = open_tab(page, "#documents_tab", "#form-documents-container")
    if not loaded:
        detail = "no documents table appeared" + (f' (tab shows: "{text}")' if text else " (tab stayed blank)")
        # a tab that says there are no documents is genuinely empty; a blank tab is retried on the next run
        return ("empty" if NO_ITEMS_RE.search(text) else "error"), detail, None
    page.wait_for_timeout(500)
    show_all_entries(cont)
    if cont.locator("td.dataTables_empty").count():
        return "empty", "document table is empty", None

    boxes = cont.locator("input[type=checkbox]")
    for i in range(boxes.count()):
        b = boxes.nth(i)
        if b.is_visible() and not b.is_checked():
            b.check()
    unchecked = sum(1 for i in range(boxes.count()) if boxes.nth(i).is_visible() and not boxes.nth(i).is_checked())
    if unchecked:
        return "error", f"{unchecked} checkbox(es) could not be ticked", None

    btn = cont.locator(".btn-get-documents:visible").filter(has_text=re.compile("Download Selected", re.I))
    if btn.count() == 0:
        btn = page.locator(".btn-get-documents:visible").filter(has_text=re.compile("Download Selected", re.I))
    if btn.count() == 0:
        btn = page.locator("button:visible, input[type=button]:visible, a:visible").filter(
            has_text=re.compile(r"^\s*Download Selected\s*$", re.I))
    if btn.count() == 0:
        return "error", "Download Selected button not found", None

    d = capture_download(page, lambda: btn.first.click(), args.download_timeout)
    dest = unique_path(dest_for("documents", d.suggested_filename))
    d.save_as(dest)

    detail = ""
    expected = total_entries(cont)
    if zipfile.is_zipfile(dest):
        with zipfile.ZipFile(dest) as zf:
            n = sum(1 for name in zf.namelist() if not name.endswith("/"))
        detail = f"{n} file(s) in zip"
        if expected is not None and n != expected:
            return "warning", f"table lists {expected} document(s) but zip holds {n}", dest
    else:
        detail = "download was not a zip (single file?)"
    return "ok", detail, dest


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def history_row_wanted(args, desc, form_name=""):
    if args.history_all or re.search(args.history_pattern, desc, re.I) is not None:
        return True
    return bool(form_name and STATUS_OUTCOME_FORMS.search(form_name) and STATUS_OUTCOME_ROWS.search(desc))


def download_history_attachments(page, args, dest_for, form_copy=False, form_name=""):
    """History tab: download the attachments on rows whose description matches
    --history-pattern (default: favourable opinion), across all pages. A file whose
    content is identical to one already saved for this form is not kept."""
    cont, loaded, text = open_tab(page, "#history_tab", "#form-history-container", waits=(8000, 12000))
    if not loaded:
        return [("empty", "no history table appeared" + (f' (tab shows: "{text}")' if text else " (tab stayed blank)"), None)]
    page.wait_for_timeout(500)
    show_all_entries(cont)

    heads = [h.strip().lower() for h in cont.locator("thead th").all_inner_texts()]

    def col(name, default):
        return next((i for i, h in enumerate(heads) if name in h), default)

    date_col, desc_col = col("date", 0), col("description", 2)
    results, seen_hashes, skipped = [], {}, 0
    copy_saved = {}  # fallback label -> (date tag, file): only the latest submitted copy of a form is kept
    n_attach = n_wanted = 0
    for _page_no in range(500):
        rows = cont.locator("tbody tr")
        for i in range(rows.count()):
            row = rows.nth(i)
            cells = row.locator("td")
            if cells.count() <= max(date_col, desc_col):
                continue
            btn = row.get_by_role("button", name="Download", exact=True).or_(
                row.get_by_role("link", name="Download", exact=True))
            if btn.count() == 0:
                continue
            btn = btn.first
            disabled = (not btn.is_enabled()) or "disabled" in (btn.get_attribute("class") or "") \
                or btn.get_attribute("aria-disabled") == "true"
            if disabled:
                continue
            when = " ".join(cells.nth(date_col).inner_text().split())
            desc = " ".join(cells.nth(desc_col).inner_text().split())
            wanted = history_row_wanted(args, desc, form_name)
            copy_label = None
            if form_copy and not wanted:  # Documents tab was empty: also take the form's own copy
                copy_label = next((lab for lab, rx in FORM_COPY_ROWS if rx.search(desc)), None)
                wanted = copy_label is not None
            n_attach += 1
            n_wanted += wanted

            if args.history_scan:  # report only
                results.append(("scan", f"{when} | {'DOWNLOAD' if wanted else 'skip'} | {desc}", None))
                continue
            if not wanted:
                skipped += 1
                continue
            if copy_label:
                prev = copy_saved.get(copy_label)
                if prev and date_tag(when) <= prev[0]:  # an older version of a form that was resubmitted
                    skipped += 1
                    continue
            try:
                d = capture_download(page, lambda: btn.click(), args.download_timeout)
                label = f"letter {date_tag(when)} - {d.suggested_filename}"
                if copy_label:
                    dest = unique_path(dest_for("copy", d.suggested_filename, copy_label, stamp=date_tag(when)))
                else:
                    dest = unique_path(dest_for("letter", d.suggested_filename, label, stamp=date_tag(when)))
                d.save_as(dest)
                digest = sha256_of(dest)
                if digest in seen_hashes:
                    dest.unlink()
                    results.append(("duplicate", f"{when} | {desc} (same content as {seen_hashes[digest]}; not kept)", None))
                else:
                    seen_hashes[digest] = dest.name
                    results.append(("ok", f"{when} | {desc}" + (" (form copy: Documents tab lists nothing)" if copy_label else ""), dest))
                    if copy_label:
                        old = copy_saved.get(copy_label)
                        if old and old[1].exists():  # a newer submission was found after an older one was saved
                            old[1].unlink()
                            results.append(("info", f"older submitted copy replaced by the newer one ({old[1].name})", None))
                        copy_saved[copy_label] = (date_tag(when), dest)
            except PWTimeout:
                results.append(("error", f"no download started for {when} | {desc}", None))
            time.sleep(args.delay)

        nxt = cont.locator(".paginate_button.next")
        if nxt.count() == 0 or "disabled" in (nxt.first.get_attribute("class") or ""):
            break
        before = cont.locator("tbody tr").first.inner_text()
        nxt.first.click()
        advanced = False
        for _ in range(40):
            page.wait_for_timeout(250)
            if cont.locator("tbody tr").first.inner_text() != before:
                advanced = True
                break
        if not advanced:
            results.append(("error", "History table did not advance to the next page; later pages not checked", None))
            break
    if args.history_scan:
        results.append(("scansummary", f"{n_attach} attachment row(s), {n_wanted} would be downloaded", None))
    if skipped:
        results.append(("info", f"{skipped} other attachment(s) not downloaded (description did not match)", None))
    return results


# ---------------------------------------------------------------- per-form / per-project


def process_form(page, args, log, project, project_dir, index, form):
    display = form.get("display") or sanitise(form["name"], 50)

    if args.layout == "structured":
        # <project>/<NN - form>/<form> - all documents.zip     <project>/Approval letters/<date> - <form> - <name>
        form_dir = project_dir / (form.get("folder") or f"{index:02d} - {display}")
        letters_dir = project_dir / LETTERS_DIR
        form_dir.mkdir(parents=True, exist_ok=True)

        def dest_for(kind, suggested, label=None, stamp=None):
            if kind == "documents":
                ext = Path(suggested).suffix or ".zip"
                return form_dir / sanitise_filename(f"{display} - {ALL_DOCS}{ext}", 130)
            when = (stamp or "undated").replace("_", " ")
            if kind == "copy":  # form content taken from History because the Documents tab is empty
                return form_dir / sanitise_filename(f"{display} - {label} {when} - {suggested}", 130)
            letters_dir.mkdir(parents=True, exist_ok=True)
            return letters_dir / sanitise_filename(f"{when} - {display} - {suggested}", 130)
    else:  # flat: everything side by side in the project folder (the original layout)
        prefix = f"{index:02d} - {sanitise(form['name'], 50)} [{form['id']}]"
        form_dir = project_dir
        form_dir.mkdir(parents=True, exist_ok=True)

        def dest_for(kind, suggested, label=None, stamp=None):
            if kind == "documents":
                return form_dir / (f"{prefix}.zip" if suggested.lower().endswith(".zip")
                                   else sanitise_filename(f"{prefix} - {suggested}"))
            if kind == "copy":
                return form_dir / sanitise_filename(f"{prefix} - {label} {(stamp or 'undated').replace('_', ' ')} - {suggested}", 120)
            return form_dir / sanitise_filename(f"{prefix} - {label}", 120)

    open_form(page, args.base_url, form["id"])
    if args.dump_html:
        dump_debug(page, args, form)
        return "dumped"

    problems = 0
    form_copy = False
    if args.letters_only:
        # Do not download the documents again; only check whether the tab is empty (for the form-copy fallback).
        cont, loaded, text = open_tab(page, "#documents_tab", "#form-documents-container")
        form_copy = (not loaded and bool(NO_ITEMS_RE.search(text))) or (loaded and cont.locator("td.dataTables_empty").count() > 0)
    elif not args.history_scan:
        try:
            status, detail, dest = download_documents(page, args, dest_for)
            form_copy = status == "empty"
            log.row(project, form, "documents", dest.name if dest else "", status, detail)
            problems += status in ("error", "warning")
        except Exception as e:  # keep going with the history tab
            log.row(project, form, "documents", "", "error", repr(e))
            problems += 1
        time.sleep(args.delay)
    try:
        for status, detail, dest in download_history_attachments(page, args, dest_for, form_copy=form_copy, form_name=form["name"]):
            item = {"scan": "history scan", "scansummary": "history scan summary"}.get(status, "history attachment")
            log.row(project, form, item, dest.name if dest else "", status, detail)
            if status == "scansummary":
                print(f"        history: {detail}")
            problems += status == "error"
    except Exception as e:
        log.row(project, form, "history", "", "error", repr(e))
        problems += 1
    if args.history_scan or args.letters_only:
        return "scanned"  # these modes do not change which forms count as finished
    return "complete" if problems == 0 else "needs_review"


# ---------------------------------------------------------------- tidy an existing export


def tidy_export(args):
    """Move letters that should not be there into <out>/_tidy_removed/ (nothing is deleted):
    1. letters whose History row (recorded in export_log.csv) does not match --history-pattern;
    2. letters with identical content to another letter of the same form.
    Without --apply it only reports what it would move."""
    out = Path(args.out).expanduser().resolve()
    log_path = out / "export_log.csv"
    if not log_path.exists():
        print(f"No export_log.csv in {out}")
        return 1
    pattern = re.compile(args.history_pattern, re.I)

    row_matches = {}  # (project folder, file name) -> True if any History row for it matched
    with open(log_path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["item"] != "history attachment" or r["status"] != "ok" or not r["file"]:
                continue
            desc = r["detail"].split("|", 1)[-1].strip()
            pdir = out / f"{r['project_id']} - {sanitise(r['project_title'], 70)}"
            key = (pdir, r["file"])
            row_matches[key] = row_matches.get(key, False) or history_row_wanted(args, desc, r["form_name"])

    actions = []  # (path, reason)
    for pdir in sorted(p for p in out.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        letters = [p for p in pdir.rglob("*") if p.is_file() and (" - letter " in p.name or p.parent.name == LETTERS_DIR)]
        keep = []
        for p in letters:
            if row_matches.get((pdir, p.name)) is False:
                actions.append((p, "History row is not a favourable opinion"))
            else:
                keep.append(p)
        groups = {}
        for p in keep:
            groups.setdefault((p.parent, p.name.split(" - letter ")[0] if " - letter " in p.name else ""), []).append(p)
        for members in groups.values():
            first_of = {}
            for p in sorted(members, key=lambda q: (bool(re.search(r" \(\d+\)$", q.stem)), q.name)):
                digest = sha256_of(p)
                if digest in first_of:
                    actions.append((p, f"same content as {first_of[digest].name}"))
                else:
                    first_of[digest] = p

    by_project = {}
    for p, reason in actions:
        by_project.setdefault(p.relative_to(out).parts[0], []).append((p, reason))
    for proj, items in by_project.items():
        print(f"{proj[:70]}: {len(items)}")
    print(f"\n{len(actions)} file(s) would be moved." if not args.apply else f"\n{len(actions)} file(s) to move.")

    with open(out / "tidy_report.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["file", "reason", "moved"])
        for p, reason in actions:
            w.writerow([str(p.relative_to(out)), reason, "yes" if args.apply else "no (dry run)"])
    if args.apply:
        for p, _reason in actions:
            dest = out / "_tidy_removed" / p.relative_to(out)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(unique_path(dest)))
        print(f"Moved to {out / '_tidy_removed'} (delete that folder once you are satisfied). Report: {out / 'tidy_report.csv'}")
    else:
        print(f"Nothing moved. Report: {out / 'tidy_report.csv'}\nRun again with --apply to move them.")
    return 0


def untidy_export(args):
    """Undo --tidy --apply: move everything in <out>/_tidy_removed/ back to where it came from."""
    out = Path(args.out).expanduser().resolve()
    src = out / "_tidy_removed"
    if not src.exists():
        print(f"Nothing to restore: {src} does not exist.")
        return 0
    restored = skipped = 0
    for p in sorted(x for x in src.rglob("*") if x.is_file()):
        dest = out / p.relative_to(src)
        if dest.exists():
            skipped += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(dest))
        restored += 1
    for d in sorted((x for x in src.rglob("*") if x.is_dir()), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass
    try:
        src.rmdir()
    except OSError:
        pass
    print(f"Restored {restored} file(s)." + (f" {skipped} left in _tidy_removed because a file of that name already exists." if skipped else ""))
    return 0


# ---------------------------------------------------------------- restructure an existing flat export

OLD_LETTER_RE = re.compile(r"^(\d{2}) - (.+) \[(\d+)\] - letter (\d{4}-\d{2}-\d{2}|undated)(?:_(\d{4}))? - (.+)$")
OLD_ZIP_RE = re.compile(r"^(\d{2}) - (.+) \[(\d+)\](?: \((\d+)\))?(\.[A-Za-z0-9]+)$")
OLD_OTHER_RE = re.compile(r"^(\d{2}) - (.+) \[(\d+)\] - (.+)$")


def _letter_row_matches(out, args):
    """(project folder, file name) -> True if any History row recorded for that file is an approval."""
    path = out / "export_log.csv"
    result = {}
    if not path.exists():
        return result
    pattern = re.compile(args.history_pattern, re.I)
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["item"] != "history attachment" or r["status"] != "ok" or not r["file"]:
                continue
            desc = r["detail"].split("|", 1)[-1].strip()
            pdir = out / f"{r['project_id']} - {sanitise(r['project_title'], 70)}"
            key = (pdir, r["file"])
            result[key] = result.get(key, False) or history_row_wanted(args, desc, r["form_name"])
    return result


def _free_path(dest, taken):
    cand, n = dest, 1
    while cand in taken or cand.exists():
        n += 1
        cand = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
    taken.add(cand)
    return cand


def plan_restructure(args, out):
    """Return [(old path, new path, reason)] for every loose file in a flat project folder."""
    matches = _letter_row_matches(out, args)
    plan, taken = [], set()
    for pdir in sorted(p for p in out.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        parsed = []
        for p in sorted(x for x in pdir.iterdir() if x.is_file() and not x.name.startswith("_")):
            for kind, rx in (("letter", OLD_LETTER_RE), ("zip", OLD_ZIP_RE), ("doc", OLD_OTHER_RE)):
                m = rx.match(p.name)
                if m:
                    parsed.append((kind, p, m))
                    break
        if not parsed:
            continue

        forms = []
        meta = pdir / "_project.json"
        if meta.exists():
            try:
                forms = [dict(f) for f in json.loads(meta.read_text(encoding="utf-8")).get("forms", [])]
            except Exception:
                forms = []
        by_id = {str(f["id"]): f for f in forms}
        for _kind, _p, m in parsed:
            if m.group(3) not in by_id:  # no _project.json entry: use the name in the file name
                f = {"id": m.group(3), "name": m.group(2), "depth": 0}
                forms.append(f)
                by_id[m.group(3)] = f
        form_display_names(forms)
        number = {m.group(3): m.group(1) for _k, _p, m in parsed}
        for f in forms:
            if str(f["id"]) in number:
                f["folder"] = f"{number[str(f['id'])]} - {f['display']}"

        letters = []
        for kind, p, m in parsed:
            f = by_id[m.group(3)]
            if kind == "zip":
                copy = f" ({m.group(4)})" if m.group(4) else ""
                name = sanitise_filename(f"{f['display']} - {ALL_DOCS}{copy}{m.group(5)}", 130)
                plan.append((p, _free_path(pdir / f["folder"] / name, taken), "documents"))
            elif kind == "doc":
                name = sanitise_filename(f"{f['display']} - {ALL_DOCS} - {m.group(4)}", 130)
                plan.append((p, _free_path(pdir / f["folder"] / name, taken), "documents"))
            else:
                when = m.group(4) + (f" {m.group(5)}" if m.group(5) else "")
                name = sanitise_filename(f"{when} - {f['display']} - {m.group(6)}", 130)
                is_approval = args.history_all or matches.get((pdir, p.name), True)  # unknown -> keep as approval
                letters.append((p, str(f["id"]), name, is_approval))

        seen = {}
        order = sorted(letters, key=lambda t: (bool(re.search(r" \(\d+\)\.[^.]+$", t[0].name)), t[0].name))
        for p, fid, name, is_approval in order:
            if not is_approval:
                plan.append((p, _free_path(pdir / OTHER_DIR / name, taken), "History row is not an approval"))
                continue
            digest = sha256_of(p)
            if (fid, digest) in seen:
                plan.append((p, _free_path(pdir / OTHER_DIR / name, taken), f"same content as {seen[(fid, digest)]}"))
                continue
            seen[(fid, digest)] = p.name
            plan.append((p, _free_path(pdir / LETTERS_DIR / name, taken), "approval letter"))
    return plan


def restructure_export(args):
    """Move an existing flat export into the structured layout. Dry run unless --apply.
    Files are moved, never deleted or re-downloaded."""
    out = Path(args.out).expanduser().resolve()
    if not out.exists():
        print(f"Folder not found: {out}")
        return 1
    plan = plan_restructure(args, out)
    if not plan:
        print("Nothing to restructure: no flat-layout files found (already restructured?).")
        return 0

    from collections import Counter
    counts = Counter(reason if reason in ("documents", "approval letter") else "other History attachments" for _o, _n, reason in plan)
    projects = {o.parent for o, _n, _r in plan}
    print(f"{len(plan)} file(s) in {len(projects)} project folder(s): "
          f"{counts['documents']} document zip(s), {counts['approval letter']} approval letter(s), "
          f"{counts['other History attachments']} moved to '{OTHER_DIR}'.")
    sample = next(iter(projects))
    print(f"\nExample ({sample.name[:60]}):")
    for o, n, _r in [t for t in plan if t[0].parent == sample][:8]:
        print(f"  {o.name[:70]}\n    -> {n.relative_to(sample)}")

    with open(out / "restructure_report.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["old", "new", "reason", "moved"])
        for o, n, reason in plan:
            w.writerow([str(o.relative_to(out)), str(n.relative_to(out)), reason, "yes" if args.apply else "no (dry run)"])
    if not args.apply:
        print(f"\nNothing moved. Full plan: {out / 'restructure_report.csv'}\nRun again with --apply to move the files.")
        return 0
    for o, n, _r in plan:
        n.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(o), str(n))
    print(f"\nMoved {len(plan)} file(s). Report: {out / 'restructure_report.csv'}\n"
          "To undo: python3 leo_export.py --unrestructure")
    return 0


def unrestructure_export(args):
    """Undo --restructure --apply, using restructure_report.csv."""
    out = Path(args.out).expanduser().resolve()
    report = out / "restructure_report.csv"
    if not report.exists():
        print(f"No restructure_report.csv in {out}")
        return 1
    restored = skipped = 0
    with open(report, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["moved"] == "yes"]
    for r in rows:
        old, new = out / r["old"], out / r["new"]
        if not new.exists() or old.exists():
            skipped += 1
            continue
        old.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(new), str(old))
        restored += 1
    for d in sorted((x for x in out.rglob("*") if x.is_dir()), key=lambda x: len(x.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass
    report.rename(out / "restructure_report.undone.csv")
    print(f"Restored {restored} file(s)." + (f" {skipped} skipped (missing, or a file with the old name already exists)." if skipped else ""))
    return 0


def dump_debug(page, args, form):
    debug = Path(args.out) / "_debug"
    debug.mkdir(parents=True, exist_ok=True)
    for tab, container in (("documents_tab", "#form-documents-container"), ("history_tab", "#form-history-container")):
        page.click(f"#{tab}")
        page.wait_for_timeout(4000)
        html = page.locator(container).inner_html()
        (debug / f"form_{form['id']}_{tab}.html").write_text(html, encoding="utf-8")
    page.screenshot(path=str(debug / f"form_{form['id']}.png"), full_page=True)
    print(f"Saved HTML of the Documents and History tabs to {debug}")


# ---------------------------------------------------------------- browser session

# Stop Chromium throttling or pausing a window that is minimised or covered.
CHROME_ARGS = ["--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
               "--disable-background-timer-throttling"]
VIEWPORT = {"width": 1400, "height": 900}


def start_background(pw, args, storage_state, user_agent):
    """Open a hidden browser carrying the logged-in session. Returns (browser, ctx, page) or None."""
    browser = None
    try:
        launch = {"headless": True, "args": CHROME_ARGS}
        if args.channel:
            launch["channel"] = args.channel
        browser = pw.chromium.launch(**launch)
        ctx = browser.new_context(storage_state=storage_state, accept_downloads=True,
                                  user_agent=user_agent, viewport=VIEWPORT)
        page = ctx.new_page()
        page.set_default_timeout(30000)
        install_download_listener(ctx)
        page.goto(f"{args.base_url}/ActivityForm/FolderProjectList/0")
        page.wait_for_selector("#projectTableView tbody tr.project-row", timeout=30000)
        return browser, ctx, page
    except Exception as exc:
        print(f"Could not continue in a hidden browser ({type(exc).__name__}); staying with the visible window.")
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        return None


class Session:
    """Owns the browser. It opens visibly so you can log in, then moves the run into a hidden
    browser with the same login, so no window pops up while it works. If the site later asks
    for a login again, a window opens once, and the run carries on from the same project."""

    def __init__(self, pw, args, out):
        self.pw, self.args, self.out = pw, args, out
        self.browser = self.ctx = self.page = None

    def login(self):
        a = self.args
        self.ctx = self.pw.chromium.launch_persistent_context(
            str(self.out / ".browser_profile"), headless=a.headless, accept_downloads=True,
            channel=a.channel, viewport=VIEWPORT, args=CHROME_ARGS)
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.page.set_default_timeout(30000)
        install_download_listener(self.ctx)
        BACKGROUND["on"] = False
        wait_for_login(self.page, a.base_url)

    def hide(self):
        a = self.args
        if a.headed or a.headless or a.dump_html:
            return
        state = self.ctx.storage_state()
        ua = self.page.evaluate("navigator.userAgent")
        got = start_background(self.pw, a, state, ua)
        if not got:
            return
        visible = self.ctx
        self.browser, self.ctx, self.page = got
        BACKGROUND["on"] = True
        visible.close()
        print("Logged in. Continuing in a hidden browser; the window has closed. "
              "It reopens only if you need to log in again.")

    def relogin(self):
        print("\nThe session has expired. A browser window will open: log in there and the run continues by itself.")
        self.close()
        self.login()
        self.hide()

    def close(self):
        for obj in (self.ctx, self.browser):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        self.ctx = self.browser = self.page = None
        BACKGROUND["on"] = False


def run_project(page, args, log, out, project, n, total):
    """Export one project. Returns 'dumped' when --dump-html finished, otherwise None.
    Raises SessionExpired if the site asks for a login."""
    print(f"\n[{n}/{total}] {project['id']} - {project['title'][:70]}")
    project_dir = out / f"{project['id']} - {sanitise(project['title'], 70)}"
    try:
        open_form(page, args.base_url, project["form_id"])
        forms = read_tree(page) or [{"id": project["form_id"], "name": "Form", "depth": 0}]
    except SessionExpired:
        raise
    except Exception as e:
        log.row(project, None, "project tree", "", "error", repr(e))
        return None
    form_display_names(forms)
    print("    forms: " + "; ".join(f"{f['folder']} [{f['id']}]" for f in forms))
    if args.dry_run:
        return None
    project_dir.mkdir(parents=True, exist_ok=True)

    for i, form in enumerate(forms, 1):
        if args.retry_empty:
            if log.docs.get(form["id"]) != "empty":
                continue
        elif log.state.get(form["id"]) == "complete" and not args.force and not args.history_scan and not args.letters_only:
            print(f"    skip (already complete): {form['name']}")
            continue
        print(f"    {form['name']}")
        try:
            status = process_form(page, args, log, project, project_dir, i, form)
        except SessionExpired:
            raise
        except Exception as e:
            log.row(project, form, "form", "", "error", repr(e))
            try:
                page.screenshot(path=str(out / f"error_form_{form['id']}.png"))
            except Exception:
                pass
            status = "error"
        if status == "dumped":
            return "dumped"
        if status != "scanned":
            log.set_state(project, form, status)
        time.sleep(args.delay)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="LEO_export", help="output folder (default: ./LEO_export)")
    ap.add_argument("--layout", choices=["structured", "flat"], default="structured",
                    help="structured (default): a folder per form holding its zip, plus one 'Approval letters' folder; "
                         "flat: everything side by side in the project folder (the original layout)")
    ap.add_argument("--restructure", action="store_true",
                    help="move an existing flat export into the structured layout without downloading anything "
                         "(dry run unless --apply)")
    ap.add_argument("--unrestructure", action="store_true",
                    help="undo --restructure --apply, using restructure_report.csv")
    ap.add_argument("--owned-only", action="store_true", help="only projects where you are the owner")
    ap.add_argument("--project", action="append", help="only this Project ID (repeatable)")
    ap.add_argument("--limit", type=int, help="only the first N projects (for a trial run)")
    ap.add_argument("--dry-run", action="store_true", help="list projects and forms, download nothing")
    ap.add_argument("--dump-html", action="store_true",
                    help="diagnostic: save the HTML of the Documents and History tabs of the first form, then stop")
    ap.add_argument("--force", action="store_true", help="re-download forms already marked complete")
    ap.add_argument("--history-pattern", default=DEFAULT_HISTORY_PATTERN,
                    help="regular expression; only History rows whose description matches are downloaded "
                         "(default: favourable opinion, amendment approved by the RGIO, response to provisional letter approved)")
    ap.add_argument("--history-all", action="store_true", help="download every History attachment, whatever the description")
    ap.add_argument("--retry-empty", action="store_true",
                    help="only forms whose last Documents result in export_log.csv was 'empty' (no zip): check the tab again, "
                         "download the zip if it now has documents, otherwise save the form's submitted copy from History")
    ap.add_argument("--letters-only", action="store_true",
                    help="only (re)save the History letters of every form: documents are not downloaded again and "
                         "forms are not marked finished. Use it to top up an export made before a rule changed")
    ap.add_argument("--history-scan", action="store_true",
                    help="list History rows that have an attachment and whether they would be downloaded; "
                         "downloads nothing (results go in export_log.csv, item 'history scan')")
    ap.add_argument("--tidy", action="store_true",
                    help="clean an existing export: move non-matching and duplicate letters to _tidy_removed/ (dry run unless --apply)")
    ap.add_argument("--apply", action="store_true", help="with --tidy: actually move the files")
    ap.add_argument("--untidy", action="store_true", help="undo --tidy --apply: move files back from _tidy_removed/")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds to pause between actions (default 1)")
    ap.add_argument("--download-timeout", type=int, default=180, help="seconds to wait for each download")
    ap.add_argument("--channel", help="use an installed browser, e.g. 'chrome' or 'msedge'")
    ap.add_argument("--headed", action="store_true",
                    help="keep the browser window visible for the whole run (default: log in in a window, "
                         "then continue in a hidden browser)")
    ap.add_argument("--base-url", default=DEFAULT_BASE, help=argparse.SUPPRESS)
    ap.add_argument("--headless", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.unrestructure:
        return unrestructure_export(args)
    if args.restructure:
        return restructure_export(args)
    if args.untidy:
        return untidy_export(args)
    if args.tidy:
        return tidy_export(args)

    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    args.out = str(out)
    log = RunLog(out)

    with sync_playwright() as p:
        session = Session(p, args, out)
        try:
            session.login()
            projects = list_projects(session.page, args.base_url)
            if not projects:
                print("No projects found in the table.")
                return
            with open(out / "projects_index.csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=list(projects[0].keys()))
                w.writeheader()
                w.writerows(projects)
            print(f"{len(projects)} projects listed.")

            if args.retry_empty:
                wanted_ids = log.empty_project_ids()
                projects = [pr for pr in projects if pr["id"] in wanted_ids]
                print(f"{len(wanted_ids)} project(s) hold a form whose Documents tab came back empty.")
            if args.project:
                projects = [pr for pr in projects if pr["id"] in set(args.project)]
            if args.owned_only:
                projects = [pr for pr in projects if pr["is_owner"]]
            if args.limit:
                projects = projects[: args.limit]

            session.hide()
            n, expiries = 0, 0
            while n < len(projects):
                project = projects[n]
                try:
                    outcome = run_project(session.page, args, log, out, project, n + 1, len(projects))
                except SessionExpired:
                    expiries += 1
                    if expiries > 3:
                        log.row(project, None, "project", "", "error", "session kept expiring; project skipped")
                        n, expiries = n + 1, 0
                        continue
                    session.relogin()
                    continue  # same project again; forms already complete are skipped
                if outcome == "dumped":
                    return
                n, expiries = n + 1, 0
        finally:
            session.close()
    print(f"\nFinished. See {out / 'export_log.csv'} for anything marked warning or error.")


if __name__ == "__main__":
    sys.exit(main())
