# LEO Export Tools

LSHTM Ethics Online (LEO) is being replaced. These tools save the records from every project you can see in LEO, so you keep a copy:

- the documents for each form (the ethics application, each amendment, each report), as a zip in its own folder (a closed form with no documents listed gets its submitted copy from the History tab instead);
- the committee approval letters, collected in one folder per project.

You log in to LEO yourself, as normal. The tools never see or store your password.

> **Handle the saved files with care.** They contain research documents and committee correspondence. Treat them like the originals.

---

## Choose a tool

There are two tools. They do the same job and save files in the same folder structure. The extension shortens long project and form names more, to keep paths inside the Windows limit, so the same folder can have a slightly different name. **Pick one.**

### A. Python tool

For people who are comfortable using a terminal.

- **Download:** [`leo_export.py`](python/leo_export.py)
- **How to use it:** [`python/README.md`](python/README.md)
- **Comparing two exports:** [`compare_exports.py`](python/compare_exports.py) checks one tool's output against the other's.

### B. Browser extension

For everyone else. It works in Chrome and Edge, and needs no terminal.

- **Download:** [`leo-export-extension.zip`](browser-extension/leo-export-extension.zip?raw=true)
- **How to use it:** [`browser-extension/README.md`](browser-extension/README.md)

---

## Good to know

- Both tools work only with LEO's current page layout. If LEO is updated, they may stop working.
- Both run on your own computer and send your data nowhere except to your own saved files. The extension's access and promises are set out in the "Security and privacy" section of [`browser-extension/MORE_INFORMATION.md`](browser-extension/MORE_INFORMATION.md).
- They have not had an independent security review, and are provided as is.
- Some work computers may not allow the extension, or changes to browser download settings. If so, ask IT.

## Problems

Open an issue, and say which tool you used and whether you are on Windows or Mac. Include the message you saw. Do not attach exported documents, and check any log you attach for project titles or names first.
