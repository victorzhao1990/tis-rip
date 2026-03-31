# tis-rip

Downloads Toyota repair manuals, collision repair manuals, and electrical wiring diagrams from [Toyota TIS (techinfo.toyota.com)](https://techinfo.toyota.com) and saves them as PDFs organized by section.

## Prerequisites

Python 3 and the following packages:

```
pip install -r requirements.txt
```

Google Chrome must be installed. The script also requires ChromeDriver — see [Known limitations](#known-limitations) below.

## Usage

```
./rip.py [--output <dir>] [--cache-dir <dir>] [--model <name>] [--engine <name>] [--year <yyyy>] [--choose-filters] [--all-filters] [--render-from-cache|--reindex] <doc_id> [<doc_id> ...]
```

### Arguments

| Argument | Description |
|---|---|
| `--output <dir>` | Directory to write PDFs and `index.html` into (default: `output`) |
| `--cache-dir <dir>` | Directory to store cached TOCs, HTML, and temporary downloads (default: `cache`) |
| `--model <name>` | Limit RM/BM manual pages to a specific `tocmodelname` such as `GR Corolla` |
| `--engine <name>` | Limit RM/BM manual pages to a specific engine such as `G16E-GTS` |
| `--year <yyyy>` | Limit RM/BM manual pages to one or more model years such as `2025` |
| `--choose-filters` | Prompt again for RM/BM filter selection even if a saved choice already exists |
| `--all-filters` | Run non-interactively with no RM/BM filtering and fetch all available content |
| `--render-from-cache` | Render missing PDFs from cached HTML and rebuild indexes without logging in |
| `--reindex` | Rebuild indexes from cached TOCs without downloading or rendering |
| `EM…` | Electrical wiring diagram ID |
| `RM…` | Repair manual ID |
| `BM…` | Collision repair manual ID |

### Example

```
./rip.py RM3560U BM3560U --output "/Users/you/Documents/GR Corolla Service Manual"
```

Filter to a specific model directly:

```
./rip.py --model "GR Corolla" RM3560U
```

The script will open Chrome, navigate to TIS, and pause for you to log in. Press Enter when ready.

If Toyota expires the session mid-run, the script now retries once automatically. If TIS still shows the login page, it will pause again so you can reauthenticate in the same Chrome window and continue.

If you do not pass filters directly, the script will read the TOC metadata, show the available models, engines, and years, and ask you to choose one, some, or all. It also suggests when each filter is likely useful. That selection is saved per document and reused on later runs so resume picks up the same choice automatically.

If you want to skip prompts entirely and fetch everything, use:

```
./rip.py --all-filters RM3560U
```

Recovery examples:

```
./rip.py --render-from-cache RM3560U BM3560U
./rip.py --reindex RM3560U BM3560U
./rip.py --choose-filters RM3560U
```

## Output structure

```
<output>/
  <doc_id>/
    <filter selection>/
      html/
        <TIS Page Id>.html
      pdf/
        <Section>/
          <Subsection>/
            <Page Title>.pdf
```

For example:
```
GR Corolla Service Manual/
  RM3560U/
    models_GR Corolla__engines_G16E_GTS__years_2025/
      html/
        RM100000002QJU4.html
      pdf/
        General/
          INTRODUCTION/
            IDENTIFICATION INFORMATION/
              VEHICLE IDENTIFICATION AND SERIAL NUMBERS_ 2024 _ 2025 MY GR Corolla Corolla Corolla Hatchback Corolla HV _08_2023 _ 09_2024_.pdf
```

Intermediate HTML files, `toc.xml`, and temporary downloads are cached under the cache directory so re-runs skip already-downloaded pages. Output HTML, PDFs, and the generated `index.html` are written under the output directory.

## Known limitations

### Chrome path is hardcoded (macOS only)

The script assumes Chrome is installed at:
```
/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
```
This is used for headless PDF rendering. If Chrome is installed elsewhere (e.g. on Linux or Windows), edit the path in `make_pdf()` near the bottom of `rip.py`:
```python
def make_pdf(src, dest):
    subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", ...])
```

### ChromeDriver version must match Chrome

`webdriver-manager` automatically downloads the matching ChromeDriver at runtime. If you see a `SessionNotCreatedException` mentioning a version mismatch, it means the auto-downloaded driver doesn't match your installed Chrome version. Try updating Chrome to the latest version and re-running.

### TIS subscription required

You must have an active Toyota TIS subscription. The script pauses at login so you can authenticate in the browser window it opens.

## Notes

- A `user-data` Chrome profile is saved locally so the browser remembers your TIS login session between runs.
- The cache directory stores temporary downloads plus cached TOCs and HTML, and is cleared only for the temporary download staging area on each run.
- Generated manual caches and `output/` are ignored by git.
- The cert warning (`Error parsing certificate`) printed during headless PDF rendering is harmless.
- Document IDs (e.g. `RM3560U`, `BM3560U`) can be found in the TIS URL when browsing a manual.
