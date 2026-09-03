# Medicine Search Feature

## Overview
The medicine search feature allows you to search across multiple medicine lists to find specific medicines with their discounts from different shops.

## Features

### 1. Multi-file Upload
- Upload multiple medicine list files at once (HTML, TXT, PDF)
- Files are stored in sessions and can be accumulated (upload more files without losing previous ones)

### 2. Improved Search Algorithm
- **Fixed issue**: Prevents partial matches like "500" from matching "650"
- Smart matching that considers medicine names as complete phrases
- Supports both exact and partial matches

### 3. Shop/Company Name Extraction
- Automatically extracts company/shop names from:
  - HTML title tags
  - Headers in text files
  - First pages of PDF files
- Shows which shop carries each medicine in search results

### 4. Multi-format Support
- HTML files (from .htm/.html)
- Text files (from .txt/.text)
- PDF files (from .pdf)

### 5. Batch Search
- Search for multiple medicines at once by separating with commas
- Results show all matches grouped by search term

## How to Use

### Web Interface (Recommended)
1. Start the application: `python3 app.py`
2. Go to `http://localhost:5001/search`
3. Upload medicine list files using the upload button
4. Enter medicine names (comma separated) to search
5. View results with shop names and discount rates

### Manual Testing
You can place your medicine list files in the `medicine_lists` folder and then test the search functionality.

## Technical Details

The search functionality is implemented in:
- `search_medicines.py`: Core search algorithm
- `app.py`: Flask routes and file handling
- `templates/search.html`: Frontend interface

The search algorithm includes:
- Format-specific parsing for HTML, TXT, and PDF files
- Company/shop name extraction from file headers
- Improved word-based matching to prevent incorrect number matches
- Session-based file storage that appends (doesn't replace) files 

## Other Features & Documentation

The app also includes these pages:

| Page | URL | Purpose |
|------|-----|---------|
| Home | `/` | Upload/process medicine lists |
| Make HTML | `/make_html` | Generate HTML offer lists from processed data |
| **Deduplicate** | `/deduplicate` | Remove duplicate list entries, keeping the highest discount |
| Search | `/search` | Search medicines across uploaded lists |
| Compare (Diff) | `/diff` | Compare two lists (added / deleted / changed) |

Full documentation for the deduplication feature is available here:

- **📄 [DEDUPLICATION.md](DEDUPLICATION.md)** — consolidated guide (overview, usage, fuzzy matching, exports, troubleshooting)

