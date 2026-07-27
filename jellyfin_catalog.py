#!/usr/bin/env python3
"""
jellyfin_catalog.py — Generate a single-file HTML catalog of your Jellyfin movie
library that you can send to anyone. No server access required to view it.

The page shows every movie as a poster card in a grid, with search, genre filter,
and sorting. The viewer taps posters to add them to a "pull list", then exports
that list as a text file (or copies it to the clipboard) to send back to you.

Usage:
    pip install requests --break-system-packages   # if requests isn't installed
    python3 jellyfin_catalog.py \
        --url http://192.168.68.136:8096 \
        --api-key YOUR_API_KEY \
        --output my_movies.html

Get an API key in Jellyfin: Dashboard -> API Keys -> +

Optional flags:
    --poster-width 240     Poster thumbnail width in px (default 240)
    --quality 80           JPEG quality 1-100 (default 80)
    --workers 8            Parallel poster downloads (default 8)
    --library "Movies"     Only include items from a library whose name matches
"""

import argparse
import base64
import concurrent.futures
import html
import json
import sys

try:
    import requests
except ImportError:
    sys.exit("The 'requests' package is required: pip install requests --break-system-packages")


def get_json(session, base_url, path, params=None):
    r = session.get(f"{base_url}{path}", params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_movies(session, base_url, library_name=None):
    params = {
        "IncludeItemTypes": "Movie",
        "Recursive": "true",
        "Fields": "Genres,ProductionYear,Overview,RunTimeTicks,CommunityRating,OfficialRating,DateCreated",
        "SortBy": "SortName",
        "SortOrder": "Ascending",
    }
    if library_name:
        # Resolve the library (view) id by name
        views = get_json(session, base_url, "/Library/MediaFolders")
        match = next(
            (v for v in views.get("Items", []) if v.get("Name", "").lower() == library_name.lower()),
            None,
        )
        if not match:
            names = ", ".join(v.get("Name", "?") for v in views.get("Items", []))
            sys.exit(f"Library '{library_name}' not found. Available: {names}")
        params["ParentId"] = match["Id"]

    data = get_json(session, base_url, "/Items", params)
    return data.get("Items", [])


def fetch_poster_b64(session, base_url, item_id, width, quality):
    try:
        r = session.get(
            f"{base_url}/Items/{item_id}/Images/Primary",
            params={"fillWidth": width, "quality": quality, "format": "Jpg"},
            timeout=30,
        )
        if r.status_code == 200 and r.content:
            return base64.b64encode(r.content).decode("ascii")
    except requests.RequestException:
        pass
    return None


def ticks_to_minutes(ticks):
    if not ticks:
        return None
    return round(ticks / 10_000_000 / 60)


def build_records(session, base_url, items, width, quality, workers, posters_dir=None):
    """If posters_dir is None, embed posters as base64 ('p'). Otherwise write
    posters/NNNN.jpg files and store a relative URL ('u')."""
    total = len(items)

    def work(idx_item):
        idx, item = idx_item
        poster = fetch_poster_b64(session, base_url, item["Id"], width, quality)
        rec = {
            "t": item.get("Name", "Untitled"),
            "y": item.get("ProductionYear"),
            "g": item.get("Genres", [])[:4],
            "o": (item.get("Overview") or "")[:400],
            "m": ticks_to_minutes(item.get("RunTimeTicks")),
            "r": item.get("CommunityRating"),
            "c": item.get("OfficialRating"),
            "d": item.get("DateCreated"),
        }
        if poster and posters_dir is not None:
            fname = f"{idx:05d}.jpg"
            with open(posters_dir / fname, "wb") as f:
                f.write(base64.b64decode(poster))
            rec["u"] = f"posters/{fname}"
        elif poster:
            rec["p"] = poster
        done = idx + 1
        if done % 25 == 0 or done == total:
            print(f"  posters: {done}/{total}", flush=True)
        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        records = list(ex.map(work, enumerate(items)))
    return records


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #101418;
    --panel: #1a2027;
    --ink: #e8ecef;
    --muted: #8b98a5;
    --line: #2a333d;
    --pick: #e9b44c;          /* selection accent: marquee amber */
    --pick-ink: #191204;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  header {
    position: sticky; top: 0; z-index: 5; background: var(--bg);
    border-bottom: 1px solid var(--line); padding: 14px 18px;
    display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  }
  header h1 { font-size: 17px; margin: 0 12px 0 0; letter-spacing: .02em; font-weight: 600; }
  header h1 small { color: var(--muted); font-weight: 400; margin-left: 8px; }
  input[type="search"], select {
    background: var(--panel); color: var(--ink); border: 1px solid var(--line);
    border-radius: 8px; padding: 8px 12px; font-size: 14px; outline: none;
  }
  input[type="search"] { flex: 1 1 220px; min-width: 160px; }
  input[type="search"]:focus, select:focus { border-color: var(--pick); }
  .grid {
    display: grid; gap: 16px; padding: 18px;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    padding-bottom: 110px;
  }
  .card {
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    overflow: hidden; cursor: pointer; position: relative;
    transition: transform .12s ease, border-color .12s ease;
  }
  .card:hover { transform: translateY(-2px); }
  .card:focus-visible { outline: 2px solid var(--pick); outline-offset: 2px; }
  .card img, .card .noart {
    display: block; width: 100%; aspect-ratio: 2/3; object-fit: cover; background: #0c1013;
  }
  .card .noart {
    display: flex; align-items: center; justify-content: center; text-align: center;
    color: var(--muted); font-size: 13px; padding: 10px;
  }
  .meta { padding: 8px 10px 10px; }
  .meta .title { font-size: 13.5px; font-weight: 600; line-height: 1.25; }
  .meta .sub { color: var(--muted); font-size: 12px; margin-top: 3px; }
  .card .tick {
    position: absolute; top: 8px; right: 8px; width: 26px; height: 26px;
    border-radius: 50%; background: rgba(10,12,14,.72); border: 1.5px solid var(--muted);
    display: flex; align-items: center; justify-content: center;
    color: transparent; font-size: 15px; font-weight: 700;
  }
  .card.picked { border-color: var(--pick); }
  .card.picked .tick { background: var(--pick); border-color: var(--pick); color: var(--pick-ink); }
  .card.picked::after {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    box-shadow: inset 0 0 0 2px var(--pick); border-radius: 10px;
  }
  /* pull-list tray */
  .tray {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 6;
    background: var(--panel); border-top: 1px solid var(--line);
    padding: 12px 18px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
  }
  .tray .count { font-weight: 600; }
  .tray .count b { color: var(--pick); }
  .tray button {
    background: var(--pick); color: var(--pick-ink); border: 0; border-radius: 8px;
    padding: 9px 14px; font-size: 14px; font-weight: 600; cursor: pointer;
  }
  .tray button.ghost { background: transparent; color: var(--muted); border: 1px solid var(--line); }
  .tray button:disabled { opacity: .45; cursor: default; }
  .tray .note { color: var(--muted); font-size: 12.5px; margin-left: auto; }
  .tray input[type="text"] {
    background: var(--bg); color: var(--ink); border: 1px solid var(--line);
    border-radius: 8px; padding: 8px 10px; font-size: 13px; width: 170px;
  }
  .empty { color: var(--muted); padding: 40px 18px; text-align: center; }
  dialog {
    background: var(--panel); color: var(--ink); border: 1px solid var(--line);
    border-radius: 12px; max-width: 560px; width: calc(100% - 40px); padding: 18px;
  }
  dialog::backdrop { background: rgba(0,0,0,.6); }
  dialog h2 { margin: 0 0 6px; font-size: 16px; }
  dialog p { color: var(--muted); margin: 4px 0 10px; }
  dialog img { float: left; width: 90px; border-radius: 6px; margin: 0 12px 8px 0; }
  dialog .close { float: right; background: none; border: 0; color: var(--muted); font-size: 20px; cursor: pointer; }
  @media (prefers-reduced-motion: reduce) { .card { transition: none; } }
</style>
</head>
<body>
<header>
  <h1>__TITLE__<small id="shown"></small></h1>
  <input type="search" id="q" placeholder="Search titles&hellip;" aria-label="Search titles">
  <select id="genre" aria-label="Filter by genre"><option value="">All genres</option></select>
  <select id="sort" aria-label="Sort">
    <option value="title">Title A–Z</option>
    <option value="added-desc">Recently added</option>
    <option value="year-desc">Release year (newest)</option>
    <option value="year-asc">Release year (oldest)</option>
    <option value="rating">Highest rated</option>
  </select>
</header>

<div class="grid" id="grid"></div>
<div class="empty" id="empty" hidden>Nothing matches that search.</div>

<div class="tray">
  <span class="count"><b id="n">0</b> on your pull list</span>
  <input type="text" id="who" placeholder="Your name (optional)" aria-label="Your name" hidden>
  <button id="export" disabled>Download list (.txt)</button>
  <button id="copy" class="ghost" disabled>Copy to clipboard</button>
  <button id="clear" class="ghost" disabled>Clear</button>
  <span class="note">Tap a poster to add it &middot; tap the title area for details &middot; picks are saved in this browser</span>
</div>

<dialog id="dlg">
  <button class="close" aria-label="Close">&times;</button>
  <div id="dlgBody"></div>
</dialog>

<script>
const MOVIES = __DATA__;
const LS_KEY = "jf-pulllist-__STAMP__";

const grid = document.getElementById("grid");
const q = document.getElementById("q");
const genreSel = document.getElementById("genre");
const sortSel = document.getElementById("sort");
const shown = document.getElementById("shown");
const emptyMsg = document.getElementById("empty");
const nEl = document.getElementById("n");
const btnExport = document.getElementById("export");
const btnCopy = document.getElementById("copy");
const btnClear = document.getElementById("clear");
const dlg = document.getElementById("dlg");
const dlgBody = document.getElementById("dlgBody");

let picked = new Set();
try { picked = new Set(JSON.parse(localStorage.getItem(LS_KEY) || "[]")); } catch (e) {}

function key(m) { return m.t + " (" + (m.y || "?") + ")"; }
function savePicks() {
  try { localStorage.setItem(LS_KEY, JSON.stringify([...picked])); } catch (e) {}
  const n = picked.size;
  nEl.textContent = n;
  btnExport.disabled = btnCopy.disabled = btnClear.disabled = n === 0;
}

// genres dropdown
const genres = [...new Set(MOVIES.flatMap(m => m.g || []))].sort();
for (const g of genres) {
  const o = document.createElement("option");
  o.value = o.textContent = g;
  genreSel.appendChild(o);
}

function currentList() {
  const term = q.value.trim().toLowerCase();
  const gen = genreSel.value;
  let list = MOVIES.filter(m =>
    (!term || m.t.toLowerCase().includes(term)) &&
    (!gen || (m.g || []).includes(gen))
  );
  const s = sortSel.value;
  if (s === "title") list.sort((a, b) => a.t.localeCompare(b.t));
  if (s === "added-desc") list.sort((a, b) => (b.d || "").localeCompare(a.d || ""));
  if (s === "year-desc") list.sort((a, b) => (b.y || 0) - (a.y || 0));
  if (s === "year-asc") list.sort((a, b) => (a.y || 9999) - (b.y || 9999));
  if (s === "rating") list.sort((a, b) => (b.r || 0) - (a.r || 0));
  return list;
}

function artSrc(m) {
  if (m.u) return m.u;
  if (m.p) return "data:image/jpeg;base64," + m.p;
  return null;
}

function render() {
  const list = currentList();
  grid.innerHTML = "";
  emptyMsg.hidden = list.length > 0;
  shown.textContent = list.length + " of " + MOVIES.length + " movies";
  const frag = document.createDocumentFragment();
  for (const m of list) {
    const card = document.createElement("div");
    card.className = "card" + (picked.has(key(m)) ? " picked" : "");
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-pressed", picked.has(key(m)));

    const src = artSrc(m);
    const art = src
      ? '<img loading="lazy" alt="" src="' + src + '">'
      : '<div class="noart">' + escapeHtml(m.t) + "</div>";
    const sub = [m.y, m.m ? m.m + " min" : null, m.r ? "★ " + m.r.toFixed(1) : null]
      .filter(Boolean).join(" · ");
    card.innerHTML = art +
      '<div class="tick">✓</div>' +
      '<div class="meta"><div class="title">' + escapeHtml(m.t) + '</div>' +
      '<div class="sub">' + escapeHtml(sub) + "</div></div>";

    card.addEventListener("click", (ev) => {
      if (ev.target.closest(".meta")) { openDetails(m); return; }
      togglePick(m, card);
    });
    card.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); togglePick(m, card); }
    });
    frag.appendChild(card);
  }
  grid.appendChild(frag);
}

function togglePick(m, card) {
  const k = key(m);
  if (picked.has(k)) picked.delete(k); else picked.add(k);
  card.classList.toggle("picked", picked.has(k));
  card.setAttribute("aria-pressed", picked.has(k));
  savePicks();
}

function openDetails(m) {
  const src = artSrc(m);
  const art = src ? '<img alt="" src="' + src + '">' : "";
  const bits = [m.y, m.m ? m.m + " min" : null, m.c, m.r ? "★ " + m.r.toFixed(1) : null,
                (m.g || []).join(", ")].filter(Boolean).join(" · ");
  dlgBody.innerHTML = art + "<h2>" + escapeHtml(m.t) + "</h2><p>" + escapeHtml(bits) +
    "</p><p>" + escapeHtml(m.o || "No description.") + "</p>";
  dlg.showModal();
}
dlg.querySelector(".close").addEventListener("click", () => dlg.close());
dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });

const WEBHOOK = "__WEBHOOK__";
const whoInput = document.getElementById("who");
if (WEBHOOK) {
  btnExport.textContent = "Send list to Discord";
  whoInput.hidden = false;
}

function listText() {
  const who = whoInput.value.trim();
  const header = (who ? who + "'s pull list" : "Movie pull list") +
    " (" + picked.size + "):";
  return header + "\\n\\n" +
    [...picked].sort().map(t => "  - " + t).join("\\n") + "\\n";
}

async function sendToDiscord() {
  // Discord caps messages at 2000 chars; split long lists across messages.
  const lines = listText().split("\\n");
  const chunks = [];
  let cur = "";
  for (const line of lines) {
    if ((cur + line).length > 1900) { chunks.push(cur); cur = ""; }
    cur += line + "\\n";
  }
  if (cur.trim()) chunks.push(cur);

  btnExport.disabled = true;
  btnExport.textContent = "Sending\u2026";
  try {
    for (const chunk of chunks) {
      const res = await fetch(WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: chunk })
      });
      if (!res.ok && res.status !== 204) throw new Error("HTTP " + res.status);
      // stay under Discord's webhook rate limit on multi-chunk sends
      if (chunks.length > 1) await new Promise(r => setTimeout(r, 700));
    }
    btnExport.textContent = "Sent!";
  } catch (e) {
    btnExport.textContent = "Failed \u2014 retry";
    alert("Couldn't reach Discord. Check your connection and try again.\\n\\n" + e);
  } finally {
    setTimeout(() => {
      btnExport.textContent = "Send list to Discord";
      btnExport.disabled = picked.size === 0;
    }, 2000);
  }
}

btnExport.addEventListener("click", () => {
  if (WEBHOOK) { sendToDiscord(); return; }
  const blob = new Blob([listText()], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "movie-pull-list.txt";
  a.click();
  URL.revokeObjectURL(a.href);
});
btnCopy.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(listText());
    btnCopy.textContent = "Copied!";
    setTimeout(() => (btnCopy.textContent = "Copy to clipboard"), 1500);
  } catch (e) { alert(listText()); }
});
btnClear.addEventListener("click", () => {
  if (!confirm("Clear all " + picked.size + " picks?")) return;
  picked.clear(); savePicks(); render();
});

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

q.addEventListener("input", render);
genreSel.addEventListener("change", render);
sortSel.addEventListener("change", render);
savePicks();
render();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="Generate a shareable HTML catalog from Jellyfin.")
    ap.add_argument("--url", required=True, help="Jellyfin base URL, e.g. http://192.168.68.136:8096")
    ap.add_argument("--api-key", required=True, help="Jellyfin API key (Dashboard -> API Keys)")
    ap.add_argument("--output", default="movie_catalog.html", help="Output HTML file")
    ap.add_argument("--title", default="Movie Library", help="Page title")
    ap.add_argument("--poster-width", type=int, default=240)
    ap.add_argument("--quality", type=int, default=80)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--library", default=None, help="Only include this library (by name)")
    ap.add_argument("--discord-webhook", default="",
                    help="Discord webhook URL; if set, the page sends the pull list to "
                         "Discord instead of downloading a .txt file")
    ap.add_argument("--split", action="store_true",
                    help="Write a site folder (index.html + posters/*.jpg) instead of one "
                         "big HTML file. Use this for Cloudflare Pages, which caps files "
                         "at 25 MB each. --output is treated as the folder name.")
    args = ap.parse_args()

    base_url = args.url.rstrip("/")
    session = requests.Session()
    session.headers["Authorization"] = f'MediaBrowser Token="{args.api_key}"'

    print("Fetching movie list...")
    items = fetch_movies(session, base_url, args.library)
    if not items:
        sys.exit("No movies found. Check the URL, API key, and library name.")
    print(f"Found {len(items)} movies. Downloading posters...")

    from pathlib import Path
    posters_dir = None
    if args.split:
        out_dir = Path(args.output)
        if out_dir.suffix.lower() == ".html":
            out_dir = out_dir.with_suffix("")  # "--output index.html --split" -> ./index/
        posters_dir = out_dir / "posters"
        posters_dir.mkdir(parents=True, exist_ok=True)

    records = build_records(session, base_url, items, args.poster_width,
                            args.quality, args.workers, posters_dir)

    import datetime
    stamp = datetime.date.today().isoformat()
    page = (
        PAGE_TEMPLATE
        .replace("__TITLE__", html.escape(args.title))
        .replace("__STAMP__", stamp)
        .replace("__WEBHOOK__", args.discord_webhook.strip())
        .replace("__DATA__", json.dumps(records, separators=(",", ":")))
    )

    if args.split:
        out_path = out_dir / "index.html"
    else:
        out_path = args.output

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)

    if args.split:
        total = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
        print(f"Done: {out_dir}/ ({total / 1_048_576:.1f} MB total, "
              f"{len(records)} movies, largest file "
              f"{max(p.stat().st_size for p in out_dir.rglob('*') if p.is_file()) / 1_048_576:.1f} MB)")
        print(f"Upload the whole '{out_dir}' folder (or zip it) to Cloudflare Pages.")
    else:
        size_mb = len(page.encode("utf-8")) / 1_048_576
        print(f"Done: {out_path} ({size_mb:.1f} MB, {len(records)} movies)")
        print("Send that file to your friend, or drop it on Cloudflare Pages / GitHub Pages.")


if __name__ == "__main__":
    main()