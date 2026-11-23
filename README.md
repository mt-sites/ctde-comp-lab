# CTDE Computer Laboratory Website

Un-official website for the Computer Laboratory of the **College of Technological and Developmental Education (CTDE)**.

A static, no-backend website providing lab information, resources, and a time-slot reservation system for students.

---

## 🌐 Live Site

Published via GitHub Pages: `https://mtlaynesa.github.io/ctde-comp-lab/index.html`

---

## 📄 Pages

| File | Description |
|---|---|
| `index.html` | Home page — facilities overview, lab photo gallery, resources (PDF manual), software list, weekly class schedule, and laboratory rules. |
| `contact.html` | Contact page — Laboratory In-Charge and Technician profiles, photos, Google Certified Educator badges, office details. |
| `booking.html` | Lab reservation system — students pick a date, see hourly availability, and are routed to a Google Form to reserve an open slot. |
| `forms.html` | Downloadable forms library (equipment borrowing, incident report, lab usage request, software installation request). |

---

## 📁 Project Structure

HTML, CSS, and JavaScript are kept in separate files rather than inline, so each can be edited independently:

```
/
├── index.html
├── contact.html
├── booking.html
├── forms.html
├── README.md
├── css/
│   ├── style.css      # Shared: header/nav, hero, section titles, cards, footer, responsive base
│   ├── index.css       # Home page only: facilities cards, photo gallery, lightbox, schedule table
│   ├── contact.css     # Contact page only: profile cards, photo/badge holders
│   ├── booking.css     # Booking page only: availability grid, legend, date picker
│   └── forms.css       # Forms page only: form cards, download buttons
├── js/
│   ├── schedule.js     # Home page: builds the schedule grid + full-screen room plotting viewer
│   ├── security.js     # Shared: right-click/DevTools shortcut deterrent (used on all 4 pages)
│   └── booking.js      # Booking page only: all reservation logic and configuration
├── Pictures/
│   ├── CSPC-Seal.png
│   ├── CTDE 1.JPG
│   ├── CTDE 2.JPG
│   ├── CTDE 3.JPG
│   ├── CTDE 4.JPG
│   ├── Romeo-Sotto.jpg
│   ├── Matt-Glenn-Laynesa.jpg
│   ├── Google-Cert-1.png
│   └── Google-Cert-2.png
└── PDF/
    └── CSPC ICT Laboratory Manual.pdf
```

Every HTML file only contains markup — styling is pulled in via `<link rel="stylesheet">` and behavior via `<script src="...">`. Each page loads `css/style.css` (shared) plus its own page-specific stylesheet.

---

## ⚙️ Configuring the Reservation System (`js/booking.js`)

The booking page has no backend of its own — it reads live reservation counts from a Google Form's linked response Spreadsheet. All settings live at the top of **`js/booking.js`** (not inside `booking.html` anymore).

| Setting | What it does |
|---|---|
| `GOOGLE_FORM_URL` | Link to the reservation Google Form (the public "fill out this form" link). |
| `SHEET_ID` | The ID of the Form's linked response Google Sheet (from its URL). |
| `SHEET_TAB_NAME` | The response tab name, usually `"Form Responses 1"`. |
| `TIME_COLUMN` | Must exactly match the Form's Time question title (e.g. `"Time Options"`). |
| `DATE_COLUMN` | Must exactly match the Form's Date question title (e.g. `"Reservation Date"`). |
| `OCCUPIED_RANGES` | Recurring weekly class hours that block out the lab, written as plain ranges (e.g. `"1:00 PM to 4:00 PM"`). |
| `SLOT_LIMIT` | Max reservations allowed per hour, per specific date (default `20`). |
| `FORM_TIME_ENTRY` / `FORM_DATE_ENTRY_BASE` | Optional — pre-fills the Time/Date fields when a student clicks a slot, from the Form's "Get pre-filled link" entry IDs. |

### Requirements on the Google Form/Sheet side
- The response Sheet must be shared as **Anyone with the link → Viewer** (read-only) so the page can fetch counts.
- The Form should be restricted to your institution's Google accounts (Settings → Responses → "Restrict to users in [domain]") to prevent outside spam.
- **Choice Eliminator 2** (Form add-on) is recommended as the actual hard cap enforcement — the live counter on the page is a convenience display, not a guaranteed limit on its own.

---

## 📝 Adding a Downloadable Form (`forms.html`)

1. Create a `Forms/` folder next to the HTML files and drop your PDF/DOCX files in it.
2. In `forms.html`, copy one `.form-card` block and update its icon, title, description, and the `href` in the Download link to match your filename.

---

## 🔒 Security Notes

- Only collaborators added under **Settings → Collaborators** can push changes — enable **2FA** on all contributor accounts.
- No API keys or secrets are used anywhere in this site — everything client-side is inherently public/viewable, by design of how browsers work.
- The reservation system's real integrity relies on the Google Form's domain restriction and the Sheet's Viewer-only sharing — not on anything in the HTML/JS.
- `js/security.js` only discourages casual right-click/DevTools use — it is not real protection (view source is always possible on any published website).

---

## 👤 Maintained By

- **Computer Laboratory Technician:** Matt Glenn L. Laynesa, LPT

---

## 📜 License

For educational use only. Not licensed for external redistribution.

---

## 🗓️ Auto-updating the Schedule from the Room Plotting image

The Laboratory Schedule (`index.html`), Occupied Hours and Reserve a Time Slot (`booking.html`) are all generated from **`data/room-plotting-data.js`**, which is **rewritten automatically** from `Pictures/room-plotting.png`.

**Free setup: nothing to configure.** Just keep the repository on GitHub.

**To update the schedule**
1. Upload/replace `Pictures/room-plotting.png` (same filename) in the repository.
2. The *Update schedule from room plotting image* workflow (Actions tab) runs by itself, reads the image with free OCR (Tesseract), and commits a new `data/room-plotting-data.js`.
3. Open the finished run → **Summary** to see the list of classes it found and any **"please review"** notes. Fix any wrong text directly in `data/room-plotting-data.js` (your fixes are remembered as the spelling reference for the next upload).

**How accurate is it?** Day/time blocks are detected from the colored cells and are very reliable. The printed text (subject, section, instructor) is read with OCR and can have small slips, especially for new names; those are listed in the run summary. Spellings already in `data/room-plotting-data.js` are used to auto-correct future readings.

**Optional, more accurate:** add a repository secret named `ANTHROPIC_API_KEY` and the same workflow will read the image with Claude instead (pay-as-you-go).

**Run it by hand** (optional): `python3 scripts/update_schedule.py` (add `--dry-run` to preview, `--engine local` or `--engine claude` to choose). The free engine needs `tesseract-ocr` plus `pip install opencv-python-headless numpy pytesseract`.

**Limits:** it expects the CSPC room plotting template (hour rows with Monday–Sunday columns and the dark lunch band). Only Monday–Friday is shown on the site. The booking grid uses the hours in `HOURS` (`js/booking.js`), which must match your Google Form choices, so classes outside 8 AM–5 PM show on the schedule but not in booking. The daily lunch break (`lunch`) is kept when the file is regenerated.

Clicking the room plotting image on the home page opens it full screen with zoom.
