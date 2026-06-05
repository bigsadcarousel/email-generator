#!/usr/bin/env python3
"""
Core email logic shared by the command-line scripts and the web app.

Pure functions only -- no file reading or writing happens here. Callers pass in
already-parsed rows (a header list + a list of row lists) and get back rows +
a stats dict. This keeps the verified generate/dedupe behaviour in ONE place so
the UI can never drift from the CLI.
"""

import re
import unicodedata
from collections import Counter, defaultdict

# ---- Patterns --------------------------------------------------------------

# Each builder receives cleaned first, last, and their initials, and returns the
# local-part (before the "@"). Order here is the canonical tie-break order.
PATTERNS = [
    ("first.last", lambda f, l, fi, li: f"{f}.{l}"),
    ("firstlast", lambda f, l, fi, li: f"{f}{l}"),
    ("flast", lambda f, l, fi, li: f"{fi}{l}"),
    ("f.last", lambda f, l, fi, li: f"{fi}.{l}"),
    ("first", lambda f, l, fi, li: f"{f}"),
    ("firstl", lambda f, l, fi, li: f"{f}{li}"),
]
PATTERN_NAMES = [name for name, _ in PATTERNS]
_BUILDERS = dict(PATTERNS)

# Dedupe tuning (see the diagnosis we ran on the real export).
CATCHALL_LEAD_THRESHOLD = 4      # this many verified guesses == treat as catch-all
PERMISSIVE_MIN_LEADS = 3         # a domain needs this many leads to be judged
PERMISSIVE_MIN_RATIO = 4.0       # ...averaging this many verified emails each
CONVENTION_MIN_EXAMPLES = 2      # unambiguous leads needed to trust a convention


# ---- Helpers ---------------------------------------------------------------

def clean(value):
    """Lowercase, strip accents, and remove every non a-z character."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", value.lower())


def _cell(row, idx):
    return row[idx].strip() if 0 <= idx < len(row) else ""


def guess_columns(header):
    """Best-guess column indexes for first/last/domain/email by header name."""
    guess = {"first": None, "last": None, "domain": None, "email": None}
    for i, name in enumerate(header):
        n = name.lower().strip()
        if guess["first"] is None and "first" in n:
            guess["first"] = i
        if guess["last"] is None and "last" in n and "name" in n:
            guess["last"] = i
        if guess["domain"] is None and "domain" in n:
            guess["domain"] = i
        if guess["email"] is None and n == "email":
            guess["email"] = i
    # looser email fallback
    if guess["email"] is None:
        for i, name in enumerate(header):
            if "email" in name.lower():
                guess["email"] = i
                break
    return guess


def pattern_of(first, last, local):
    """Return the pattern label that produced `local`, or None."""
    f, l = clean(first), clean(last)
    if not (f and l):
        return None
    fi, li = f[0], l[0]
    for name, build in PATTERNS:
        if build(f, l, fi, li) == local:
            return name  # first match wins on the rare collision
    return None


# ---- Generate --------------------------------------------------------------

def generate_candidates(header, rows, col_first, col_last, col_domain, enabled=None):
    """Long-format candidate emails: one output row per (contact, pattern).

    Returns (out_header, out_rows, stats).
    """
    if enabled is None:
        enabled = PATTERN_NAMES
    builders = [(n, _BUILDERS[n]) for n in enabled if n in _BUILDERS]

    out = []
    made = blank = 0
    for row in rows:
        first = clean(_cell(row, col_first))
        last = clean(_cell(row, col_last))
        domain = _cell(row, col_domain).lower()

        if first and last and domain:
            fi, li = first[0], last[0]
            seen = set()
            for _, build in builders:
                local = build(first, last, fi, li)
                if local in seen:
                    continue
                seen.add(local)
                out.append(row + [f"{local}@{domain}"])
                made += 1
        else:
            out.append(row + [""])
            blank += 1

    stats = {"contacts_read": len(rows), "candidates_written": made, "blank_rows": blank}
    return header + ["email"], out, stats


# ---- Dedupe ----------------------------------------------------------------

def dedupe(header, rows, col_first, col_last, col_domain, col_email):
    """Collapse verified rows to one email per lead, tagged by confidence.

    Returns (out_header, out_rows, dropped_header, dropped_rows, stats).
    """
    # group rows by lead -> list of (row, pattern_label)
    leads = defaultdict(list)
    lead_domain = {}
    for row in rows:
        email = _cell(row, col_email)
        if "@" not in email:
            continue
        local = email.split("@", 1)[0]
        first, last = _cell(row, col_first), _cell(row, col_last)
        domain = _cell(row, col_domain).lower()
        key = (clean(first), clean(last), domain)
        label = pattern_of(first, last, local) or "?unknown"
        leads[key].append((row, label))
        lead_domain[key] = domain

    # learn empirical global order + per-domain conventions from 1-ok leads
    global_freq = Counter()
    domain_freq = defaultdict(Counter)
    for key, cands in leads.items():
        if len(cands) != 1:
            continue
        label = cands[0][1]
        global_freq[label] += 1
        domain_freq[lead_domain[key]][label] += 1

    global_order = [lbl for lbl, _ in global_freq.most_common()]
    for name in PATTERN_NAMES:
        if name not in global_order:
            global_order.append(name)
    global_order.append("?unknown")

    conventions = {
        dom: freq.most_common(1)[0][0]
        for dom, freq in domain_freq.items()
        if sum(freq.values()) >= CONVENTION_MIN_EXAMPLES
    }

    # permissive (catch-all-lite) domains: many leads, lots of oks each
    dcount = defaultdict(lambda: [0, 0])
    for key, cands in leads.items():
        dcount[lead_domain[key]][0] += 1
        dcount[lead_domain[key]][1] += len(cands)
    permissive = {
        d for d, (nl, ne) in dcount.items()
        if nl >= PERMISSIVE_MIN_LEADS and ne / nl >= PERMISSIVE_MIN_RATIO
    }

    out = []
    dropped = []
    conf_counts = Counter()
    bucket_counts = {"1": 0, "2-3": 0, "4-6": 0}

    for key, cands in leads.items():
        domain = lead_domain[key]
        n = len(cands)
        bucket_counts["1" if n == 1 else "2-3" if n <= 3 else "4-6"] += 1

        if n == 1:
            chosen_row, reason, confidence = cands[0][0], "sole_ok", "verified"
        else:
            confidence = "low_catchall" if (n >= CATCHALL_LEAD_THRESHOLD or domain in permissive) else "high"
            labels = {}
            for row, label in cands:
                labels.setdefault(label, row)  # first wins
            conv = conventions.get(domain)
            if conv and conv in labels:
                chosen_label, reason = conv, f"domain_convention:{conv}"
            else:
                chosen_label = min(labels, key=lambda lbl: global_order.index(lbl))
                reason = f"global_priority:{chosen_label}"
            chosen_row = labels[chosen_label]

        out.append(chosen_row + [confidence, reason])
        conf_counts[confidence] += 1
        kept_email = _cell(chosen_row, col_email)
        for row, _ in cands:
            if row is not chosen_row:
                dropped.append(row + [confidence, kept_email])

    stats = {
        "rows_read": sum(len(c) for c in leads.values()),
        "leads_out": len(leads),
        "dropped": len(dropped),
        "buckets": bucket_counts,
        "confidence": {k: conf_counts[k] for k in ("verified", "high", "low_catchall")},
        "global_order": global_order[:len(PATTERN_NAMES)],
        "conventions": len(conventions),
        "permissive_domains": sorted(permissive),
    }
    return (header + ["confidence", "pick_reason"], out,
            header + ["confidence_of_kept", "kept_email"], dropped, stats)
