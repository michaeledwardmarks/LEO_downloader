# LEO Project Exporter: more information

**For information only.** You do not need to read this to use the extension. The steps are in `README.md`. This file is for people who are curious, or who are fixing a problem.

---

## Security and privacy

This is a tool for exporting your own LEO records to your own computer. This section says what it can access, when, and why, and what it does not and will not do. It is provided as is, and it has not had an independent security review. It is three small files of plain, readable code, so IT can check it (see "Checking it yourself" below).

### What it can access, when, and under which permission

| What it can access | When | Permission (in `manifest.json`) |
|---|---|---|
| **LEO pages, and only LEO.** It adds a small panel to pages on `leo.lshtm.ac.uk`. It reads the project list, each project's form tree, and the Documents and History tables (form names, dates, History row descriptions). | The panel appears on every LEO page. It reads page content only after you click **Choose projects…** and start an export. | Access to `https://leo.lshtm.ac.uk/*` only |
| **Your download location.** It saves files into a folder you name, and checks the name, size and state of its own downloads. | During an export, plus one tiny test file before it starts (see below). | `downloads` |
| **Browser storage.** It remembers your project selection, its progress, and the log. | From when you start an export until you click **Start over** or remove the extension. | `storage` |
| **The method and address of requests to LEO** (for example, whether a request was a `GET` or a `POST`, and its page address). It does not read the content, headers or cookies of those requests. | While the browser is open and LEO pages make requests. The last 300 are kept in memory only and are never saved. | `webRequest` |
| **New tabs.** It can open the All Projects page and your browser's download settings page. | Only when you click the toolbar icon or **Open download settings**. | None needed |

The only requests the extension makes itself are:

- one small image from LEO (`/Content/Icons/help-blue.png`), downloaded as a test before an export and then deleted, to check the browser will save files without asking;
- the files you asked for, by clicking LEO's own **Download Selected** and **Download** buttons, which the browser then fetches from LEO as normal.

### What it stores, and where

- **In your browser only:** your selection, progress, and the log, in the browser's local extension storage. This is not synced to your account or any other device, and removing the extension deletes it.
- **On your computer only:** the exported files and `export_log.csv`, in the download folder you chose.
- **The log is sensitive.** It contains project IDs and titles, form names, file paths, and the wording of History rows, which can include people's names. Handle it like the export itself.

### What it will not do

- It will **not send, upload or store anything on the cloud**, on a commercial service, or on any server of any kind. It has no analytics, tracking, advertising, error reporting, email, or connection to any AI service.
- It will **not contact any website other than LEO**. It has no access to other sites or to the content of your other tabs.
- It will **not see or store your password or login.** You log in to LEO as normal in the browser. The extension has no access to cookies, passwords, saved logins, your browsing history, bookmarks or clipboard.
- It will **not open or read the contents of the files it downloads.** It sees only each file's name, where it was saved, its size, and its download state.
- It will **not change or delete your files.** The one file it removes is its own test image.
- It will **not create, edit, submit, sign or delete anything in LEO.** It only reads pages and uses these controls: the Documents and History tabs, the selection boxes on the Documents tab, page buttons for browsing long tables, and the download buttons. As with any download, LEO may record that documents were downloaded.
- It will **not run when the browser is closed**, start by itself, or run on any other website.
- It will **not update itself or load code from anywhere.** It runs only the files in the folder you installed from, and changes only if you replace that folder.

### Things outside its control

- **Cloud syncing of your Downloads folder.** Some computers sync the Downloads folder to a cloud service, for example OneDrive folder backup or iCloud Drive. The extension does not do this, but if the files must stay off the cloud, check those settings, or choose a download location that is not synced.
- **Browser download history.** Chrome and Edge list downloaded file names in their downloads page (`chrome://downloads`, `edge://downloads`). You can clear that list there.
- **Security software.** Antivirus or monitoring software on your computer may scan the files as they are saved.
- **Who can change the folder.** An extension loaded from a folder runs whatever is in that folder. Keep it somewhere only you can edit, and remove it when you have finished (step 7 of the README).

### Checking it yourself

The extension is three files, and a technical colleague or IT can read them in a few minutes:

| File | Lines | What to look at |
|---|---|---|
| `manifest.json` | 41 | The permissions list and the single website it can access. |
| `background.js` | 194 | Download naming and checks. It has no network code of its own. |
| `content.js` | 788 | The panel, the project picker, and the clicks on LEO's pages. |

Searching the code for `fetch`, `XMLHttpRequest`, `WebSocket` and `sendBeacon` finds nothing, and the only web address in it is `leo.lshtm.ac.uk`.

---

## What is saved

- **Saved:** the Documents tab of each form, as one zip, and the attachment on each History row that records an approval. That means a favourable opinion, an amendment approved by the RGIO, a response to a provisional letter that has been approved, a "Study Closed" notice (the approval of an End of Study form), one of the committee's provisional letters ("further clarification has been requested", "provisionally approved"), or another decision: an unfavourable opinion, a "not valid" or invalidated notice, or an "ethics approval is not required" notice. For Annual Report and Protocol Deviation forms, which record their outcome as a status change, the letter on the "status changed to Favourable" row and on an RGIO acceptance is saved too.
- **Forms with no documents listed:** for a form whose Documents tab lists nothing (LEO says "There are currently no documents listed", as it does for closed End of Study forms), the form's own copy from the History tab is saved instead, in that form's folder: its "Form submitted" attachment (the submitted form; if the form was submitted more than once, only the latest). There is no zip for such a form. If it has no submitted copy either, a short text file is saved in its folder saying why: `Form never submitted.txt` when LEO's Submissions tab says the form has not been submitted yet, otherwise `No files held in LEO.txt`. Its approval letter goes in the **Approval letters** folder as usual.
- **Not saved:** the Submissions, Signatures, Correspondence and Collaborators tabs, other History attachments, and the status-change rows between review stages.

## Folder layout

```
Downloads/LEO_export/
  34352 - SNAP EOS Survey/
    01 - Ethics Application & CARE Form/
      Ethics Application & CARE Form - all documents.zip
    02 - Amendment Form - 01/
      Amendment Form - 01 - all documents.zip
    03 - Annual Report Form 1/
      Annual Report Form 1 - all documents.zip
    04 - Annual Report Form 2/
      Annual Report Form 2 - all documents.zip
    Approval letters/
      2022-03-11 0912 - Ethics Application & CARE Form - Favourable opinion letter.pdf
      2023-01-20 1433 - Amendment Form - 01 - Approval.pdf
  export_log.csv
```

- One folder per project. Inside it, each form has its own numbered subfolder, in the order the forms appear in LEO's project tree. Folder `01` is the main ethics application. The amendments, annual reports and any other forms follow, each in its own folder at the same level. They are not placed inside the `01` folder.
- Forms that share a name, such as several annual reports, are numbered 1, 2, 3.
- **Approval letters** collects the approval letters from every form. Names start with the date and time, so they sort in the order issued.
- Names are shortened so that paths stay inside the Windows limit of about 260 characters.

## The log (`export_log.csv`)

Open it in Excel or Numbers and look at the `status` column.

| `status` | Meaning |
|---|---|
| `OK` | Saved. |
| `INFO` | A note only, such as "3 other attachments not downloaded". |
| `CHECK` | A letter has the same name and size as another letter of the same form, so it may be a duplicate. Nothing is deleted automatically. |
| `WARNING` | The Documents table showed a different number of files from what was expected. Check that form. |
| `EMPTY` | The tab had no table. The detail shows what the tab said instead. A message such as "No documents…" means the form really has none. "Tab stayed blank" means it did not load: that form is marked `NEEDS_REVIEW` and nothing is saved for it. |
| `ERROR`, `NEEDS_REVIEW`, `MISPLACED` | Something failed, and the form is not finished. A new run starts again from the beginning for the projects you tick, so tick only the projects that contain these forms. |

The `documents` rows also say how LEO served each file, for example `served as GET /...`. Include a few of these rows when asking for help.

## If something goes wrong

| What you see | What to do |
|---|---|
| "Your browser is set to ask where to save each file…" | Switch that setting off (step 4 of the README), then click **Try again**. |
| A Save window appears during the run | Switch the same setting off, then press **Pause** and **Resume**. |
| "A file was not saved where the exporter asked…" | The browser saved a file somewhere other than planned, so the export paused. This usually means the browser is overriding the save location, for example because it asks where to save each file. Fix the setting, move or delete the misplaced files, then press **Resume**. |
| "leo.lshtm.ac.uk wants to download multiple files" | Click **Allow**. |
| A PDF opens in a tab, in Acrobat or in another PDF program while the export runs | Close it, then follow the PDF settings in step 4 of the README. A window on top of LEO can slow the page. If the log shows "tab stayed blank", run those projects again. |
| "Paused: this is not a project page (session expired?)" | Log in to LEO again, open All Projects, and click **Resume**. |
| "An export is running in another browser tab" | Go back to the tab where you started the export. Only one export can run at a time. |
| Nothing happens when you click the toolbar icon | Check that **LEO Project Exporter** is switched on at the extensions page. |
| `ERROR` rows with `FILE_NAME_TOO_LONG` | Use a shorter download location and run again. |
| "Manifest file is missing or unreadable" when installing | You chose the wrong folder. Choose the one that contains `manifest.json`. |

If you need help, send the message shown in the panel, and a few rows from `export_log.csv`.

## Saving somewhere other than Downloads

A browser extension can only save inside the browser's own download location, which is normally your **Downloads** folder. The folder name you type in the picker becomes a folder inside it.

To use a different location, open the Downloads settings page, click **Change** next to **Location**, and choose a folder before you run the export. On Windows, choose a short path such as `C:\LEO`.

## If the export stops

The export stops if the browser is closed, the computer sleeps, or you are logged out. When you return, the panel shows **Paused** or **Interrupted**. Log in to LEO, open All Projects, and click **Resume**. Forms already finished are not downloaded again.

Other buttons on the panel: **Save log** saves the log so far, and **Start over** forgets the run's progress so you can begin again.

## Why the settings are needed

- **Ask where to save each file.** When this is on, the browser opens a Save window for every download, and no extension can override that. Before it starts, the exporter saves a tiny test file to check. If the browser does not settle on a file name, the exporter stops and says so. Some work computers lock the setting on. If you cannot switch it off, ask IT.
- **PDFs opening on screen.** The approval letters are PDFs. If the browser opens them in its viewer, or the computer opens them in Acrobat or another program, a window can end up on top of LEO. Browsers slow the timers of a page that is hidden or covered, and a slow page can fail to load a tab in time. The extension cannot see or stop another program opening a file, so the settings in step 4 of the README are the fix.
- **Multiple downloads.** An export makes many downloads from one site, and the browser may ask you to approve that. Adding `leo.lshtm.ac.uk` to the Allow list approves it in advance.
- **Staying awake.** The export runs in the browser tab, so it stops if the computer sleeps.

## Managed computers

Some LSHTM computers do not allow Developer mode or changes to download settings. If so, ask IT. The extension can instead be published privately on the Chrome Web Store, which needs a one-off developer account and review by Google.

## How it works

- It drives the LEO pages you are logged in to, in the browser tab: it reads the All Projects list and each project's tree, opens each form's Documents and History tabs, clicks **Download Selected**, and clicks the Download button on History rows that record an approval.
- It tells the browser what name and folder to use for each file, and watches each download until it finishes.
- **Checks it makes:** a test download before starting; after each file, whether it landed in the folder planned (it pauses at the first mismatch); and whether two letters of the same form share a name and size.
- **One driver tab.** The tab that starts the export does the work. Other LEO tabs show a notice and do nothing.
- **Progress** is kept in the browser's storage, so a run survives page changes and can be resumed. A run that has not been touched for about 90 seconds is treated as interrupted and waits for **Resume**.
- **Waiting** is done by the extension's background worker, because browsers slow a hidden page's own timers.

## Limits

- It has been tested against a mock of LEO and has not been confirmed on every LEO page layout.
- It cannot open the downloaded files, so it cannot check zip contents or remove duplicate letters by content. The Python version can.
- Exports made with versions before 1.6.0 have `undated` in many file names, because LEO's 12-hour times could not be read. The Python version's `--redate` renames them from the log; or run the export again with 1.6.0 or later.
- It has no top-up mode. To add letters or zips to an earlier export, run the same projects again: files are saved under the same names, so they are overwritten in place. The Python version can top up letters only (`--letters-only`) or re-check forms that have no zip (`--retry-empty`).
- Only the Documents and History tabs are exported.
