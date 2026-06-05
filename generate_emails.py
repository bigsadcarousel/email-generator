#!/usr/bin/env python3
"""
Generate candidate email addresses for a contact list.

Reads a CSV with First Name, Last Name and Company Domain columns and writes a
long-format CSV with all original columns plus an appended `email` column --
one row per candidate email, ready to feed into an email verifier.

The actual logic lives in email_core.py (shared with the web app); this file is
just the command-line wrapper.

Usage:
    python3 generate_emails.py                       # uses defaults below
    python3 generate_emails.py input.csv output.csv  # custom paths
"""

import csv
import sys

import email_core

INPUT_FILE = "data.csv"
OUTPUT_FILE = "data_emails.csv"

# Column indexes in the input file (0-based): First Name, Last Name, Domain.
COL_FIRST, COL_LAST, COL_DOMAIN = 2, 3, 7


def generate(input_file, output_file):
    with open(input_file, newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f))
    header, data = rows[0], rows[1:]

    out_header, out_rows, stats = email_core.generate_candidates(
        header, data, COL_FIRST, COL_LAST, COL_DOMAIN)

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([out_header] + out_rows)

    print(f"Contacts read:            {stats['contacts_read']}")
    print(f"Email candidates written: {stats['candidates_written']}")
    print(f"Blank-email rows:         {stats['blank_rows']}")
    print(f"Total rows (excl header): {len(out_rows)}")
    print(f"Output file:              {output_file}")


if __name__ == "__main__":
    in_file = sys.argv[1] if len(sys.argv) > 1 else INPUT_FILE
    out_file = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_FILE
    generate(in_file, out_file)
