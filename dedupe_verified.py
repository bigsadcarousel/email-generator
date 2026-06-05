#!/usr/bin/env python3
"""
Collapse a MillionVerifier "Good Emails Only" export to one email per lead.

The verifier returns every deliverable guess, so one person can have several
`ok` rows (real aliases, or a permissive/catch-all-lite domain that accepts
everything). This keeps ONE email per lead and tags how much to trust it:

  * 1 verified email   -> keep it.                    confidence = verified
  * 2-3 verified        -> canonical pick (domain      confidence = high
                           convention, else empirical global order)
  * 4-6 verified, or a permissive domain -> best-guess, confidence = low_catchall

The logic lives in email_core.py (shared with the web app); this is the CLI
wrapper. The input file is never modified. Dropped aliases (which still
deliver) are saved to a sibling file for a full audit trail.

Usage:
    python3 dedupe_verified.py                      # uses defaults below
    python3 dedupe_verified.py verified.csv out.csv
"""

import csv
import sys

import email_core

INPUT_FILE = "data_emails_OK_ONLY_MILLIONVERIFIER.COM.csv"
OUTPUT_FILE = "data_verified_deduped.csv"


def run(input_file, output_file):
    with open(input_file, newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f))
    header, data = rows[0], rows[1:]

    guess = email_core.guess_columns(header)
    missing = [k for k in ("first", "last", "domain", "email") if guess[k] is None]
    if missing:
        sys.exit(f"Could not find column(s) for: {', '.join(missing)} in header {header}")

    out_h, out_rows, drop_h, drop_rows, stats = email_core.dedupe(
        header, data, guess["first"], guess["last"], guess["domain"], guess["email"])

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([out_h] + out_rows)
    dropped_file = output_file.replace(".csv", "") + "_dropped.csv"
    with open(dropped_file, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([drop_h] + drop_rows)

    print(f"Verified rows read:       {stats['rows_read']}")
    print(f"Unique leads (out):       {stats['leads_out']}")
    print(f"Aliases dropped:          {stats['dropped']}")
    print(f"  check: {stats['leads_out']} + {stats['dropped']} = "
          f"{stats['leads_out'] + stats['dropped']} (should equal rows read)")
    print(f"Empirical global order:   {' > '.join(stats['global_order'])}")
    print(f"Domains with a learned convention: {stats['conventions']}")
    print(f"Permissive (catch-all-lite) domains: {len(stats['permissive_domains'])}")
    print("Confidence breakdown:")
    for k in ("verified", "high", "low_catchall"):
        print(f"  {k:<13} {stats['confidence'][k]}")
    print(f"Output file:              {output_file}")
    print(f"Dropped aliases file:     {dropped_file}")


if __name__ == "__main__":
    in_file = sys.argv[1] if len(sys.argv) > 1 else INPUT_FILE
    out_file = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_FILE
    run(in_file, out_file)
