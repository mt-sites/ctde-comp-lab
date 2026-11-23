#!/usr/bin/env python3
"""
update_schedule.py — reads Pictures/room-plotting.png with Claude (vision) and
regenerates data/room-plotting-data.js, which drives:
  • the Laboratory Schedule grid (index.html)
  • the Occupied Hours + "Reserve a Time Slot" grid (booking.html)

Two ways to read the image:
  --engine local   100% FREE, no account/API key. Uses OpenCV + Tesseract OCR on the
                   room-plotting template layout (colored blocks on a day/hour grid).
  --engine claude  Uses Claude vision (needs ANTHROPIC_API_KEY, pay-as-you-go). More accurate.
  --engine auto    (default) Claude if ANTHROPIC_API_KEY is set, otherwise local.

Runs automatically via .github/workflows/update-schedule.yml whenever the image is replaced.
Can also be run by hand:

    python3 scripts/update_schedule.py                 # read the image, rewrite the data file
    python3 scripts/update_schedule.py --dry-run       # show the result, write nothing
    python3 scripts/update_schedule.py --engine local  # force the free engine
    python3 scripts/update_schedule.py --from-json extracted.json   # skip reading (manual)

Local engine needs:  sudo apt-get install tesseract-ocr  and  pip install opencv-python-headless numpy pytesseract
"""
import argparse, base64, collections, difflib, json, os, re, sys, time, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_PATH = os.path.join(ROOT, "Pictures", "room-plotting.png")
DATA_PATH = os.path.join(ROOT, "data", "room-plotting-data.js")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
API_URL = "https://api.anthropic.com/v1/messages"

SITE_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]   # days the website shows
ALL_DAYS = SITE_DAYS + ["Saturday", "Sunday"]
DEFAULT_LUNCH = ("12:00", "13:00")

PROMPT = """This image is a university ROOM PLOTTING timetable (weekly grid: days across the top, hourly time rows down the left). Extract every scheduled class block.

Return ONLY one JSON object, no prose and no markdown fences, in exactly this shape:
{
  "room": "room/laboratory name printed above the grid",
  "term": "semester and school year printed under the title",
  "effectiveDate": "the 'Effective Date' printed at the bottom (e.g. July 2026), or empty string",
  "classes": [
    {"day": "Monday", "start": "08:00", "end": "10:00", "subject": "...", "section": "...", "instructor": "..."}
  ]
}

Rules:
- One entry per coloured block. Decide start/end from the block's top and bottom edges against the time rows on the left. Use 24-hour "HH:MM" (1:00 PM = "13:00").
- If two stacked blocks have the same text but are separate coloured boxes, keep them as separate entries.
- subject = the top bold line (e.g. "ITLE 4", "PROF EDUC 7 (TECH)"); section = the program/year line (e.g. "BTVTED FP 3A"); instructor = the name line.
- Ignore the dark lunch-break band, empty rows, headers/footers, and any handwritten notes written over blocks.
- Use full English day names (Monday ... Sunday). Do not invent blocks; if text is unreadable, give your best reading.
"""

def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr); sys.exit(1)

def detect_media_type(raw):
    if raw[:8] == b"\x89PNG\r\n\x1a\n": return "image/png"
    if raw[:3] == b"\xff\xd8\xff": return "image/jpeg"
    if raw[:6] in (b"GIF87a", b"GIF89a"): return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP": return "image/webp"
    die("Pictures/room-plotting.png is not a PNG/JPEG/GIF/WEBP image.")

def load_image():
    if not os.path.exists(IMAGE_PATH): die(f"Image not found: {IMAGE_PATH}")
    raw = open(IMAGE_PATH, "rb").read()
    if len(raw) > 4_500_000:                      # API image limit is ~5 MB
        try:
            from PIL import Image; import io
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            img.thumbnail((2400, 2400))
            buf = io.BytesIO(); img.save(buf, "JPEG", quality=88); raw = buf.getvalue()
            print("Image was large — downscaled before sending.")
        except ImportError:
            die("Image is over 4.5 MB. Install Pillow (pip install pillow) or save a smaller image.")
    return base64.b64encode(raw).decode(), detect_media_type(raw)

def call_claude(b64, media_type):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key: die("ANTHROPIC_API_KEY is not set (add it as a GitHub repository secret, or export it locally).")
    body = json.dumps({
        "model": MODEL, "max_tokens": 4000,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": PROMPT}]}],
    }).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    last = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}"
            if e.code not in (429, 500, 502, 503, 529): break
        except Exception as e:
            last = str(e)
        time.sleep(4 * attempt)
    die(f"Claude API request failed: {last}")

def parse_json(text):
    a, b = text.find("{"), text.rfind("}")
    if a == -1 or b == -1: die("Claude's reply did not contain JSON:\n" + text[:500])
    try: return json.loads(text[a:b + 1])
    except json.JSONDecodeError as e: die(f"Could not parse JSON from Claude: {e}\n{text[:500]}")


# =====================================================================
#  FREE LOCAL ENGINE  (OpenCV + Tesseract) — no account, no API key
# =====================================================================
FLAGS = []   # human-review notes collected while reading

# characters OCR often mixes up are collapsed so "BIVTED" == "BTVTED", "GA" == "6A", "38" == "3B" ...
_CANON = str.maketrans({"i": "t", "l": "t", "1": "t", "|": "t", "!": "t", "(": "t", "{": "t", "[": "t", "y": "t",
                        "g": "6", "8": "b", "s": "b", "0": "o", "u": "3", "5": "b"})
def canon(x):
    x = re.sub(r"[.,'`]", "", x.lower())
    return re.sub(r"\s+", " ", x.translate(_CANON)).strip()
def sim(a, b, field="subject"):
    """Spelling similarity that forgives OCR slips but never merges different year/section codes
    (so '3A' and '2A', or 'FP' and 'FSM', stay different)."""
    ca, cb = canon(a), canon(b)
    if ca == cb: return 1.0
    ta, tb = ca.split(), cb.split()
    if not ta or not tb or ta[-1] != tb[-1]: return 0.0          # last token (year+section / initial) must agree
    if abs(len(ca) - len(cb)) <= 1 and (ca.endswith(cb) or cb.endswith(ca)): return 0.95   # first letter dropped/added
    return difflib.SequenceMatcher(None, " ".join(ta[:-1]), " ".join(tb[:-1])).ratio()

def need(field): return 0.85 if field == "instructor" else 0.9

PROGRAM_CODES = ["BTVTED", "BCAED", "BSNED", "BPED", "BECED", "BEED", "BSED", "BSIT", "BSCS", "BSIE", "BSABE"]
def fix_codes(field, v):
    """Cheap, safe corrections for typical OCR slips in codes (G->6, 8->B, 'BIVTED' -> 'BTVTED')."""
    if field == "instructor" or not v: return v
    toks = v.split()
    if re.fullmatch(r"G[A-Z]", toks[-1]): toks[-1] = "6" + toks[-1][1:]
    elif re.fullmatch(r"\d8", toks[-1]): toks[-1] = toks[-1][0] + "B"
    if field == "section":
        for i, t in enumerate(toks):
            for code in PROGRAM_CODES:
                if t != code and len(t) == len(code) and canon(t) == canon(code): toks[i] = code
    return " ".join(toks)

def quality(v, field):
    """Higher = looks more like a real printed value (used to choose between OCR variants)."""
    q = 0
    if v.count("(") != v.count(")"): q -= 2
    if field == "instructor":
        words = v.replace(",", " ").split()
        q -= sum(1 for w in words if not re.fullmatch(r"[A-Z][a-z]*\.?|[A-Z]+\.?|[A-Z][a-z]+-[A-Z][a-z]+", w))
        if "," not in v: q -= 1
    else:
        if re.search(r"[a-z]", v): q -= 2
        if re.search(r"[^A-Z0-9 ()\-&/]", v): q -= 2
    return q

def existing_data():
    """Old classes/meta from the current data file (used as spelling vocabulary)."""
    try:
        txt = open(DATA_PATH, encoding="utf-8").read()
    except FileNotFoundError:
        return {"subject": [], "section": [], "instructor": [], "room": "", "term": "", "effectiveDate": ""}
    v = {k: sorted(set(re.findall(k + r': "((?:[^"\\]|\\.)*)"', txt))) for k in ("subject", "section", "instructor")}
    v = {k: [json.loads('"' + i + '"') for i in L] for k, L in v.items()}
    for k in ("room", "term", "effectiveDate"):
        m = re.search(r'^\s*' + k + r': "((?:[^"\\]|\\.)*)"', txt, re.M)
        v[k] = json.loads('"' + m.group(1) + '"') if m else ""
    return v

def _runs(mask, y0, y1, min_len):
    out, cur = [], None
    for y in range(y0, y1):
        if mask[y] and cur is None: cur = y
        elif not mask[y] and cur is not None:
            if y - cur >= min_len: out.append((cur, y))
            cur = None
    if cur is not None and y1 - cur >= min_len: out.append((cur, y1))
    return out

def _ocr_lines(crop, scale, thr, cv2, np, pytesseract):
    big = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    bw = np.where(big < thr, 0, 255).astype(np.uint8)
    bw = cv2.copyMakeBorder(bw, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    t = pytesseract.image_to_string(bw, config="--psm 6 --oem 1")
    return [re.sub(r"\s+", " ", l).strip() for l in t.split("\n") if l.strip()]

def _pick(cands, vocab, field, label):
    """Choose the best reading of one text line: prefer a candidate matching known spelling."""
    cands = [c for c in cands if c]
    if not cands: FLAGS.append(f"{label}: could not read {field}"); return "?"
    count = collections.Counter(cands)
    best = None
    for c, n in count.items():
        for vv in vocab:
            sc = sim(c, vv, field)
            if best is None or (sc, n) > (best[0], best[1]): best = (sc, n, vv)
    if best and best[0] >= need(field): return best[2]
    top = max(count, key=lambda c: (quality(c, field), count[c]))
    return top

def local_extract():
    try:
        import cv2, numpy as np, pytesseract
    except ImportError:
        die("Local engine needs: pip install opencv-python-headless numpy pytesseract  (and: apt-get install tesseract-ocr)")
    if not os.path.exists(IMAGE_PATH): die(f"Image not found: {IMAGE_PATH}")
    img = cv2.imread(IMAGE_PATH)
    if img is None: die("Could not open the image.")
    H, W = img.shape[:2]
    sc = W / 1280.0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sat = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 1]
    old = existing_data()

    # -- 1. header band (days row) and lunch band = row anchors --
    darkfrac = (gray < 110).mean(axis=1) > 0.5
    bands = _runs(darkfrac, 0, H, 2)
    head = next((b for b in bands if b[1] - b[0] >= 12 * sc), None)
    if not head: die("Could not find the table header (Time / Monday / Tuesday ...). Is this the room plotting template?")
    T = head[1]
    lunch = next((b for b in bands if b[0] > T and b[1] - b[0] >= 20 * sc), None)
    hh0 = 40.2 * sc
    if lunch:
        n = max(1, round((lunch[0] - T) / hh0)); first_hour = 12 - n; hh = (lunch[0] - T) / n
        def hour_at(y):
            return first_hour + (y - T) / hh if y <= (lunch[0] + lunch[1]) / 2 else 13 + (y - lunch[1]) / hh
    else:
        first_hour, hh = 7, hh0
        def hour_at(y): return first_hour + (y - T) / hh
        FLAGS.append("lunch band not found; assumed the grid starts at 7:00 AM")
    y_end = int(min(H - 5, T + 14 * hh))

    # -- 2. day columns from the long vertical grid lines --
    body = (gray[int(T + 10 * sc): int(T + 400 * sc)] < 110).mean(axis=0) > 0.5
    lines = [(a + b) // 2 for a, b in _runs(body, 0, W, 1)]
    if len(lines) < 5: die("Could not detect the day columns of the grid.")
    diffs = [b - a for a, b in zip(lines, lines[1:])]
    cw = sorted(diffs)[len(diffs) // 2]
    while len(lines) > 1 and abs(lines[1] - lines[0] - cw) > 0.15 * cw: lines.pop(0)
    while len(lines) > 1 and abs(lines[-1] - lines[-2] - cw) > 0.15 * cw: lines.pop()
    while len(lines) < 8 and lines[-1] + cw < W: lines.append(lines[-1] + cw)
    lines = lines[:8]
    day_names = ALL_DAYS[:len(lines) - 1]

    # -- 3. blocks: colored runs along each column's text-free margins --
    raw_blocks = []
    for i, day in enumerate(day_names):
        a, b = lines[i], lines[i + 1]
        m = int(5 * sc); w = int(9 * sc)
        cols = list(range(a + m, a + m + w)) + list(range(b - m - w, b - m))
        colored = ((sat[:, cols] > 45) & (gray[:, cols] > 95)).mean(axis=1) > 0.6
        for y0, y1 in _runs(colored, T + 2, y_end, int(10 * sc)):
            s_h = round(hour_at(y0) * 2) / 2; e_h = round(hour_at(y1) * 2) / 2
            if e_h <= s_h: continue
            raw_blocks.append((day, y0, y1, a, b, s_h, e_h))
    if not raw_blocks: die("No colored class blocks were found in the image.")

    # -- 4. OCR every block (several scales/thresholds, then vote) --
    vocab = {k: list(old[k]) for k in ("subject", "section", "instructor")}
    out = []
    for day, y0, y1, a, b, s_h, e_h in raw_blocks:
        label = f"{day} {int(s_h):02d}:{int(s_h % 1 * 60):02d}"
        crop = gray[y0 + 2:y1 - 1, a + 4:b - 4]
        reads = []
        for scale in (3, 4, 5, 6):
            for thr in (70, 85, 100):
                L = _ocr_lines(crop, scale, thr, cv2, np, pytesseract)
                if len(L) >= 3: reads.append(L)
        if not reads:
            FLAGS.append(f"{label}: no readable text — please fill it in manually")
            reads = [["?", "?", "?"]]
        fields = {}
        for k, name in enumerate(("subject", "section", "instructor")):
            fields[name] = fix_codes(name, _pick([r[k] for r in reads if len(r) > k], vocab[name], name, label))
        # a block taller than ~5h probably hides two stacked blocks with the same color
        if e_h - s_h > 5: FLAGS.append(f"{label}: block is {e_h - s_h:g}h long — check it is not two classes")
        fmt = lambda h: f"{int(h):02d}:{int(h % 1 * 60):02d}"
        out.append({"day": day, "start": fmt(s_h), "end": fmt(e_h), **fields})

    # -- 5. make spelling consistent inside this image (cluster look-alike readings, keep the best one) --
    for name in ("subject", "section", "instructor"):
        raws = collections.Counter(c[name] for c in out)
        reps = []                                           # clusters: [representative, members]
        for v in sorted(raws, key=lambda v: (v not in old[name], -quality(v, name), -len(v), -raws[v])):
            for cl in reps:
                if sim(v, cl[0], name) >= need(name):
                    cl[1].append(v); break
            else: reps.append([v, [v]])
        remap = {}
        for rep, members in reps:
            if rep in old[name] or len(members) == 1: best = rep
            else:
                best = max(members, key=lambda m: (quality(m, name), raws[m], len(m)))
                for m in members:      # OCR often drops a first letter ("TLE 4" vs "ITLE 4"): keep the longer
                    if len(m) == len(best) + 1 and canon(m).endswith(canon(best)) and quality(m, name) >= quality(best, name): best = m
            for m in members: remap[m] = best
        for c in out: c[name] = remap[c[name]]

    unverified = collections.OrderedDict()
    for c in out:
        for name in ("subject", "section", "instructor"):
            if c[name] not in old[name] and c[name] != "?":
                unverified.setdefault(f"{name} '{c[name]}'", []).append(f"{c['day'][:3]} {c['start']}")
    for k, where in unverified.items():
        FLAGS.append(f"unverified {k} (e.g. {where[0]}" + (f", +{len(where) - 1} more" if len(where) > 1 else "") + ") — please check the spelling")

    # -- 6. header text: room / term / effective date --
    big = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    txt = pytesseract.image_to_string(big, config="--psm 11 --oem 1")
    def grab(rx):
        m = re.search(rx, txt, re.I | re.M)
        return re.sub(r"\s+", " ", m.group(0)).strip() if m else ""
    meta = {
        "room": grab(r"^.*(laborator|room|building).*\d.*$") or old["room"],
        "term": grab(r"(first|second|summer|mid\w*)\s+sem\w*,?\s+(school\s+year\s+)?\d{4}\s*-\s*\d{4}") or old["term"],
        "effectiveDate": (re.sub(r"(?i)effective date:?\s*", "", grab(r"effective date:?[^\n]*")) or old["effectiveDate"]),
    }
    if not meta["room"]: FLAGS.append("room name not found in the header")
    return {**meta, "classes": out}

def to_min(t): h, m = t.split(":"); return int(h) * 60 + int(m)

def validate(raw):
    classes, warnings = [], []
    for i, c in enumerate(raw.get("classes", []), 1):
        day = str(c.get("day", "")).strip().capitalize()
        s, e = str(c.get("start", "")).strip(), str(c.get("end", "")).strip()
        if day not in ALL_DAYS: die(f"Block #{i}: unknown day '{c.get('day')}'.")
        if not (re.fullmatch(r"\d{2}:\d{2}", s) and re.fullmatch(r"\d{2}:\d{2}", e)): die(f"Block #{i}: bad time '{s}'–'{e}'.")
        if not (6 * 60 <= to_min(s) < to_min(e) <= 21 * 60): die(f"Block #{i} ({day} {s}-{e}): time range looks wrong.")
        if day not in SITE_DAYS:
            warnings.append(f"{day} {s}-{e} ignored (website only shows Mon–Fri)."); continue
        classes.append({"day": day, "start": s, "end": e,
                        "subject": str(c.get("subject", "")).strip(),
                        "section": str(c.get("section", "")).strip(),
                        "instructor": str(c.get("instructor", "")).strip()})
    if not classes: die("No classes were found in the image — the data file was NOT changed.")
    classes.sort(key=lambda c: (SITE_DAYS.index(c["day"]), c["start"]))
    for a, b in zip(classes, classes[1:]):                       # overlap check
        if a["day"] == b["day"] and to_min(b["start"]) < to_min(a["end"]):
            die(f"Overlapping blocks on {a['day']}: {a['start']}-{a['end']} and {b['start']}-{b['end']}. Data file NOT changed.")
    if any(to_min(c["start"]) < 8 * 60 or to_min(c["end"]) > 17 * 60 for c in classes):
        warnings.append("Some classes fall outside 8:00 AM–5:00 PM. The schedule grid will extend, but the booking grid only has the hours listed in HOURS in js/booking.js (they must match your Google Form).")
    return classes, warnings

def existing_lunch():
    try:
        m = re.search(r'lunch:\s*\{\s*start:\s*"(\d\d:\d\d)"\s*,\s*end:\s*"(\d\d:\d\d)"', open(DATA_PATH, encoding="utf-8").read())
        if m: return m.group(1), m.group(2)
    except FileNotFoundError: pass
    return DEFAULT_LUNCH

def js(s): return json.dumps(s, ensure_ascii=False)

def write_data(raw, classes, lunch):
    lines = []
    for i, c in enumerate(classes):
        prev = classes[i - 1]["day"] if i else None
        if c["day"] != prev:
            if i: lines.append("")
            lines.append(f"    // ---- {c['day']} ----")
        comma = "," if i < len(classes) - 1 else ""
        lines.append(f'    {{ day: {js(c["day"])}, start: {js(c["start"])}, end: {js(c["end"])}, subject: {js(c["subject"])}, section: {js(c["section"])}, instructor: {js(c["instructor"])} }}{comma}')
    out = f'''/* =====================================================================
   ROOM PLOTTING DATA  —  AUTO-GENERATED by scripts/update_schedule.py
   ---------------------------------------------------------------------
   Read from Pictures/room-plotting.png. This file is rewritten automatically
   (GitHub Action) whenever that image is replaced, and drives:
     - Laboratory Schedule grid (index.html)
     - Occupied Hours + Reserve a Time Slot grid (booking.html)
   You can still edit it by hand, but the next image upload will overwrite it.
   Times use 24-hour format: "13:00" = 1:00 PM.
========================================================================*/
window.ROOM_PLOTTING = {{
  image: "Pictures/room-plotting.png",
  room: {js(raw.get("room") or "Laboratory")},
  term: {js(raw.get("term") or "")},
  effectiveDate: {js(raw.get("effectiveDate") or "")},

  // Daily lunch break: no class AND not bookable (shown as "Lunch break")
  lunch: {{ start: {js(lunch[0])}, end: {js(lunch[1])} }},

  classes: [
{chr(10).join(lines)}
  ]
}};
'''
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    open(DATA_PATH, "w", encoding="utf-8", newline="\n").write(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the result, do not write the data file")
    ap.add_argument("--from-json", help="use an already-extracted JSON file instead of reading the image")
    ap.add_argument("--engine", choices=["auto", "local", "claude"], default="auto",
                    help="local = free OCR (default if no API key); claude = Claude vision (needs ANTHROPIC_API_KEY)")
    a = ap.parse_args()
    engine = a.engine if a.engine != "auto" else ("claude" if os.environ.get("ANTHROPIC_API_KEY") else "local")

    if a.from_json: raw = json.load(open(a.from_json, encoding="utf-8"))
    elif engine == "claude":
        b64, mt = load_image()
        print(f"Reading {os.path.relpath(IMAGE_PATH, ROOT)} with Claude ({MODEL}) …")
        raw = parse_json(call_claude(b64, mt))
    else:
        print(f"Reading {os.path.relpath(IMAGE_PATH, ROOT)} with the free local OCR engine …")
        raw = local_extract()

    classes, warnings = validate(raw)
    for w in warnings + ["REVIEW: " + f for f in FLAGS]: print("WARNING:", w)
    print(f"Found {len(classes)} class blocks — {raw.get('room', '')} | {raw.get('term', '')}")
    for c in classes: print(f"  {c['day'][:3]} {c['start']}-{c['end']}  {c['subject']} / {c['section']} / {c['instructor']}")
    if a.dry_run: print("Dry run — nothing written."); return
    write_data(raw, classes, existing_lunch())
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write(f"### Schedule updated ({len(classes)} class blocks)\n\n")
            f.write("| Day | Time | Subject | Section | Instructor |\n|---|---|---|---|---|\n")
            for c in classes: f.write(f"| {c['day']} | {c['start']}-{c['end']} | {c['subject']} | {c['section']} | {c['instructor']} |\n")
            if warnings or FLAGS: f.write("\n**Please review:**\n" + "".join(f"- {w}\n" for w in warnings + FLAGS))
    print(f"Wrote {os.path.relpath(DATA_PATH, ROOT)}")

if __name__ == "__main__":
    main()
