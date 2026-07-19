# Optional scored lexicon

XWGen prefers `spreadthewordlist.txt` in this directory when it is installed.
The downloaded dataset is intentionally ignored by Git and is not distributed
with this repository.

Install it from the repository root:

```powershell
.venv\Scripts\python.exe scripts\install_spread_wordlist.py
```

Spread the Word(list) is maintained at
<https://www.spreadthewordlist.com/> and licensed under
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
It may be used in a free product with attribution, but its noncommercial terms
must be reconsidered before using XWGen or a derivative commercially.

If the file is absent, XWGen falls back to the bundled, unscored 2021 Crossword
Nexus list.
