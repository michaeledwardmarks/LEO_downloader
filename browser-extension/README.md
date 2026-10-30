# LEO Project Exporter

Saves your LEO projects to your computer: a zip for each form, plus the approval letters. Works in Chrome or Edge, on Windows or Mac. No Python or Terminal needed.

It only works on `leo.lshtm.ac.uk`, sends nothing to anyone, and keeps no copies except the files saved on your own computer. What it can access and what it will not do is set out in `MORE_INFORMATION.md`, under "Security and privacy". You do not need to read that file to use the extension.

## 1. Download the extension

1. On GitHub, open the `browser-extension` folder and click **`leo-export-extension.zip`**.
2. Click **Download** (it may be labelled **Download raw file** or **View raw**). The zip saves to your Downloads folder.

Already have the zip, or reading this from inside it? Go to step 2.

Or download everything: on the repository's front page, click the green **Code** button, then **Download ZIP**, and unzip it. The extension is the `browser-extension` folder inside. In step 3, choose that folder instead of unzipping the extension zip.

## 2. Write down your settings

Type each address into the address bar and press Enter.

| | Chrome | Edge |
|---|---|---|
| Downloads | `chrome://settings/downloads` | `edge://settings/downloads` |
| Automatic downloads | `chrome://settings/content/automaticDownloads` | `edge://settings/content/automaticDownloads` |
| PDF documents | `chrome://settings/content/pdfDocuments` | `edge://settings/content/pdfDocuments` |

Write down:

- the download **Location**;
- whether **Ask where to save each file before downloading** is on or off (Edge: a toggle that starts "Ask me…");
- whether `leo.lshtm.ac.uk` is already in the **Allow** list;
- the **PDF documents** setting (Chrome: **Open PDFs in Chrome** or **Download PDFs**. Edge: whether **Always download PDF files** is on or off).

You will put these back in step 7.

## 3. Install

1. If you already have an older version installed, open `chrome://extensions` (Edge: `edge://extensions`) and click **Remove** on **LEO Project Exporter** first. Then unzip `leo-export-extension.zip`. On Windows, right-click it and choose **Extract All**.
2. Move the unzipped folder somewhere permanent, such as Documents. Do not delete it while you use the extension.
3. Open `chrome://extensions` (Edge: `edge://extensions`).
4. Switch on **Developer mode** (Chrome: top right. Edge: left menu).
5. Click **Load unpacked** and choose the folder that contains `manifest.json`.
6. Click the puzzle-piece icon in the toolbar, then the pin next to **LEO Project Exporter**.

## 4. Change three settings

1. Open the **Downloads** settings page. Switch **Ask where to save each file before downloading** **off**.
2. Open the **Automatic downloads** page. Next to **Allowed to automatically download multiple files** (Edge: **Allow**), click **Add**, type `leo.lshtm.ac.uk`, and click **Add**.
3. Open the **PDF documents** page. Choose **Download PDFs** (Edge: switch **Always download PDF files** on). Otherwise the approval letters can open on screen as they are saved, and a window on top of LEO can slow the page and make forms fail.

**If PDFs still open after each download** (in Acrobat, Preview or another PDF program), the browser has been told to open that file type automatically. This is a separate setting:

1. Open the downloads list: click the downloads icon in the toolbar, or press Ctrl+J (Mac: Cmd+Shift+J).
2. Click the three dots (or right-click) next to a PDF and untick **Always open files of this type**. Chrome may word it **Always open with system viewer**. If the list is empty, download any PDF from LEO by hand first.
3. In some versions, **Settings > Downloads** has a **Clear** button next to **Open certain file types automatically after downloading**. Use it if you see it.
4. If the Adobe Acrobat extension is installed, switch it off at `chrome://extensions` (Edge: `edge://extensions`) while the export runs.

If PDFs still open, Acrobat or the computer's settings may be doing it, and some work computers lock these settings. Ask IT.

Optional: for a long export, set your computer not to sleep while plugged in (Mac: System Settings > Battery. Windows: Settings > System > Power). Write down the old value.

## 5. Run the export

1. Log in to LEO.
2. Click the blue download icon in the toolbar. It opens **All Projects**.
3. In the panel at the bottom right, click **Choose projects…**
4. Tick the projects you want. For a first try, pick two or three.
5. Under **Save into folder**, keep `LEO_export` or type another name.
6. Click **Download N projects**.
7. Wait until the panel says **Finished**. Keep that window open: do not close or minimise it. Other tabs and programs are fine, but close any PDF that opens on screen (see step 4).

If the panel shows a message, follow what it says. To stop, click **Pause**. To carry on, log in to LEO, open All Projects, and click **Resume**.

## 6. Check the result

1. Open your **Downloads** folder, then `LEO_export` (or the name you chose).
2. Each project has its own folder. Inside it, the ethics application is in folder `01`, and each amendment, annual report or other form has its own numbered folder after it, holding a zip of that form's documents. The approval letters from all the forms are together in one **Approval letters** folder.
3. Open `export_log.csv` and look for rows marked `ERROR`, `NEEDS_REVIEW` or `MISPLACED`. Those forms are not finished. Start a new export, tick only the projects that contain them, and check the log again.

The export contains research documents and committee correspondence. Copy it to its permanent home and check it before deleting anything.

## 7. Remove the extension and restore your settings

This does not touch your exported files.

1. Open `chrome://extensions` (Edge: `edge://extensions`). Find **LEO Project Exporter** and click **Remove**.
2. Delete the unzipped folder and the zip.
3. Switch **Developer mode** off.
4. On the **Downloads** page, switch **Ask where to save each file before downloading** back on if it was on before. Restore **Location** if you changed it.
5. On the **Automatic downloads** page, remove `leo.lshtm.ac.uk` from the **Allow** list if it was not there before.
6. On the **PDF documents** page, put the setting back to what you wrote down in step 2. If you turned off opening PDFs automatically, or switched off the Acrobat extension, you can turn them back on the same way.
7. Restore your sleep settings if you changed them.
