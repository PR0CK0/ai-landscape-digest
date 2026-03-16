# ci-state

This branch exists solely to persist CI state between GitHub Actions runs.

It contains two files:

- **`digests.json`** — accumulated digest history rendered into the HTML page. Without this, every run starts with an empty history and the site only ever shows one entry.
- **`seen_items.json`** — deduplication state tracking which feed items have already been processed. Without this, every run sees all feed items as new and generates a digest full of old news.

Both files replace what would otherwise be stored in `actions/cache`, which has a 7-day eviction window and is silently reset under storage pressure — causing either history loss or duplicate digests on the next run.

The workflow reads both files from this branch before running and commits the updated versions back after each successful deployment using git plumbing (no working-tree side effects, no commit noise on master).

Do not merge this branch into master or develop.
