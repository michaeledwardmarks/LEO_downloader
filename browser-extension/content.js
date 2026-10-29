// LEO Project Exporter - page script.
// Runs on every LEO page. When an export is in progress it does the work for the
// current page (project list, or one form), saves its position, and moves on.
(() => {
  "use strict";
  if (window.top !== window) return;

  const SK = "leoExportState";
  const ROOT = "LEO_export";
  let misplacedNote = "";   // set when a file is saved somewhere other than planned
  const rootOf = (state) => (state && state.opts && state.opts.root) || ROOT;
  function cleanRoot(text) {
    const parts = String(text || "").split(/[\\/]+/).map((p) => sanitise(p, 40)).filter((p) => p && p !== "unnamed");
    return parts.length ? parts.slice(0, 3).join("/") : ROOT;
  }
  let lastBeat = 0;
  // Heartbeat: lets a later page tell "still running" from "browser was closed mid-run".
  function beat(force) {
    const n = Date.now();
    if (force || n - lastBeat > 4000) {
      lastBeat = n;
      return chrome.storage.local.set({ leoExportBeat: n });
    }
  }
  // Waiting is done by the background worker. Chrome slows a hidden or covered page's own timers
  // (to one a minute after a few minutes); messages from the worker are not slowed.
  const sleep = (ms) => { beat(); return send({ type: "sleep", ms }).catch(() => new Promise((r) => setTimeout(r, ms))); };
  const norm = (t) => String(t || "").replace(/\s+/g, " ").trim();
  const visible = (el) => !!(el && (el.offsetParent !== null || el.getClientRects().length));
  const send = (msg) => chrome.runtime.sendMessage(msg);

  // History rows are exported only when their description records an approval.
  const APPROVAL = /(?<!un)favourable opinion|approved by the RGIO|response to the provisional letter has been approved/i;

  const path = location.pathname;
  const isList = /\/ActivityForm\/FolderProjectList/i.test(path);
  const formMatch = path.match(/\/Project\/Index\/(\d+)/i);
  const pageFormId = formMatch ? formMatch[1] : null;
  const LIST_URL = location.origin + "/ActivityForm/FolderProjectList/0";

  // ------------------------------------------------------------------ state

  async function load() {
    return (await chrome.storage.local.get(SK))[SK] || null;
  }
  async function save(s) {
    await chrome.storage.local.set({ [SK]: s });
  }
  async function myTab() {
    try { return (await send({ type: "whoami" })).tab; } catch (e) { return null; }
  }
  async function isStillRunning() {
    const s = await load();
    return !!(s && s.running);
  }

  function logRow(state, form, project, item, file, status, detail) {
    state.log.push({
      time: new Date().toISOString().slice(0, 19),
      project_id: project ? project.pid : "",
      project_title: project ? project.title : "",
      form_id: form ? form.id : "",
      form_name: form ? form.name : "",
      item,
      file: file || "",
      status,
      detail: detail || "",
    });
  }

  function csv(state) {
    const cols = ["time", "project_id", "project_title", "form_id", "form_name", "item", "file", "status", "detail"];
    const esc = (v) => '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"';
    return [cols.join(",")].concat(state.log.map((r) => cols.map((c) => esc(r[c])).join(","))).join("\r\n");
  }

  // ------------------------------------------------------------------ names

  function sanitise(name, max = 80) {
    let s = String(name || "")
      .replace(/[<>:"\/\\|?*\x00-\x1f]/g, "_")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/^[. ]+|[. ]+$/g, "");
    if (s.length > max) s = s.slice(0, max).replace(/[. -]+$/, "");
    return s || "unnamed";
  }

  // Folder and file names for the forms of a project. Forms that share a name (for example several
  // "Annual Report Form") are numbered 1, 2, 3 in tree order.
  function formNames(forms) {
    const counts = {};
    forms.forEach((f) => { const b = sanitise(f.name, 40); counts[b] = (counts[b] || 0) + 1; });
    const seen = {};
    return forms.map((f, i) => {
      const b = sanitise(f.name, 40);
      let display = b;
      if (counts[b] > 1) { seen[b] = (seen[b] || 0) + 1; display = `${b} ${seen[b]}`; }
      return { display, folder: `${String(i + 1).padStart(2, "0")} - ${display}` };
    });
  }

  const LETTERS_DIR = "Approval letters";

  function dateTag(text) {
    const m = String(text || "").match(/(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2})/);
    return m ? `${m[3]}-${m[2]}-${m[1]}_${m[4]}${m[5]}` : "undated";
  }

  // ------------------------------------------------------------------ DOM helpers

  async function waitFor(fn, timeout = 30000, interval = 250) {
    const t0 = Date.now();
    for (;;) {
      let v;
      try { v = fn(); } catch (e) { v = null; }
      if (v) return v;
      if (Date.now() - t0 > timeout) return null;
      await sleep(interval);
    }
  }

  const isDisabled = (el) =>
    el.disabled || el.hasAttribute("disabled") || el.getAttribute("aria-disabled") === "true" || /disabled/i.test(el.className || "");

  function findButton(scope, text) {
    return [...scope.querySelectorAll("button, a, input[type=button], input[type=submit]")].find(
      (el) => visible(el) && norm(el.innerText || el.value).toLowerCase() === text.toLowerCase()
    );
  }

  async function showAllRows(cont) {
    const sel = cont.querySelector("select[name$='_length']");
    if (!sel) return;
    const nums = [...sel.options].map((o) => o.value).filter((v) => /^-?\d+$/.test(v)).map(Number);
    if (!nums.length) return;
    sel.value = nums.includes(-1) ? "-1" : String(Math.max(...nums));
    sel.dispatchEvent(new Event("change", { bubbles: true }));
    await sleep(500);
  }

  function readTree() {
    const out = [];
    const seen = new Set();
    const tree = document.querySelector("div.well.tree");
    if (tree) {
      tree.querySelectorAll('a[href*="/Project/Index/"]').forEach((a) => {
        const m = a.href.match(/\/Project\/Index\/(\d+)/);
        if (!m || seen.has(m[1])) return;
        seen.add(m[1]);
        let depth = 0;
        let el = a.closest("li");
        while (el) {
          const p = el.parentElement && el.parentElement.closest("li");
          if (!p) break;
          depth++;
          el = p;
        }
        out.push({
          id: m[1],
          href: a.href.split("#")[0],
          name: norm(a.textContent).replace(/[\s-]+$/, ""),
          depth: Math.max(0, depth - 1),
        });
      });
    }
    if (!out.length && pageFormId) {
      out.push({
        id: pageFormId,
        href: location.href.split("#")[0],
        name: norm(document.title.split(" - LSHTM")[0]) || "Form",
        depth: 0,
      });
    }
    return out;
  }

  async function collectProjects(onProgress) {
    const out = new Map();
    for (let guard = 0; guard < 500; guard++) {
      const rows = [...document.querySelectorAll("#projectTableView tbody tr.project-row")];
      for (const tr of rows) {
        const ufid = tr.dataset.userprojectformid;
        if (!ufid || out.has(ufid)) continue;
        const td = tr.querySelectorAll("td");
        const a = tr.querySelector("a.project-link");
        out.set(ufid, {
          ufid,
          pid: td[2] ? norm(td[2].innerText) : "",
          title: a ? norm(a.innerText) : "",
          href: a ? a.href : "",
          owner: tr.dataset.owner === "True",
          ownerName: td[3] ? norm(td[3].innerText) : "",
          folder: td[6] ? norm(td[6].innerText) : "",
          canAccess: tr.dataset.canaccess !== "False",
        });
      }
      onProgress(`Reading project list: ${out.size} found`);
      const nxt = document.querySelector("#projectTableView_next");
      if (!nxt || nxt.classList.contains("disabled")) break;
      const first = rows[0] && rows[0].dataset.userprojectformid;
      nxt.click();
      const moved = await waitFor(() => {
        const r = document.querySelector("#projectTableView tbody tr.project-row");
        return r && r.dataset.userprojectformid !== first;
      }, 15000);
      if (!moved) break;
      await sleep(200);
    }
    return [...out.values()];
  }

  // ------------------------------------------------------------------ downloads

  // Tell the background worker how to name the next download, click, and wait until it finishes.
  async function downloadVia(el, dir, name, mode, startTimeoutMs, group) {
    const { tok } = await send({ type: "expect", dir, name, mode, group: group || "" });
    el.click();
    const t0 = Date.now();
    let started = false, idleSince = 0, hinted = false;
    for (;;) {
      await sleep(400);
      if (!(await isStillRunning())) {
        await send({ type: "cancel", tok });
        throw new Error("paused by user");
      }
      const r = await send({ type: "poll", tok });
      if (r.state === "complete") {
        if (r.misplaced) {
          misplacedNote =
            `A file was not saved where the exporter asked.\nExpected a folder ending "${r.path.slice(0, r.path.lastIndexOf("/"))}"\nbut it was saved to "${r.misplaced}".\n` +
            "Your browser may be overriding the save location (for example, it asks where to save each file, or a setting applies). " +
            "The export has paused. Fix the download settings, move or delete the misplaced files, then press Resume.";
          throw new Error("saved in the wrong place: " + r.misplaced);
        }
        return { path: r.path, dupOf: r.dupOf || "", req: r.req || "" };
      }
      if (r.state === "failed") throw new Error("download failed: " + (r.error || "unknown"));
      if (r.state === "started") {
        started = true;
        // the browser has not settled on a file name after 8 s: it is probably showing a Save dialog
        if (r.named === false) {
          idleSince = idleSince || Date.now();
          if (!hinted && Date.now() - idleSince > 8000) { hinted = true; showSaveHint(); }
        } else idleSince = 0;
      }
      if (!started && Date.now() - t0 > startTimeoutMs) {
        await send({ type: "cancel", tok });
        throw new Error(`no download started within ${Math.round(startTimeoutMs / 1000)}s`);
      }
      if (Date.now() - t0 > startTimeoutMs + 600000) throw new Error("download did not finish");
    }
  }

  async function exportDocuments(state, project, form, prefix, dir) {
    document.querySelector("#documents_tab").click();
    const cont = document.querySelector("#form-documents-container");
    const table = await waitFor(() => cont.querySelector("table tbody tr") && cont.querySelector("table"), 30000);
    if (!table) { logRow(state, form, project, "documents", "", "EMPTY", "no documents table appeared"); return true; }
    await sleep(500);
    await showAllRows(cont);

    const rows = [...cont.querySelectorAll("table tbody tr")].filter((r) => !r.querySelector("td.dataTables_empty"));
    if (!rows.length) { logRow(state, form, project, "documents", "", "EMPTY", "document table is empty"); return true; }

    cont.querySelectorAll("input[type=checkbox]").forEach((cb) => { if (visible(cb) && !cb.checked) cb.click(); });
    const unticked = [...cont.querySelectorAll("input[type=checkbox]")].filter((cb) => visible(cb) && !cb.checked).length;
    if (unticked) { logRow(state, form, project, "documents", "", "ERROR", `${unticked} checkbox(es) could not be ticked`); return false; }

    let detail = `${rows.length} document(s) listed`;
    const info = cont.querySelector(".dataTables_info");
    const m = info && norm(info.innerText).match(/of ([\d,]+) entries/);
    let status = "OK";
    if (m && parseInt(m[1].replace(/,/g, ""), 10) !== rows.length) {
      status = "WARNING";
      detail = `table shows ${rows.length} of ${m[1]} documents; check this form`;
    }

    const btn =
      findButton(cont, "Download Selected") ||
      [...document.querySelectorAll(".btn-get-documents")].find((el) => visible(el) && norm(el.innerText).toLowerCase() === "download selected") ||
      findButton(document, "Download Selected");
    if (!btn) { logRow(state, form, project, "documents", "", "ERROR", "Download Selected button not found"); return false; }

    try {
      const saved = await downloadVia(btn, dir, prefix, "replace", 240000);
      logRow(state, form, project, "documents", saved.path, status, `${detail}; served as ${saved.req || "unknown"}`);
      return status !== "ERROR";
    } catch (e) {
      logRow(state, form, project, "documents", "", "ERROR", String(e.message || e));
      return false;
    }
  }

  async function exportLetters(state, project, form, prefix, dir, setStatus) {
    document.querySelector("#history_tab").click();
    const cont = document.querySelector("#form-history-container");
    const table = await waitFor(() => cont.querySelector("table tbody tr") && cont.querySelector("table"), 20000);
    if (!table) return true;
    await sleep(500);
    await showAllRows(cont);

    const heads = [...cont.querySelectorAll("thead th")].map((h) => norm(h.innerText).toLowerCase());
    const col = (name, dflt) => { const i = heads.findIndex((h) => h.includes(name)); return i >= 0 ? i : dflt; };
    const dateCol = col("date", 0);
    const descCol = col("description", 2);
    let ok = true;
    let nAttach = 0, nWanted = 0, skipped = 0;
    const scan = !!state.opts.scanOnly;

    for (let pg = 0; pg < 500; pg++) {
      const rows = [...cont.querySelectorAll("tbody tr")];
      for (const row of rows) {
        const cells = row.querySelectorAll("td");
        if (cells.length <= Math.max(dateCol, descCol)) continue;
        const btn = findButton(row, "Download");
        if (!btn || isDisabled(btn)) continue;
        const when = cells[dateCol].innerText;
        const desc = norm(cells[descCol].innerText);
        const wanted = APPROVAL.test(desc);
        nAttach++;
        if (wanted) nWanted++;
        if (scan) {
          logRow(state, form, project, "history scan", "", "SCAN", `${norm(when)} | ${wanted ? "DOWNLOAD" : "skip"} | ${desc}`);
          continue;
        }
        if (!wanted) { skipped++; continue; }
        setStatus(`${form.name}: letter ${dateTag(when)}`);
        try {
          const got = await downloadVia(btn, dir, `${dateTag(when).replace("_", " ")} - ${prefix}`, "append", 90000, form.id);
          if (got.dupOf) {
            logRow(state, form, project, "history attachment", got.path, "CHECK", `${norm(when)} | ${desc} | possible duplicate: same name and size as ${got.dupOf}`);
          } else {
            logRow(state, form, project, "history attachment", got.path, "OK", `${norm(when)} | ${desc}`);
          }
        } catch (e) {
          ok = false;
          logRow(state, form, project, "history attachment", "", "ERROR", `${norm(when)} | ${desc} | ${e.message || e}`);
          if (String(e.message).includes("paused") || misplacedNote) return false;
        }
        await sleep(state.opts.delayMs);
      }
      const nxt = cont.querySelector(".paginate_button.next, a[id$='_next']");
      if (!nxt || nxt.classList.contains("disabled")) break;
      const before = (cont.querySelector("tbody tr") || {}).innerText;
      nxt.click();
      const advanced = await waitFor(() => (cont.querySelector("tbody tr") || {}).innerText !== before, 10000);
      if (!advanced) {
        logRow(state, form, project, "history", "", "ERROR", "History table did not advance to the next page; later pages not checked");
        ok = false;
        break;
      }
      await sleep(250);
    }
    if (scan) logRow(state, form, project, "history scan summary", "", "SCAN", `${nAttach} attachment row(s), ${nWanted} would be downloaded`);
    else if (skipped) logRow(state, form, project, "history attachment", "", "INFO", `${skipped} other attachment(s) not downloaded (description did not match)`);
    return ok;
  }

  // ------------------------------------------------------------------ panel UI

  const host = document.createElement("div");
  host.id = "leo-export-host";
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `
    <style>
      .card{position:fixed;right:16px;bottom:16px;z-index:2147483647;width:300px;background:#fff;color:#1b1f23;
            border:1px solid #9aa4ad;border-radius:8px;box-shadow:0 4px 18px rgba(0,0,0,.25);
            font:13px/1.4 system-ui,Segoe UI,Arial,sans-serif;padding:12px}
      h4{margin:0 0 6px;font-size:14px}
      .msg{margin:6px 0;white-space:pre-wrap;word-break:break-word}
      .row{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center}
      button{font:inherit;padding:5px 10px;border:1px solid #2563eb;background:#2563eb;color:#fff;border-radius:5px;cursor:pointer}
      button.sec{background:#fff;color:#2563eb}
      input[type=number]{width:70px;font:inherit;padding:3px}
      label{display:flex;gap:6px;align-items:center;margin-top:6px}
      .bar{height:6px;background:#e5e7eb;border-radius:3px;overflow:hidden;margin-top:6px}
      .bar>div{height:100%;background:#2563eb;width:0}
      .min{cursor:pointer;float:right;color:#6b7280}
      .hint{margin-top:8px;padding:8px;background:#fff7ed;border:1px solid #fdba74;border-radius:6px}
      .overlay{position:fixed;inset:0;z-index:2147483647;background:rgba(15,23,42,.55);display:flex;align-items:center;justify-content:center}
      .dlg{background:#fff;color:#1b1f23;width:min(980px,94vw);height:min(740px,90vh);border-radius:10px;display:flex;flex-direction:column;
           box-shadow:0 10px 40px rgba(0,0,0,.4);font:13px/1.4 system-ui,Segoe UI,Arial,sans-serif}
      .dlg header{padding:14px 16px;border-bottom:1px solid #e5e7eb}
      .dlg h3{margin:0 0 8px;font-size:16px}
      .tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
      .tools input[type=search]{flex:1;min-width:220px;padding:6px 8px;font:inherit;border:1px solid #9aa4ad;border-radius:5px}
      .list{flex:1;overflow:auto}
      table{width:100%;border-collapse:collapse}
      th{position:sticky;top:0;background:#f3f4f6;text-align:left;padding:6px 8px;cursor:pointer;border-bottom:1px solid #d1d5db;user-select:none}
      td{padding:6px 8px;border-bottom:1px solid #eef0f2;vertical-align:top}
      tr.pick:hover td{background:#f8fafc;cursor:pointer}
      td.id{white-space:nowrap}
      .dlg footer{padding:12px 16px;border-top:1px solid #e5e7eb;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
      .spacer{flex:1}
      .note{color:#4b5563;font-size:12px;margin-top:4px}
      input.folder{padding:5px 8px;font:inherit;border:1px solid #9aa4ad;border-radius:5px;width:180px}
    </style>
    <div class="card" id="card"></div>`;
  const card = root.getElementById("card");

  function el(tag, props = {}, ...kids) {
    const e = document.createElement(tag);
    Object.assign(e, props);
    kids.forEach((k) => e.append(k));
    return e;
  }
  function btn(text, onclick, sec) {
    return el("button", { textContent: text, className: sec ? "sec" : "", onclick });
  }

  let msgEl, barEl;
  function setStatus(text) { if (msgEl) msgEl.textContent = text; }
  function setBar(frac) { if (barEl) barEl.style.width = Math.round(100 * Math.max(0, Math.min(1, frac))) + "%"; }

  function summary(state) {
    const vals = Object.values(state.results);
    const done = vals.filter((v) => v === "complete" || v === "scanned").length;
    const review = vals.filter((v) => v === "needs_review").length;
    return `Projects ${Math.min(state.p + (state.finished ? 0 : 1), state.projects.length)}/${state.projects.length}. Forms done: ${done}` + (review ? `, needing review: ${review}` : "") + ".";
  }

  function render(state) {
    card.replaceChildren();
    card.append(el("h4", { textContent: "LEO Project Exporter" }));
    msgEl = el("div", { className: "msg" });
    card.append(msgEl);

    if (state && state.running) {
      barEl = el("div");
      card.append(el("div", { className: "bar" }, barEl));
      setBar(state.projects.length ? state.p / state.projects.length : 0);
      setStatus(summary(state));
      card.append(el("div", { className: "row" }, btn("Pause", pause, true)));
      return;
    }

    if (state && state.finished) {
      setStatus((state.opts && state.opts.scanOnly ? "Preview finished (nothing was downloaded). " : "Finished. ") + summary(state) +
        `\nThe log is in your Downloads folder under ${rootOf(state)} as export_log.csv.` +
        (state.opts && state.opts.scanOnly ? "" : "\nOpen it and look for any row marked ERROR, CHECK, EMPTY or NEEDS_REVIEW."));
      card.append(el("div", { className: "row" }, btn("Save log again", () => saveLog(state), true), btn("Start over", reset, true)));
      return;
    }

    if (state && state.projects && state.projects.length) {
      setStatus((state.notice ? state.notice + "\n\n" : "") + "Paused. " + summary(state));
      card.append(el("div", { className: "row" }, btn("Resume", resume), btn("Save log", () => saveLog(state), true), btn("Start over", reset, true)));
      return;
    }

    if (isList) {
      setStatus("Choose which projects to export. Files are saved in your Downloads folder, one folder per project.");
      card.append(el("div", { className: "row" }, btn("Choose projects…", chooseProjects)));
    } else {
      setStatus("To start, open Projects in the left menu.");
      card.append(el("div", { className: "row" }, btn("Go to All Projects", () => { location.href = LIST_URL; })));
    }
  }

  // ------------------------------------------------------------------ controls

  async function chooseProjects() {
    setStatus("Reading project list...");
    const projects = await collectProjects(setStatus);
    if (!projects.length) { setStatus("No projects found in the table."); return; }
    setStatus("Choose which projects to export. Files are saved in your Downloads folder, one folder per project.");
    showPicker(projects);
  }

  async function startRun(projects, opts) {
    setStatus("Checking that downloads can be saved automatically...");
    const check = await send({ type: "checkDownloads", dir: opts.root || ROOT, url: location.origin + "/Content/Icons/help-blue.png" }).catch(() => ({ ok: true }));
    if (!check.ok) { showSetupProblem(() => startRun(projects, opts)); return; }
    const state = {
      running: true, finished: false, projects, p: 0, forms: null, f: 0,
      results: {}, attempts: {}, log: [],
      opts: { delayMs: 1000, scanOnly: !!opts.scanOnly, root: opts.root || ROOT }, startedAt: Date.now(),
    };
    logRow(state, null, null, "project list", "", "OK", `${projects.length} project(s) selected`);
    state.driverTab = await myTab();
    await send({ type: "clearPending" });
    await beat(true);
    await save(state);
    goToCurrent(state);
  }

  // ------------------------------------------------------------------ project picker

  function showPicker(projects) {
    const chosen = new Set();
    let query = "";
    let mineOnly = false;
    let sortKey = "";
    let sortDir = 1;

    const search = el("input", { type: "search", placeholder: "Filter by project ID, title, owner or folder" });
    const mine = el("input", { type: "checkbox" });
    const tbody = el("tbody");
    const countEl = el("span", { className: "spacer" });
    const goBtn = btn("", () => go());
    const folderIn = el("input", { className: "folder", value: ROOT });
    const previewIn = el("input", { type: "checkbox" });

    const cols = [["pid", "Project ID"], ["title", "Title"], ["ownerName", "Owner"], ["folder", "Folder"]];
    const headRow = el("tr", {}, el("th", { textContent: "" }));
    cols.forEach(([key, label]) => {
      const th = el("th", { textContent: label });
      th.onclick = () => { sortDir = sortKey === key ? -sortDir : 1; sortKey = key; draw(); };
      headRow.append(th);
    });

    function shown() {
      const q = query.toLowerCase();
      let rows = projects.filter((p) =>
        (!mineOnly || p.owner) && (!q || [p.pid, p.title, p.ownerName, p.folder].some((v) => String(v).toLowerCase().includes(q))));
      if (sortKey) {
        rows = rows.slice().sort((a, b) => {
          const x = String(a[sortKey]), y = String(b[sortKey]);
          return sortKey === "pid" ? sortDir * (Number(x) - Number(y)) : sortDir * x.localeCompare(y);
        });
      }
      return rows;
    }

    function refresh() {
      const n = chosen.size;
      countEl.textContent = `${n} of ${projects.length} selected`;
      goBtn.textContent = n ? (previewIn.checked ? `Preview ${n} project${n > 1 ? "s" : ""}` : `Download ${n} project${n > 1 ? "s" : ""}`) : "Select projects first";
      goBtn.disabled = !n;
      goBtn.style.opacity = n ? "1" : "0.5";
    }

    function draw() {
      const rows = shown();
      tbody.replaceChildren(...rows.map((p) => {
        const cb = el("input", { type: "checkbox", checked: chosen.has(p.ufid) });
        const toggle = () => { chosen.has(p.ufid) ? chosen.delete(p.ufid) : chosen.add(p.ufid); cb.checked = chosen.has(p.ufid); refresh(); };
        cb.onclick = (e) => { e.stopPropagation(); chosen.has(p.ufid) ? chosen.delete(p.ufid) : chosen.add(p.ufid); refresh(); };
        const tr = el("tr", { className: "pick" },
          el("td", {}, cb),
          el("td", { className: "id", textContent: p.pid }),
          el("td", { textContent: p.title }),
          el("td", { textContent: p.ownerName }),
          el("td", { textContent: p.folder }));
        tr.onclick = toggle;
        return tr;
      }));
      refresh();
    }

    function close() { overlay.remove(); }
    function go() {
      const picked = projects.filter((p) => chosen.has(p.ufid)); // keep the site's order
      if (!picked.length) return;
      const rootName = cleanRoot(folderIn.value);
      close();
      startRun(picked, { root: rootName, scanOnly: previewIn.checked });
    }

    search.oninput = () => { query = search.value.trim(); draw(); };
    mine.onchange = () => { mineOnly = mine.checked; draw(); };
    previewIn.onchange = refresh;

    const overlay = el("div", { className: "overlay" },
      el("div", { className: "dlg" },
        el("header", {},
          el("h3", { textContent: "Choose projects to export" }),
          el("div", { className: "tools" },
            search,
            el("label", { style: "margin:0" }, mine, "Only mine"),
            btn("Select all shown", () => { shown().forEach((p) => chosen.add(p.ufid)); draw(); }, true),
            btn("Clear", () => { chosen.clear(); draw(); }, true))),
        el("div", { className: "list" }, el("table", {}, el("thead", {}, headRow), tbody)),
        el("footer", {},
          countEl,
          el("label", { style: "margin:0" }, "Save into folder:", folderIn),
          el("label", { style: "margin:0" }, previewIn, "Preview only"),
          btn("Cancel", close, true),
          goBtn),
        el("div", { className: "note", style: "padding:0 16px 10px" },
          "Files go inside your browser's Downloads folder, in the folder named above. To use a different location, change the download location in your browser's settings first.")));
    root.append(overlay);
    draw();
  }

  function showSetupProblem(retry) {
    const url = /Edg\//.test(navigator.userAgent) ? "edge://settings/downloads" : "chrome://settings/downloads";
    card.replaceChildren(
      el("h4", { textContent: "LEO Project Exporter" }),
      el("div", { className: "hint" },
        el("div", { textContent: "Your browser is set to ask where to save each file, so it would show a Save window for every download. Turn off \u201cAsk where to save each file before downloading\u201d in the download settings, then press Try again." }),
        el("div", { className: "row" },
          btn("Open download settings", () => send({ type: "openSettings", url }), true),
          btn("Try again", retry),
          btn("Cancel", () => render(null), true))));
  }

  function showSaveHint() {
    if (!card || card.querySelector(".hint")) return;
    const url = /Edg\//.test(navigator.userAgent) ? "edge://settings/downloads" : "chrome://settings/downloads";
    card.append(el("div", { className: "hint" },
      el("div", { textContent: "Your browser may be asking where to save a file. Look for a Save window. Turn off \u201cAsk where to save each file before downloading\u201d in the download settings, then press Pause and Resume." }),
      el("div", { className: "row" }, btn("Open download settings", () => send({ type: "openSettings", url }), true))));
  }

  async function pause() {
    const s = await load();
    if (s) { s.running = false; await save(s); }
    render(s);
  }

  async function resume() {
    const s = await load();
    if (!s) return;
    s.running = true;
    s.finished = false;
    s.notice = "";
    s.driverTab = await myTab();
    await send({ type: "clearPending" });
    await beat(true);
    await save(s);
    goToCurrent(s);
  }

  async function reset() {
    await chrome.storage.local.remove(SK);
    render(null);
  }

  async function saveLog(state) {
    await send({ type: "saveText", path: `${rootOf(state)}/export_log.csv`, text: csv(state) });
  }

  function goToCurrent(state) {
    if (state.p >= state.projects.length) { location.href = LIST_URL; return; }
    const target = state.forms && state.f < state.forms.length ? state.forms[state.f].href : state.projects[state.p].href;
    if (target.split("#")[0] === location.href.split("#")[0]) location.reload();
    else location.href = target;
  }

  async function finish(state) {
    state.running = false;
    state.finished = true;
    await save(state);
    await saveLog(state);
    render(state);
  }

  // ------------------------------------------------------------------ driver

  async function drive() {
    document.documentElement.append(host);
    let state = await load();
    if (state && state.running) {
      const last = (await chrome.storage.local.get("leoExportBeat")).leoExportBeat || 0;
      if (Date.now() - last > 90000) {
        // the browser was closed or the run stalled: do not restart downloads unasked
        state.running = false;
        await save(state);
        render(state);
        setStatus("Interrupted. " + summary(state) + "\nPress Resume to continue where it stopped.");
        return;
      }
    }
    if (state && state.running && state.driverTab != null && (await myTab()) !== state.driverTab) {
      // Another LEO tab is doing the export. Leave it alone.
      card.replaceChildren(
        el("h4", { textContent: "LEO Project Exporter" }),
        el("div", { className: "msg", textContent: "An export is running in another browser tab. Leave that tab open, and do not start a second one." })
      );
      return;
    }
    render(state);
    if (!state || !state.running) return;
    beat(true);

    if (state.p >= state.projects.length) { await finish(state); return; }

    if (isList) { goToCurrent(state); return; }
    if (!pageFormId) {
      state.running = false;
      await save(state);
      render(state);
      setStatus("Paused: this is not a project page (session expired?). Log in again, open All Projects, then press Resume.");
      return;
    }

    const project = state.projects[state.p];
    const label = `${project.pid} - ${project.title}`;
    setBar(state.p / state.projects.length);
    setStatus(`${summary(state)}\n${label.slice(0, 80)}`);

    // first visit to this project: read its tree
    if (!state.forms) {
      if (pageFormId !== project.ufid) { location.href = project.href; return; }
      const ready = await waitFor(() => document.querySelector("#documents_tab"), 30000);
      if (!ready) {
        logRow(state, null, project, "project tree", "", "ERROR", "form page did not load (no Documents tab)");
        state.p++; state.forms = null; state.f = 0;
        await save(state);
        setTimeout(() => goToCurrent(state), 500);
        return;
      }
      state.forms = readTree();
      state.f = 0;
      await save(state);
    }

    // skip forms completed in an earlier run
    while (state.f < state.forms.length && state.results[state.forms[state.f].id] === "complete") state.f++;
    if (state.f >= state.forms.length) {
      state.p++; state.forms = null; state.f = 0;
      await save(state);
      goToCurrent(state);
      return;
    }

    const form = state.forms[state.f];
    if (pageFormId !== form.id) { location.href = form.href; return; }

    const ready = await waitFor(() => document.querySelector("#documents_tab"), 30000);
    let outcome = "needs_review";
    state.attempts[form.id] = (state.attempts[form.id] || 0) + 1;
    await save(state);

    if (!ready) {
      logRow(state, form, project, "form", "", "ERROR", "form page did not load (no Documents tab)");
    } else if (state.attempts[form.id] > 3) {
      logRow(state, form, project, "form", "", "ERROR", "skipped after 3 attempts");
    } else {
      const projectDir = `${rootOf(state)}/${sanitise(label, 55)}`;
      const names = formNames(state.forms)[state.f];
      const docDir = `${projectDir}/${names.folder}`;
      const letterDir = `${projectDir}/${LETTERS_DIR}`;
      setStatus(`${summary(state)}\n${label.slice(0, 60)}\n${form.name}: documents`);
      let ok = true;
      try {
        if (!state.opts.scanOnly) ok = (await exportDocuments(state, project, form, `${names.display} - all documents`, docDir)) && ok;
        if ((await isStillRunning()) && !misplacedNote) {
          await sleep(state.opts.delayMs);
          setStatus(`${summary(state)}\n${label.slice(0, 60)}\n${form.name}: history`);
          ok = (await exportLetters(state, project, form, names.display, letterDir, (t) => setStatus(`${summary(state)}\n${t}`))) && ok;
        }
      } catch (e) {
        ok = false;
        logRow(state, form, project, "form", "", "ERROR", String(e.message || e));
      }
      if (misplacedNote) {
        // stop at the first misplaced file so a wrong setting cannot affect later projects
        const fresh = await load();
        fresh.log = state.log;
        fresh.attempts = state.attempts;
        fresh.running = false;
        fresh.notice = misplacedNote;
        logRow(fresh, form, project, "form", "", "MISPLACED", misplacedNote.split("\n")[2] || "");
        await save(fresh);
        await saveLog(fresh);
        render(fresh);
        return;
      }
      if (!(await isStillRunning())) {
        // paused part-way: keep the form unfinished, store what was logged
        const fresh = await load();
        fresh.log = state.log;
        fresh.attempts = state.attempts;
        await save(fresh);
        render(fresh);
        return;
      }
      outcome = state.opts.scanOnly ? "scanned" : ok ? "complete" : "needs_review";
    }

    state.results[form.id] = outcome;
    if (!state.opts.scanOnly) logRow(state, form, project, "form", "", outcome === "complete" ? "OK" : "NEEDS_REVIEW", "");
    state.f++;
    if (state.f >= state.forms.length) { state.p++; state.forms = null; state.f = 0; }
    await save(state);
    await sleep(state.opts.delayMs);
    if (!(await isStillRunning())) { render(await load()); return; }
    goToCurrent(state);
  }

  drive().catch((e) => {
    console.error("LEO exporter", e);
    setStatus("Stopped on an error: " + (e && e.message ? e.message : e));
  });
})();
