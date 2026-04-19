---
description: Open the digest web UI or generate a new digest on demand
argument-hint: "[today|YYYY-MM-DD|generate]"
allowed-tools: Bash(claude-almanac:*)
---

Interpret `${ARGUMENTS:-today}`:

- `today` (or empty) → open the most recent digest in the browser.
- `YYYY-MM-DD` → open that digest.
- `generate [--repo NAME] [--since HOURS]` → shell out to `claude-almanac digest generate`.

Execute:

```bash
case "${ARGUMENTS:-today}" in
  generate*)
    # Strip leading "generate" and pass remaining args through.
    args="${ARGUMENTS#generate}"
    claude-almanac digest generate $args
    ;;
  today)
    open http://127.0.0.1:8787/today 2>/dev/null || xdg-open http://127.0.0.1:8787/today
    ;;
  *)
    open "http://127.0.0.1:8787/digest/${ARGUMENTS}" 2>/dev/null || \
      xdg-open "http://127.0.0.1:8787/digest/${ARGUMENTS}"
    ;;
esac
```
