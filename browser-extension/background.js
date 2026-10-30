// LEO Project Exporter - background service worker.
// Its job: decide where each download is saved (inside Downloads/LEO_export/...),
// and report back to the page script when a download has finished or failed.

const sget = async (k) => (await chrome.storage.session.get(k))[k];
const sset = (k, v) => chrome.storage.session.set({ [k]: v });

function clean(name, max = 80) {
  let s = String(name || "")
    .replace(/[<>:"\/\\|?*\x00-\x1f]/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[. ]+|[. ]+$/g, "");
  if (s.length > max) s = s.slice(0, max).replace(/[. -]+$/, "");
  if (!s) s = "unnamed";
  if (/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i.test(s.split(".")[0])) s = "_" + s;
  return s;
}

// Shorten a file name but keep its extension (including the dot).
function cleanFile(name, max = 60) {
  const i = name.lastIndexOf(".");
  if (i > 0 && name.length - i <= 10) {
    const ext = name.slice(i).replace(/[<>:"\/\\|?*\x00-\x1f\s]/g, "");
    return clean(name.slice(0, i), max - ext.length) + ext;
  }
  return clean(name, max);
}

const safeExt = (e) => (/^\.[A-Za-z0-9]{1,8}$/.test(e) ? e : "");

// Remember the method of recent requests, so the log can say how LEO serves each download.
const reqMethod = new Map();
chrome.webRequest.onBeforeRequest.addListener(
  (d) => {
    if (["main_frame", "sub_frame", "xmlhttprequest", "other"].includes(d.type)) {
      reqMethod.set(d.url, d.method);
      if (reqMethod.size > 300) reqMethod.delete(reqMethod.keys().next().value);
    }
  },
  { urls: chrome.runtime.getManifest().host_permissions }
);

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  handle(msg, sender).then(sendResponse, (e) => sendResponse({ error: String(e) }));
  return true; // reply asynchronously
});

async function handle(msg, sender) {
  switch (msg.type) {
    case "whoami":
      return { tab: sender && sender.tab ? sender.tab.id : null };
    case "sleep":
      await new Promise((r) => setTimeout(r, Math.min(Number(msg.ms) || 0, 20000)));
      return { ok: true };
    case "expect": {
      // The page script is about to click a download button. Remember how to name the file.
      const tok = crypto.randomUUID();
      const pending = (await sget("pending")) || [];
      pending.push({ tok, dir: msg.dir, name: msg.name, mode: msg.mode, group: msg.group || "" });
      await sset("pending", pending);
      await sset("dl:" + tok, { state: "waiting" });
      return { tok };
    }
    case "poll": {
      let rec = (await sget("dl:" + msg.tok)) || { state: "unknown" };
      if (rec.id && rec.state === "started") {
        try {
          const [info] = await chrome.downloads.search({ id: rec.id });
          if (info) rec = { ...rec, named: !!info.filename };
        } catch (e) { /* ignore */ }
      }
      return rec;
    }
    case "openSettings":
      await chrome.tabs.create({ url: msg.url });
      return { ok: true };
    case "checkDownloads": {
      // Save a tiny file. When the browser is set to "ask where to save each file" it never settles on a name.
      const tok = crypto.randomUUID();
      const pending = (await sget("pending")) || [];
      pending.push({ tok, dir: msg.dir, name: "_setup_check", mode: "replace", group: "" });
      await sset("pending", pending);
      await sset("dl:" + tok, { state: "waiting" });
      // A real web address is needed: browsers do not show the Save window for data: addresses.
      const id = await chrome.downloads.download({ url: msg.url, filename: "_setup_check.png", conflictAction: "overwrite" });
      for (let i = 0; i < 10; i++) {
        await new Promise((r) => setTimeout(r, 300));
        const [info] = await chrome.downloads.search({ id });
        if (info && info.state === "complete") {
          try { await chrome.downloads.removeFile(id); } catch (e) { /* ignore */ }
          try { await chrome.downloads.erase({ id }); } catch (e) { /* ignore */ }
          return { ok: true };
        }
        if (info && info.state === "interrupted") {
          // the test file could not be fetched (not a Save-window problem): do not block the run
          try { await chrome.downloads.erase({ id }); } catch (e) { /* ignore */ }
          await sset("pending", ((await sget("pending")) || []).filter((p) => p.tok !== tok));
          return { ok: true, inconclusive: true };
        }
      }
      try { await chrome.downloads.cancel(id); } catch (e) { /* ignore */ }
      try { await chrome.downloads.erase({ id }); } catch (e) { /* ignore */ }
      await sset("pending", ((await sget("pending")) || []).filter((p) => p.tok !== tok));
      return { ok: false };
    }
    case "cancel": {
      const pending = ((await sget("pending")) || []).filter((p) => p.tok !== msg.tok);
      await sset("pending", pending);
      return { ok: true };
    }
    case "clearPending":
      await sset("pending", []);
      return { ok: true };
    case "saveText": {
      // Name the log through the same filename handler as every other download.
      const slash = msg.path.lastIndexOf("/");
      const dir = msg.path.slice(0, slash);
      const name = msg.path.slice(slash + 1).replace(/\.[^.]+$/, "");
      const ext = msg.ext || ".csv";
      const mime = msg.mime || "text/csv";
      const tok = crypto.randomUUID();
      const pending = (await sget("pending")) || [];
      pending.push({ tok, dir, name, mode: "replace", group: "", ext });
      await sset("pending", pending);
      await sset("dl:" + tok, { state: "waiting" });
      const body = (ext === ".csv" ? "\ufeff" : "") + msg.text;
      const url = "data:" + mime + ";charset=utf-8," + encodeURIComponent(body);
      const id = await chrome.downloads.download({ url, filename: name + ext, conflictAction: "overwrite" });
      return { id, tok };
    }
  }
  return { error: "unknown message" };
}

chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  (async () => {
    const pending = (await sget("pending")) || [];
    const entry = pending.shift();
    if (!entry) { suggest(); return; } // a download we did not ask for: leave it alone
    await sset("pending", pending);

    const base = (item.filename || "").split(/[\\/]/).pop() || "download";
    const ext = base.includes(".") ? base.slice(base.lastIndexOf(".")) : "";
    const dir = String(entry.dir).split("/").map((p) => clean(p, 90)).join("/");
    const name =
      entry.mode === "replace"
        ? clean(entry.name, 90) + safeExt(entry.ext || ext)
        : clean(entry.name, 100) + " - " + cleanFile(base, 40);
    const path = dir + "/" + name;

    let req = "";
    try { req = `${reqMethod.get(item.url) || "?"} ${new URL(item.url).protocol === "http:" || new URL(item.url).protocol === "https:" ? new URL(item.url).pathname : item.url.split(":")[0] + ":"}`; } catch (e) { /* ignore */ }
    await sset("dl:" + entry.tok, { state: "started", id: item.id, path, group: entry.group, base, req });
    await sset("id:" + item.id, entry.tok);
    suggest({ filename: path, conflictAction: "overwrite" });
  })();
  return true;
});

chrome.downloads.onChanged.addListener(async (delta) => {
  const tok = await sget("id:" + delta.id);
  if (!tok) return;
  const rec = (await sget("dl:" + tok)) || {};
  if (delta.state && delta.state.current === "complete") {
    rec.state = "complete";
    try {
      const [where] = await chrome.downloads.search({ id: delta.id });
      if (where && where.filename && rec.path) {
        // compare folders only: the browser may shorten or renumber a file name, but not the folder
        const actual = where.filename.replace(/\\/g, "/");
        const dirOf = (p) => p.slice(0, p.lastIndexOf("/")).toLowerCase();
        if (!dirOf(actual).endsWith(dirOf(rec.path))) rec.misplaced = actual;
      }
    } catch (e) { /* ignore */ }
    if (rec.group) {
      // Same original name and same size as an earlier letter of this form: flag it, never delete it.
      const [info] = await chrome.downloads.search({ id: delta.id });
      if (info && info.fileSize > 0) {
        const sig = `sig:${rec.group}|${rec.base}|${info.fileSize}`;
        const prior = await sget(sig);
        if (prior && prior !== rec.path) rec.dupOf = prior.split("/").pop();
        else await sset(sig, rec.path);
      }
    }
  }
  if (delta.state && delta.state.current === "interrupted") {
    rec.state = "failed";
    rec.error = (delta.error && delta.error.current) || "interrupted";
  }
  await sset("dl:" + tok, rec);
});

// Clicking the toolbar icon opens the All Projects page, where the export panel appears.
chrome.action.onClicked.addListener(() => {
  chrome.tabs.create({ url: "https://leo.lshtm.ac.uk/ActivityForm/FolderProjectList/0" });
});
