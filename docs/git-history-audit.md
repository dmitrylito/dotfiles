# Git history audit — 2026-09-18

A fresh `git clone --mirror https://github.com/dmitrylito/dotfiles.git` was
inspected, including every advertised ref fetched by the mirror: `master`,
seven pull-request heads, and the published `refs/remotes/origin/main` ref.
The `master` commit was `8b5eb262eaf39fd6d20c57315d339ec86dcd9be1`.

- Packed objects: 6.97 MiB across 7,788 objects.
- Largest reachable blob: 2,630,689 bytes, an old Spaceship theme demo GIF.
- No reachable paths containing `elephant`, case-insensitively.
- No blobs larger than 10 MiB; `git fsck --full --no-reflogs` passed.

No history rewrite or force-push is warranted by this evidence. In particular,
`git-filter-repo --strip-blobs-bigger-than 10M` would remove no blobs from the
inspected remote history. The previous README instruction to coordinate an
Elephant purge was stale. This inspection cannot account for unadvertised
server-side objects, other forks, or future pushes.

The working clone had about 53 MiB in `.git`. Normal `git gc` completed, leaving
50.36 MiB of packed objects under Git's normal retention policy. No forced
reflog expiration, aggressive pruning, ref deletion, or remote mutation was
performed. Further local space recovery is unnecessary for clone portability.

Audit commands, run against the fresh mirror:

```bash
git count-objects -vH
git for-each-ref --format='%(refname) %(objectname)'
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' | sort -k2nr | head
git rev-list --objects --all | rg -i elephant
git fsck --full --no-reflogs
```
