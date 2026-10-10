# Coverage and preservation record

Capture date: 10 October 2026, Europe/Berlin.

## BMW channel

- Channel: `1553306479019429939`, server `1553151744047976549`.
- Verified the channel's explicit start marker in both the live UI and saved HTML.
- Read and preserved all 25 messages, from 10:37:32 through 17:17:08 local time.
- First message: `1558398067122643025`; final message: `1558498629122134029`.
- Revisited the live channel after extraction: the same final message was still the latest.
- Opened Threads: UI reported “There are no threads.”
- Opened Pinned Messages: UI reported no pinned messages.
- Two complete HTML snapshots and their asset directories are retained locally, plus a JSON export containing the rendered HTML of each message and a readable transcript. These preserve full long messages, attachment references, timestamps, visible edit information, reactions, and reply context from the captured page.
- All nine unique attachment URLs were downloaded as original files: one PDF, one PPTX, seven PNGs. Every image was inspected visually. OCR is a searchable aid, not a replacement for originals.

## Linked sources

- Drive: all eight files downloaded, with no folder-limit truncation. A separate fresh remote listing was reconciled against every local filename. The listing and file IDs are retained in `archive/drive/remote-listing.json`.
- Workbooks: all sheets extracted, including raw formulas and cached values. All supplied sheets are visible; originals are preserved unchanged.
- PDFs: successfully opened the full 2-page briefing, three 23/28/27-page option lists, and 434-page annual report. The image-only briefing was rendered and read visually; OCR was produced.
- PPTX: successfully opened all four slides and extracted their text and notes. Original slide artwork is preserved in the presentation.
- The BMW message pointing to `#entire` was followed. That channel contains the Entire sponsor guide, not another BMW presentation attachment. The linked event guide was downloaded as HTML and text. Its external tool documentation links remain in that snapshot; installing services or recursively mirroring the Entire documentation site was outside this source-collection task.
- Discord invite links and setup/access forms in the supplementary guide are preserved as links; no forms were submitted and no new service access was granted.

## Integrity and storage

- `notes/source-inventory.json` records 21 source artifacts: eight Drive files, nine original Discord attachments, the annual report, the Entire guide, and two HTML snapshots.
- `archive/checksums.json` additionally fingerprints every local archive artifact, including browser assets and searchable derivatives.
- The PDF and PPTX copied under `archive/documents/` were compared byte-for-byte by SHA-256 with their separately downloaded Discord originals.
- Every archive file is gitignored. Git holds notes, a complete message-text transcript, metadata, and utilities. It does not back up the raw files; preserving this workspace requires preserving `archive/` separately.
- Downloaded originals were not edited. Spreadsheet JSON, PDF text, and OCR may omit formatting, layout, or image content; consult the original whenever those details matter.

This is a verified snapshot of currently accessible content. New messages, future Drive changes, deleted messages, and past document versions are not part of the snapshot.
