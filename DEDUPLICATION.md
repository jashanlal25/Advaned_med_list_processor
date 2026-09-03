# 🎉 Deduplication Feature — Complete Guide

A consolidated reference covering the **Deduplicate** feature: overview, how it works, fuzzy matching, usage, navigation, technical details, and troubleshooting.

**Status:** ✅ Production Ready · **Access:** `/deduplicate` (or click 📋 Deduplicate in the header)

---

## 1. Overview

The Deduplicate feature cleans up medicine lists by removing duplicate item entries while keeping the entry with the **highest discount percentage**. It runs inside the Flask app (`app.py`) and the page is `templates/deduplicate.html`.

It combines three earlier documents into one:

- Feature implementation & deliverables
- Enhanced implementation & workflow
- Fuzzy-matching update & removed-items recovery
- Complete user guide
- Navigation header update

---

## 2. What It Delivers

### Backend (`app.py`)
| Item | Purpose |
|------|---------|
| `GET /deduplicate` | Renders the deduplication page |
| `POST /deduplicate-upload` | Processes pasted text / uploaded file and returns results |
| `deduplicate_items()` | Core logic — keeps highest discount, returns kept + removed + stats |
| `normalize_name()` | Normalizes names (units, abbreviations, punctuation) for matching |
| `quick_match()` / similarity | Fuzzy similarity scoring for similar/variant names |
| `clean_removed_line()` | Normalizes spacing in removed lines for clean output |

### Frontend (`templates/deduplicate.html`)
- **Input tabs:** 📝 Paste Text · 📁 Upload File (drag & drop)
- **Statistics dashboard:** Original / Unique / Removed counts
- **Result tabs:**
  - ✓ **Deduplicated Data** — cleaned list
  - ✗ **Removed Items** — visual comparison of variants (kept = green, removed = red)
  - 📋 **Removed List (Copy)** — removed items in the same input format for easy recovery
- **Export:** 📋 Copy to clipboard · ⬇ Download `.txt` · ⬇ Download `.md` (with stats)
- **UI:** full site navigation, dark/light theme toggle, mobile hamburger menu, active-page indicator

---

## 3. Input / Output Format

```
ItemName----- discount%
Zolrest 600 Tab----- 27.00%
Aspirin 100mg----- 10%
Paracetamol----- 5.50%
```

**Output** keeps only the highest-discount entry per item, in the same format. Supported files: `.txt`, `.text`, `.md`.

---

## 4. How the Logic Works

1. Parse each line → extract **item name** and **discount %**.
2. **Normalize** names (strip punctuation, standardize units/abbreviations: `Tab.`→`tablet`, `625mg`→`625`, `Syp`→`syrup`).
3. **Group similar names** using fuzzy similarity (Levenshtein / token match, ~80% threshold).
4. Keep the entry with the **highest discount** per group; collect all others as "removed".
5. Return kept text, removed text, and statistics.

### Fuzzy matching catches (no user action needed)
| Case | Example |
|------|---------|
| Typos | `Alvostan` vs `Alvoston` |
| Abbreviations | `Claritek 125 Syp` vs `Claritek 125 Syr` |
| Spacing/shortening | `Beasy Sach` vs `Beasy Sachet` |
| Punctuation | `Artimov K` vs `Artimov-K` |
| Variant words | Names with `New`, `Platinum`, etc. |
| Brand/vendor names | `(Bosch)`, `(Sami)`, `(Hilton)` removed for comparison |

### Worked example
```
Input:
Zolrest 600----- 27.00%      → KEPT  (highest)
Zolrest 600----- 25.00%      → REMOVED
Aspirin 100mg----- 10.00%    → REMOVED
Aspirin 100mg----- 15.00%    → KEPT  (highest)
```

---

## 5. How to Use It

**Method 1 — Paste text**
1. Go to `/deduplicate` → 📝 **Paste Text** tab.
2. Paste your list into the textarea.
3. Click **▶ Run Deduplication**.
4. View results instantly.

**Method 2 — Upload a file**
1. Go to `/deduplicate` → 📁 **Upload File** tab.
2. Drag & drop (or browse) a `.txt`/`.md` file.
3. It processes automatically and shows results.

**Export / continue workflow**
```
1. Paste or upload list
2. Run Deduplication
3. Copy the deduplicated data (📋 Copy Text)
4. Go to Make HTML page and paste
5. Generate HTML — no file round-trips needed
```

**Recovery workflow** — if you accidentally removed an item:
```
1. Open 📋 Removed List (Copy) tab
2. Copy the removed item(s)
3. Paste back into 📝 Paste Text
4. Run again / adjust as needed
```

---

## 6. Navigation & Header

The page uses the shared site header (`navbar_component.html`), consistent across all pages:

- **Desktop (769px+):** full horizontal navigation with 💊 MediList Pro logo, page links, and theme toggle.
- **Mobile (0–768px):** hamburger menu that auto-closes on navigation; theme toggle visible.

| Page | Icon | URL |
|------|------|-----|
| Home | 🏠 | `/` |
| Make HTML | ✨ | `/make_html` |
| Deduplicate | 📋 | `/deduplicate` |
| Search | 🔍 | `/search` |
| Compare | 📊 | `/diff` |

The header's JS (`toggleTheme`, `toggleMobileMenu`, active-link highlighting) is provided by the shared component, so the deduplicate page no longer needs its own copy.

---

## 7. Statistics Panel

After running, three metrics appear:

- **Original** — total items before deduplication
- **Unique** — items after removing duplicates
- **Removed** — number of duplicates deleted

Example: `100 original → 85 unique (15 removed)`.

---

## 8. Performance, Security & Privacy

- **Speed:** instant (<100 ms for 1000+ items)
- **Upload size:** up to 16 MB
- **File storage:** temporary, **5-minute expiration**
- **Downloads:** token-based, unguessable URLs
- **No persistent file storage**
- **Encoding:** UTF-8 + Latin-1 support
- **Filenames:** secured via `secure_filename` (prevents directory traversal)
- **Input validation:** file type checking

---

## 9. Responsive & UI Notes

- Works on desktop, tablet, and mobile.
- Touch-friendly buttons and spacing.
- Design matches site branding (gradient `667eea → 764ba2`).
- Smooth hover/transition effects.
- Mobile menu auto-closes when a link is clicked.

---

## 10. Troubleshooting

| Problem | Solution |
|---------|----------|
| "No valid items found" | Check format is `Name----- discount%` |
| Copy button not working | Check browser clipboard permissions / use manual select-copy |
| File won't upload | Use `.txt`, `.text`, or `.md` format |
| Results not showing | Refresh the page and try again |
| Item accidentally removed | Copy it back from the 📋 Removed List (Copy) tab |

---

## 11. Files & Where Things Live

```
/mnt/e/list_website/
├── app.py                     → /deduplicate, /deduplicate-upload, deduplicate_items(),
│                                 normalize_name(), quick_match(), clean_removed_line()
├── templates/
│   ├── deduplicate.html       → Deduplicate UI (uses navbar_component.html)
│   └── navbar_component.html  → Shared header (all pages)
└── (this file) DEDUPLICATION.md → consolidated documentation
```

---

## 12. Use Cases

1. Clean medicine lists (remove duplicate entries).
2. Prepare data before making HTML files.
3. Verify which discount version was kept.
4. Data-quality control.
5. Workflow optimization (paste directly between Deduplicate → Make HTML).

---

## 13. Optional Future Enhancements

1. Option to keep the **lowest** discount instead.
2. Export statistics to CSV/PDF.
3. Batch processing of multiple files.
4. Advanced filtering options.
5. Side-by-side before/after comparison.
6. History / auto-save of recent results.
7. Share results via link.

---

## 14. Quick Summary

| Item | Status |
|------|--------|
| Implementation | ✅ Complete |
| Fuzzy matching | ✅ Complete |
| Removed-items recovery | ✅ Complete |
| Full navigation header | ✅ Complete |
| Testing | ✅ All passing |
| Ready for use | ✅ Yes |

**Visit:** `/deduplicate` 🚀
