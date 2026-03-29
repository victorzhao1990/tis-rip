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
./rip.py [--output <dir>] <doc_id> [<doc_id> ...]
```

### Arguments

| Argument | Description |
|---|---|
| `--output <dir>` | Directory to write PDFs into (default: current directory) |
| `EM…` | Electrical wiring diagram ID |
| `RM…` | Repair manual ID |
| `BM…` | Collision repair manual ID |

### Example

```
./rip.py RM3560U BM3560U --output "/Users/you/Documents/GR Corolla Service Manual"
```

The script will open Chrome, navigate to TIS, and pause for you to log in. Press Enter when ready.

## Output structure

```
<output>/
  <doc_id>/
    <Section>/
      <Section>_ <Subsection>_ <Page Title>_ <vehicle info>.pdf
```

For example:
```
GR Corolla Service Manual/
  BM3560U/
    General/
      General_ INTRODUCTION_ HOW TO USE THIS MANUAL_ GENERAL INFORMATION_ ....pdf
  RM3560U/
    Engine/
      Engine_ ..._ ....pdf
```

Intermediate HTML files are cached in `./<doc_id>/html/` so re-runs skip already-downloaded pages.

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
- The `download/` folder is a temporary staging area for browser downloads and is cleared on each run.
- The cert warning (`Error parsing certificate`) printed during headless PDF rendering is harmless.
- Document IDs (e.g. `RM3560U`, `BM3560U`) can be found in the TIS URL when browsing a manual.
