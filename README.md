# ehl-final

BMW — AI for Product Decision Making, EHL Munich, 10–11 October 2026.

Private repository: https://github.com/jakobtfr/ehl-final

This repository currently contains research, source records, and archive utilities. No application architecture or implementation has been selected yet.

## Start here

- [Challenge brief and judging criteria](notes/challenge.md)
- [Every BMW channel message](notes/discord-transcript.md)
- [Data inventory and interpretation caveats](notes/data-inventory.md)
- [Build discussion](notes/build-discussion.md)
- [Download provenance and checksums](notes/source-inventory.json)
- [Coverage and preservation record](notes/coverage.md)

## Local source archive

| Directory | Contents |
| --- | --- |
| `archive/drive/BMW-Data/` | All eight original Google Drive files |
| `archive/discord/` | Saved channel HTML, page assets, complete extracted messages and attachment records |
| `archive/discord/attachments/` | All nine original channel attachments, including seven images |
| `archive/documents/` | Briefing, keynote, BMW Group Report 2025, and linked Entire event guide |
| `archive/extracted/` | Searchable PDF/slide text, workbook cells/formulas/cached values, image OCR |

**The archive is local and gitignored. A GitHub clone does not contain the raw downloads.** BMW explicitly asked participants not to push the Google Drive input data. Keep `archive/` when moving or backing up this workspace; the manifest records what belongs in it and detects changes. Original files are authoritative; text and OCR are convenience derivatives.

## Archive utilities

Requires Python via `uv`; OCR additionally uses macOS Vision through Swift.

```sh
# Redownload the Drive folder into a new snapshot if updating an existing archive.
uvx gdown --folder 'https://drive.google.com/drive/folders/1AyPzFu7qoNuCTW0tqlBCJggbmG_MZUem' -O archive/drive/

# Parse a complete Discord HTML page saved from the authenticated browser.
uv run scripts/capture_discord.py archive/discord/bmw-channel.html

# Produce searchable local derivatives without modifying originals.
uv run scripts/extract_sources.py
swift scripts/ocr_images.swift archive/discord/attachments/*.png archive/extracted/briefing-page-*.png

# Verify source hashes and Git exclusion; does not rewrite the reference manifest.
uv run scripts/verify_archive.py
```

Discord attachment URLs expire. The inventory retains the originating message URLs, so fresh download links can be retrieved from the channel. No Discord credentials or browser sessions are stored in the repository.
