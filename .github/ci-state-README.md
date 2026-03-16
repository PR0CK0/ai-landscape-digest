# ci-state branch

This branch is managed automatically by GitHub Actions. Do not edit manually.

It stores two files that persist state between workflow runs:

| File | Purpose |
|---|---|
| `seen_items.json` | Dedup cache — maps item IDs to timestamps so each release is only surfaced once |
| `digests.json` | Digest history — rendered on the GitHub Pages site |

Updated after every successful digest run. To reset, use:
**Actions → Reset Digest State → Run workflow**
