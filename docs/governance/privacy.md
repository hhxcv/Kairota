---
doc:
  updated_at: 2026-07-08
  category: governance
  status: current
  audience: ai
  keywords: [privacy, local-info, secrets, public-text]
  description: "Defines privacy rules for Kairota docs, issues, PRs, and integrations."
---

# Privacy

## Public Text Rule

Do not expose local-only or private information in public docs, issues, PRs,
comments, examples, logs, screenshots, or generated reports.

Common leaks:

- Absolute paths.
- User or home names.
- Local time-zone names.
- Exact local clock values.
- Locale strings.
- Localhost or private endpoints.
- Proxy values.
- Secrets, tokens, cookies, credentials, and account ids.
- Private notes, financial data, account data, or private work records.
- Raw terminal output that contains environment details.

## Storage Rule

Kairota should store only the data needed for scheduling, audit, recovery, and
optimization. Do not store full transcripts, full terminal logs, or private
files by default.

## Integration Rule

Each external adapter must define:

- data read;
- data written;
- permissions required;
- retention expectation;
- failure and redaction behavior.
