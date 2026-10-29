# LEO export tool (Python)

Saves your projects from LSHTM Ethics Online (LEO, `leo.lshtm.ac.uk`) to your computer before the system is retired.

For every project you can see in **All Projects**, and every form in its project tree, it saves:

- the **Documents** tab as one zip per form (the same file as "Download Selected");
- the **committee approval letters** from the **History** tab: favourable opinions, amendments approved by the RGIO, and responses to a provisional letter that were approved.

It also writes a log of everything it did, so you can check that nothing was missed.

You log in yourself, so SSO and MFA work as normal. The tool never sees or stores your password.

---

## Quick start

**1. Download the tool.** You need one file, `leo_export.py`, from this repository's `python` folder.

1. Open the file `leo_export.py` on GitHub. (If you are reading this page, it is in the same folder as this README.)
2. Above the code, at the right, click the **Download raw file** button (a downward arrow). The file saves to your Downloads folder. If you cannot find the button, click **Raw**, then right-click the page and choose **Save As**.
3. Check the saved file is called `leo_export.py`. Some browsers add `.txt` to the end. If yours is `leo_export.py.txt`, rename it to remove the `.txt`.

Or download everything at once: on the repository's front page, click the green **Code** button, then **Download ZIP**, and unzip it. The tool is the file `python/leo_export.py` inside.

**2. Install (once).** You need Python 3.9 or later from [python.org](https://www.python.org/downloads/).

| | Commands |
|---|---|
| macOS (Terminal) | `python3 -m pip install playwright`<br>`python3 -m playwright install chromium` |
| Windows (PowerShell) | `py -m pip install playwright`<br>`py -m playwright install chromium` |

Use `python3` on macOS and `py` on Windows in every command below.

**3. Open a terminal in the folder that contains `leo_export.py`.** If you saved the file in your Downloads folder, on a Mac open Terminal, type `cd ~/Downloads` and press Enter. Otherwise type `cd ` and drag the folder into Terminal. On Windows, open the folder in File Explorer, click the address bar, type `powershell` and press Enter. Files are saved into whichever folder you run the command from.

**4. Try three projects first.**

```
python3 leo_export.py --limit 3
```

A browser window opens. Log in to LEO. When you are in, the window closes and the run carries on in a hidden browser.

**5. Check the result.** Open the `LEO_export` folder and `export_log.csv` (see [Checking the result](#checking-the-result)).

**6. Run everything.**

```
python3 leo_export.py
```

Leave the computer on and awake. If the run stops for any reason, run the same command again. Finished forms are skipped.

---

## What you get

```
LEO_export/
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
  export_log.csv        one row per download, warning or error; also used to resume
  projects_index.csv    the All Projects list
```

- One folder per project, named `Project ID - Title`.
- One numbered folder per form, in project-tree order. Folder `01` is the main ethics application. Amendments and other forms follow.
- Forms that share a name, such as several annual reports, are numbered `1`, `2`, `3` in tree order.
- Each form folder holds one zip of everything on that form's Documents tab.
- **Approval letters** collates the letters from every form. Names start with the date and time, so they sort in the order issued, followed by the form name and the original file name.
- LEO's internal form IDs are not in the names. They are in `export_log.csv`.
- `--layout flat` gives the original layout instead, with every zip and letter side by side in the project folder.

---

## Restructuring an export you already have

If you downloaded with an earlier version, which put everything side by side in each project folder, move it into the structure above without downloading anything again:

```
python3 leo_export.py --restructure            # report only; writes restructure_report.csv
python3 leo_export.py --restructure --apply    # move the files
python3 leo_export.py --unrestructure          # undo, using restructure_report.csv
```

Add `--out FOLDER` if your export is not in `./LEO_export`.

What it does:

- Files are moved, never deleted or re-downloaded. Always run without `--apply` first and read `restructure_report.csv`.
- Each zip goes into its form's folder. Form names and order come from `_project.json` if your earlier run left one in the project folder; otherwise the names in the file names are used. Newer downloads do not create `_project.json`.
- Letters go to `Approval letters`, except two kinds, which go to `Other History attachments` in the same project folder: letters whose History row was not an approval (judged from `export_log.csv` and the History pattern), and a second copy of a letter with identical content.
- A letter with no row in the log is kept as an approval letter.
- Run it from the folder that holds `export_log.csv`, because it uses it (and any `_project.json` files). Run `--tidy` first if you were going to. `--tidy` relies on the old file names.
- After restructuring, `python3 leo_export.py` carries on downloading any remaining projects in the new layout. Forms already marked complete are skipped.

---

## Logging in, and running in the background

- The tool opens a visible browser for login, then **moves the run into a hidden browser** that carries the same session. Nothing appears on screen, so you can minimise Terminal and carry on with other work.
- If LEO asks for a login again part-way through, a window opens once. Log in and the run continues from the same project.
- If the hidden browser cannot start or does not accept the session, the tool says so and carries on in the visible window.
- `--headed` keeps the window visible for the whole run.
- `--channel chrome` or `--channel msedge` uses a browser you already have, instead of the one Playwright downloaded. This can help on managed computers.
- Your login is kept in `LEO_export/.browser_profile`. Do not share or copy that folder.

---

## Checking the result

Open `export_log.csv` and filter the `status` column. Anything other than `ok` or `info` deserves a look.

| `status` | Meaning |
|---|---|
| `ok` | Saved. |
| `info` | Note only, for example "3 other attachments not downloaded (description did not match)". |
| `duplicate` | A letter with identical content to one already saved for this form. It was not kept. |
| `warning` | The Documents table lists a different number of files from the number inside the zip. Check that form. |
| `empty` | The tab had no table (for example, no History table). Worth opening that form in LEO to confirm. |
| `error` | A download did not start, a button was not found, or a page did not load. The form is retried on the next run. |

When a form finishes, a row with item `form` is added to `export_log.csv`, with status `complete` or `needs_review`. Only `complete` forms are skipped on a re-run.

Older versions kept this in `state.json`. If that file is in the output folder, its contents are copied into the log the first time you run, and it is then ignored. You can delete `state.json` and any `_project.json` files once that has happened. If you plan to restructure an existing export, do that first, because restructure uses `_project.json` for form names.

Useful columns in the log: `project_id`, `form_name`, `item` (`documents`, `history attachment`, ...), `file`, `detail` (the History row's date and wording for letters).

For scale: a preview scan of 175 forms across 97 projects took about 11 minutes. Downloads add to that.

---

## Choosing which History letters to save

LEO records an approval in several different wordings. By default a History row is downloaded when its description matches any of these (case-insensitive):

- `favourable opinion` (but not `unfavourable opinion`)
- `approved by the RGIO` (amendment approvals)
- `response to the provisional letter has been approved`

Not downloaded by default: provisional approvals, "approval not required" notices, unfavourable opinions, annual report acceptances, and rows such as "Form submitted" or "Form signed".

### Preview before you commit

```
python3 leo_export.py --history-scan
```

This visits every form's History tab and records each row that has an attachment, marked `DOWNLOAD` or `skip`. It downloads nothing and does not mark forms complete. In `export_log.csv`:

- item `history scan`: one line per attachment row;
- item `history scan summary`: one line per form, including forms with no attachments, so you can confirm every form was visited.

Read through the `skip` descriptions. If something you want is being skipped, change the pattern.

### Change the pattern

`--history-pattern` takes a regular expression:

```
python3 leo_export.py --history-pattern "favourable opinion|approved by the RGIO|response to the provisional letter has been approved|provisionally approved"
```

The pattern replaces the default, so include every wording you want. The example above adds provisional approvals to the three defaults.

`--history-all` downloads every History attachment regardless of wording.

### Clean up an earlier export

If a folder was made with a different pattern, or before duplicates were handled:

```
python3 leo_export.py --tidy            # report only; writes tidy_report.csv
python3 leo_export.py --tidy --apply    # move the files
python3 leo_export.py --untidy          # put everything back
```

`--tidy` moves letters that do not match the current pattern, and letters with identical content to another letter of the same form, into `LEO_export/_tidy_removed/`. Nothing is deleted. Read `tidy_report.csv` before using `--apply`. Delete `_tidy_removed` yourself once you are satisfied.

---

## Options

| Option | Effect |
|---|---|
| `--out FOLDER` | Output folder (default `./LEO_export`). On Windows use a short path such as `C:\LEO_export`, because Windows limits full paths to about 260 characters. |
| `--limit N` | Only the first N projects. For trial runs. |
| `--project ID` | Only this Project ID. Repeat for several. |
| `--owned-only` | Only projects where you are the owner. |
| `--dry-run` | List projects and forms. Download nothing. |
| `--force` | Download forms again even if already marked complete. |
| `--layout flat` | The original layout: every zip and letter side by side in the project folder. |
| `--restructure`, `--apply`, `--unrestructure` | Move an existing flat export into the structured layout (see above). |
| `--history-pattern REGEX` | Which History rows to download (see above). |
| `--history-all` | Download every History attachment. |
| `--history-scan` | Preview only (see above). |
| `--tidy`, `--apply`, `--untidy` | Clean up an existing export (see above). |
| `--headed` | Keep the browser window visible. |
| `--channel chrome` / `msedge` | Use an installed browser. |
| `--delay SECONDS` | Pause between actions (default 1). |
| `--download-timeout SECONDS` | How long to wait for each download (default 180). Raise it for very large forms. |
| `--dump-html` | Diagnostic: save the HTML of the Documents and History tabs of the first form to `_debug/`, then stop. |

---

## Troubleshooting

| Problem | What to do |
|---|---|
| `can't open file '.../leo_export.py'` | The terminal is in the wrong folder. Change into the folder that contains the script (see Quick start, step 3). |
| `No module named playwright` | Run the install commands again. |
| `Executable doesn't exist` | Run `python3 -m playwright install chromium`. |
| Windows opens the Microsoft Store when you type `python` | Use `py` instead. |
| "Could not continue in a hidden browser" | The tool is staying in the visible window and will still work. Add `--headed` to stop it trying. |
| Many `error` rows such as "Download Selected button not found" | LEO's page layout may differ from what the tool expects. Run `--dump-html` and look at `LEO_export/_debug/`. |
| Repeated `error` rows with timeouts on large forms | Add `--download-timeout 600`. |
| Windows path errors | Use a short `--out`, for example `C:\LEO_export`. |
| Run stopped part-way | Run the same command again. Finished forms are skipped. |

If you need to ask for help, send the relevant rows of `export_log.csv`. The `_debug` files contain page HTML, so check them for sensitive content first.

---

## Notes for technical readers

- **Stack.** Python with [Playwright](https://playwright.dev/python/) driving Chromium. One file, `leo_export.py`, with no other dependencies.
- **Target.** Infonetica LEO (the pages report version 2.21.3). The script reads the All Projects table (`#projectTableView`, paginated), the project tree (`div.well.tree`), and the lazily loaded Documents and History tab containers (`#form-documents-container`, `#form-history-container`). A LEO upgrade could change these.
- **Downloads.** Playwright captures each download event, including ones from popups, and saves it under a name built from the form and History row. Filenames are sanitised for Windows and macOS.
- **Session hand-off.** After login the visible context's `storage_state` is copied into a headless context, and the run is verified against the project list before the window closes. If a login page appears later, the tool reopens a visible window, logs in again, and retries the same project.
- **Resume.** The log's `form` rows map form ID to `complete` or `needs_review`; the last row for a form wins. A retried form overwrites its earlier files rather than creating copies.
- **De-duplication.** Within a form, a letter whose SHA-256 matches an earlier letter is removed.
- **Politeness.** One action at a time, with a configurable pause (`--delay`).

### Limits

- Only the Documents and History tabs are exported. Submissions, Signatures, Correspondence, Collaborators, and the project-level page above the forms are not.
- Which letters are saved depends on the wording of History rows. Use `--history-scan` to check this across all projects.
- Projects that LEO flags as not accessible are still attempted, and any failure is logged.
- The login hand-off assumes the session lives in cookies. If it does not, the tool falls back to the visible window.

### Data handling

The output holds research documents and committee correspondence. Store it as you would the originals, and do not share `LEO_export/.browser_profile`.
