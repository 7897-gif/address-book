# Demo video script (≈ 2 minutes)

The blog links a "complete running video". Record it once with this script and upload it
(YouTube / Bilibili / CSDN, or commit a small `.mp4` under `docs/demo/`).

## Before recording

```bash
python seed.py --reset      # 8 demo contacts, 3 favourites
python app.py --open        # http://127.0.0.1:8000/
```

1. Close other windows, set the browser to 1440×900, zoom 100 %.
2. Windows: `Win + Alt + R` (Xbox Game Bar) starts recording; press it again to stop.
   Alternative: OBS Studio, 30 fps, 1080p.
3. Keep the mouse movements slow; the recording is watched by a grader in one pass.

## Scenes

| # | Time | What to do | What it proves |
| --- | --- | --- | --- |
| 1 | 0:00–0:10 | Show the home page, scroll the contact grid once | Page style, data loaded from SQLite |
| 2 | 0:10–0:25 | Click the star on *Hannah Brooks*, click **Favorites** | 1.1 Bookmark contacts |
| 3 | 0:25–0:40 | Back to **All contacts**, type `chen` in the search box, clear it | Search across names and methods |
| 4 | 0:40–1:05 | **New contact** → name "Test Person", company "Demo Co", add a phone, an e-mail and a WeChat → save | 1.2 Multiple contact methods |
| 5 | 1:05–1:20 | Click the new card, change the phone, add an address → **Save changes** | Edit + multiple methods |
| 6 | 1:20–1:35 | **Export** → open `address-book.xlsx` in Excel, point at the columns `Phone 1`, `Phone 2`, `Email 1` | 1.3 Export |
| 7 | 1:35–1:55 | Back in the app, **Import** → choose `docs/address-book-export.xlsx` → show the summary dialog (duplicates skipped, 0 errors) | 1.3 Import + duplicate protection |
| 8 | 1:55–2:05 | Open the trash icon on "Test Person" → confirm | Delete + cascade |
| 9 | 2:05–2:15 | Terminal: `python -m unittest discover -s tests -t .` → `OK` | 37 tests pass |

## After recording

1. Upload the file, put the link in `docs/blog.md` (table at the top, §1 and §5).
2. Replace the GitHub placeholder in the same table.
3. Take the **commit history screenshot** from GitHub (`Insights → Commits`) and save it as
   `docs/screenshots/07-commit-history.png`; add it to §1 of the blog.
