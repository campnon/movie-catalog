# Jellyfin Movie Catalog Generator

A lightweight Python script that generates a responsive, visually appealing HTML catalog of your Jellyfin movie library. This allows you to share your movie collection with friends or family without giving them direct access to your Jellyfin server. Viewers can browse, search, filter, and curate a "pull list" of movies to send back to you.

## Features

- **Interactive Grid**: Beautiful, responsive card layout showing movie posters and details (title, year, runtime, rating, and genres).
- **Search & Filter**: Real-time title search and genre filtering.
- **Sorting Options**: Sort by title (A–Z), release year (newest/oldest), recently added, and highest rated.
- **Curated Pull List**: Viewers can click on posters to add movies to a personal "pull list".
- **Easy Exporting**: Viewers can download their pull list as a `.txt` file, copy it to the clipboard, or send it directly to a configured **Discord Webhook** with custom name input.
- **Two Generation Modes**:
  - **Single HTML File**: Everything (including movie posters encoded in Base64) is embedded into a single, self-contained HTML file. Perfect for sharing via email or chat.
  - **Split Folder (Recommended for hosting)**: Generates an `index.html` file alongside a `posters/` folder containing JPEG images. This keeps file sizes small and is perfect for hosting on Cloudflare Pages or GitHub Pages.

---

## Installation

The generator requires Python 3 and the `requests` library.

1. Clone or download this repository.
2. Install the required dependency:
   ```bash
   pip install requests
   ```

---

## Usage

### Getting a Jellyfin API Key
1. Log into your Jellyfin server as an administrator.
2. Go to the **Admin Dashboard** -> **API Keys**.
3. Click the **+** (Add) button, give it a name (e.g., "Catalog Generator"), and copy the generated key.

### Basic Generation (Single HTML File)
To generate a single self-contained HTML file:
```bash
python3 jellyfin_catalog.py --url http://YOUR_JELLYFIN_IP:8096 --api-key YOUR_API_KEY --output my_movies.html
```

### Advanced Generation (Split Folder for Hosting)
For larger libraries, embedding posters as base64 can make the HTML file extremely large. Use the `--split` flag to output a directory structure:
```bash
python3 jellyfin_catalog.py --url http://YOUR_JELLYFIN_IP:8096 --api-key YOUR_API_KEY --output catalog --split
```
This generates:
- `catalog/index.html`
- `catalog/posters/*.jpg`

---

## Command Line Options

| Flag | Default | Description |
|------|---------|-------------|
| `--url` | *Required* | The base URL of your Jellyfin server (e.g., `http://192.168.1.100:8096`). |
| `--api-key` | *Required* | Your Jellyfin API key. |
| `--output` | `movie_catalog.html` | Output file name (or directory name if `--split` is used). |
| `--title` | `Movie Library` | The title header shown at the top of the generated page. |
| `--split` | *None* | Writes a folder (`index.html` + `posters/` directory) instead of a single large HTML file. |
| `--library` | `None` | Optional name of the library folder to scan (e.g. `"Movies"`). If omitted, scans all movies. |
| `--discord-webhook` | `None` | A Discord webhook URL. If provided, the "Download list" button becomes "Send list to Discord" and posts selected movies directly to a Discord channel. |
| `--poster-width` | `240` | Width of the downloaded poster images in pixels. |
| `--quality` | `80` | JPEG compression quality (1-100) for posters. |
| `--workers` | `8` | Number of concurrent threads to use for downloading posters. |

---

## Deployment (Cloudflare Pages Example)

If you generated a split folder using the `--split` flag, you can easily host it on Cloudflare Pages.

1. Install Wrangler CLI:
   ```bash
   npm install -g wrangler
   ```
2. Deploy the generated folder (assuming your output directory is named `catalog`):
   ```bash
   npx wrangler pages deploy catalog --project-name movie-catalog
   ```
