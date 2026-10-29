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

Write down:

- the download **Location**;
- whether **Ask where to save each file before downloading** is on or off (Edge: a toggle that starts "Ask me…");
- whether `leo.lshtm.ac.uk` is already in the **Allow** list.

You will put these back in step 7.

## 3. Install

1. Unzip `leo-export-extension.zip`. On Windows, right-click it and choose **Extract All**.
2. Move the unzipped folder somewhere permanent, such as Documents. Do not delete it while you use the extension.
3. Open `chrome://extensions` (Edge: `edge://extensions`).
4. Switch on **Developer mode** (Chrome: top right. Edge: left menu).
5. Click **Load unpacked** and choose the folder that contains `manifest.json`.
6. Click the puzzle-piece icon in the toolbar, then the pin next to **LEO Project Exporter**.

## 4. Change two settings

1. Open the **Downloads** settings page. Switch **Ask where to save each file before downloading** **off**.
2. Open the **Automatic downloads** page. Next to **Allowed to automatically download multiple files** (Edge: **Allow**), click **Add**, type `leo.lshtm.ac.uk`, and click **Add**.

Optional: for a long export, set your computer not to sleep while plugged in (Mac: System Settings > Battery. Windows: Settings > System > Power). Write down the old value.

## 5. Run the export

1. Log in to LEO.
2. Click the blue download icon in the toolbar. It opens **All Projects**.
3. In the panel at the bottom right, click **Choose projects…**
4. Tick the projects you want. For a first try, pick two or three.
5. Under **Save into folder**, keep `LEO_export` or type another name.
6. Click **Download N projects**.
7. Wait until the panel says **Finished**. Keep that window open: do not close or minimise it. Other tabs and programs are fine.

If the panel shows a message, follow what it says. To stop, click **Pause**. To carry on, log in to LEO, open All Projects, and click **Resume**.

## 6. Check the result

1. Open your **Downloads** folder, then `LEO_export` (or the name you chose).
2. Each project has its own folder, with a zip for each form and an **Approval letters** folder.
3. Open `export_log.csv` and look for rows marked `ERROR`, `NEEDS_REVIEW` or `MISPLACED`.

The export contains research documents and committee correspondence. Copy it to its permanent home and check it before deleting anything.

## 7. Remove the extension and restore your settings

This does not touch your exported files.

1. Open `chrome://extensions` (Edge: `edge://extensions`). Find **LEO Project Exporter** and click **Remove**.
2. Delete the unzipped folder and the zip.
3. Switch **Developer mode** off.
4. On the **Downloads** page, switch **Ask where to save each file before downloading** back on if it was on before. Restore **Location** if you changed it.
5. On the **Automatic downloads** page, remove `leo.lshtm.ac.uk` from the **Allow** list if it was not there before.
6. Restore your sleep settings if you changed them.
