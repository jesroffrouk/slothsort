# SlothSort

**A lazy, fully local file tidier powered by an open-weight model.**

Your Downloads folder is a mess. You know it, and you keep putting it off. SlothSort does it for you: a local LLM reads each file's name and a snippet of its contents, decides where it belongs, and (optionally) gives it a clean name. Old files get archived by year.

Everything runs on your machine. No cloud, no API keys, no internet required. It's a single Python file that uses only the standard library, so there is nothing to `pip install`.

> Built for the DEV Hacktoberfest Week 3 challenge: *Slow and Steady*.

---

## Features

- **Local AI sorting:** uses any open-weight model served by [Ollama](https://ollama.com) (default: `llama3.2:3b`).
- **Dry run by default:** nothing moves until you pass `--apply`.
- **One-command undo:** every run is logged, so `--undo` puts files back.
- **Smart renaming:** `--rename` lets the model suggest clean, descriptive filenames.
- **Auto-archive:** files older than 90 days go to `Archive/<year>/<category>/`.
- **Sloth mode:** `--watch` re-checks the folder every few minutes, otherwise does nothing.
- **Graceful fallback:** if Ollama isn't running (or the model errors on a file), it falls back to simple extension rules instead of crashing.
- **Safe by design:** skips hidden files, half-downloaded files (`.crdownload`, `.part`, ...), and anything modified in the last 2 minutes. It never overwrites; name collisions get a numeric suffix.

## Quick start

### 1. Install Ollama and pull a model

```bash
# install from https://ollama.com, then:
ollama pull llama3.2:3b
```

Any small open-weight model works (Llama, Gemma, Qwen, Mistral, ...).

### 2. Run SlothSort

```bash
python slothsort.py
```

Requires Python 3.8+. That's it.

## Usage

```text
python slothsort.py [folder] [options]
```

| Option | What it does |
|---|---|
| `folder` | Folder to tidy (default: `~/Downloads`) |
| `--apply` | Actually move files (without it, it's a dry run) |
| `--rename` | Let the model rename files with short descriptive names |
| `--undo` | Revert the most recent run |
| `--watch` | Keep running and tidy periodically |
| `--interval N` | Seconds between checks in watch mode (default: 300) |
| `--archive-days N` | Archive files older than N days (default: 90) |
| `--model NAME` | Ollama model to use (default: `llama3.2:3b`) |
| `--no-llm` | Skip the model, use extension rules only |

### Examples

```bash
# Preview what would happen to Downloads
python slothsort.py

# Tidy your Desktop for real
python slothsort.py ~/Desktop --apply

# Tidy and rename files
python slothsort.py --apply --rename

# Changed your mind? Undo the last run
python slothsort.py --undo

# Full sloth: set it and forget it
python slothsort.py --apply --watch --interval 600

# Use a different model
python slothsort.py --model qwen2.5:3b
```

### Example output

```text
SlothSort looking at /home/me/Downloads [model: llama3.2:3b]
  IMG_2231.jpg          ->  Images/IMG_2231.jpg
  notes_final_v2.txt    ->  Documents/meeting-notes-q3-planning.txt
  setup.exe             ->  Installers/setup.exe
  taxes.pdf             ->  Archive/2024/Documents/taxes.pdf

Dry run: 4 file(s) would move. Add --apply to do it.
```

## Categories

`Documents`, `Images`, `Videos`, `Audio`, `Code`, `Archives`, `Installers`, `Spreadsheets`, `Presentations`, `Books`, `Misc`

Edit the `CATEGORIES` list and `EXT_MAP` at the top of `slothsort.py` to make your own.

## How it works

1. Scans the target folder (non-recursive).
2. For each file, sends the filename, an extension hint, and (for text-like files) the first ~600 characters to your local Ollama model.
3. The model replies with JSON: `{"category": "...", "new_name": "..."}`. Temperature is 0 for consistent results.
4. If the answer isn't a valid category, SlothSort uses the extension rule instead.
5. Files are moved (or just listed, in a dry run), and a log is saved to `.slothsort_log.json` in the folder so `--undo` works.

## Configuration

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Where your Ollama server lives |
| `SLOTH_MODEL` | `llama3.2:3b` | Default model name |

## Why open models?

- **Privacy:** downloads are full of invoices, IDs, and personal documents. Nothing here leaves your machine.
- **Offline:** works without an internet connection.
- **Free to run:** no per-request API bill, even if it checks every 5 minutes.
- **Swappable:** change `--model` to try any open-weight model, with no code changes and no vendor lock-in.

## Limitations

- Only reads content from plain-text-like files; PDFs, images, and Office docs are classified by filename and extension.
- Small models can occasionally pick odd categories or names. That's why dry run is the default and `--undo` exists.
- Non-recursive: it only tidies the top level of the folder you give it.

## Contributing

Hacktoberfest contributions are welcome! Ideas:

- PDF / DOCX text extraction for better classification
- Vision model support for images
- A nightly "here's what I moved" summary
- Custom category rules via a config file

Fork the repo, make your change, and open a pull request.

## License

MIT
