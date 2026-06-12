# Email Generator + Verifier Deduper

A small, **zero-dependency** toolkit (pure Python standard library — no `pip install`) for the cold-email workflow:

1. **Generate** candidate email addresses from a contact CSV.
2. Send those candidates to an email verifier (e.g. [MillionVerifier](https://www.millionverifier.com/)).
3. **Dedupe** the verifier's results down to **one trustworthy email per lead**.

Everything runs **100% offline** on your own machine. Your contact data never leaves your computer.

---

## Quick start — the web app

```bash
python3 app.py
```

Opens `http://localhost:8000` in your browser. Two tabs:

- **① Generate** — drop a contact CSV, confirm the First / Last / Domain columns (auto-detected), tick which email patterns to produce, and download the candidate list.
- **② Dedupe** — drop the verifier's "Good Emails Only" export, confirm the First / Last / Title / Company / Domain / Email columns (auto-detected), review the breakdown, and download the deduped file (one per lead) plus the dropped aliases.

No data is written to disk except the files you choose to download.

## Command line

The same logic is available as scripts:

```bash
python3 generate_emails.py  input.csv  candidates.csv
python3 dedupe_verified.py  verified.csv  deduped.csv
```

---

## How generation works

For each contact it builds local-parts from the name and appends the company domain. The six default patterns:

| Pattern | Example (Jane Doe @ acme.com) |
|---|---|
| `first.last` | jane.doe@acme.com |
| `firstlast`  | janedoe@acme.com |
| `flast`      | jdoe@acme.com |
| `f.last`     | j.doe@acme.com |
| `first`      | jane@acme.com |
| `firstl`     | janed@acme.com |

Output is long-format: one row per candidate, ready to upload to a verifier.

## How dedupe works

The verifier marks every deliverable guess `ok`, so one person can come back with several. The deduper keeps **one email per lead**, judges how much to trust it, and **splits the result so your main send list is only the clean, verified addresses**:

- **1 `ok` on a normal domain** → trustworthy. → **verified list** (the deliverable).
- **2–3 `ok`** → real aliases; pick the canonical one (prefers the **company's own observed convention**, learned from coworkers whose email was unambiguous, else the most common format overall). → other-leads file, `confidence = high`.
- **4–6 `ok`, or any domain proven to be catch-all** → the `ok` is unreliable. → other-leads file, `confidence = low_catchall`.

**Catch-all detection.** A domain is treated as catch-all if it accepts mail on volume (many leads, lots of `ok`s each) **or** if even a single lead returns ~all 6 patterns as `ok` — nobody owns five working aliases, so one such lead proves the domain accepts everything. A lone `ok` on a catch-all domain confirms nothing, so it's kept *out* of the verified list too. This is the main lever against "valid but unmonitored / auto-reply" mailboxes.

Output files (all trimmed to **first name, last name, title, company, email**):

| File | Contents |
|---|---|
| `*_deduped.csv` | **Verified list** — your clean send list. |
| `*_deduped_other.csv` | Alias / catch-all leads (+ a `confidence` column). Send cautiously or skip. |
| `*_deduped_dropped.csv` | Aliases set aside from multi-`ok` leads, full original columns, for audit. |

The input file is never modified.

---

## Files

| File | Purpose |
|---|---|
| `app.py` | Zero-install local web UI (stdlib `http.server`). |
| `email_core.py` | Shared generate + dedupe logic. Single source of truth. |
| `generate_emails.py` | Command-line wrapper for generation. |
| `dedupe_verified.py` | Command-line wrapper for dedupe. |

## Privacy

`.gitignore` excludes all `*.csv` files. **Contact data stays local** — only the code is tracked in git.
