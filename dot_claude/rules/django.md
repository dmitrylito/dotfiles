---
paths: ["**/models.py", "**/views.py", "**/admin.py", "**/tasks.py", "**/api.py", "**/serializers.py", "**/services/**", "**/management/commands/**", "**/urls.py"]
---
# Django architecture — thin entry points, class-driven services

- Business logic lives in the app's `services/` module — never in views, management
  commands, Celery/queue tasks, serializers, or signals. Those are thin entry points:
  parse input, call a service, render/return the result.
- Services are CLASS-DRIVEN: encapsulate each domain operation in a service class
  (state via `__init__`, one clear public entry method), not floating module-level
  functions. Group related operations in one class instead of scattering helpers.
  This is a fallback for projects without an established convention: explicit
  repository architecture and existing pure-function service/engine patterns win.
  Do not convert those functions to classes solely to satisfy this default.
- Models hold data shape and simple domain invariants; querying beyond trivial lookups
  belongs in managers/querysets or services, not sprinkled through views.
- The repos differ on queue (NSQ in backend, Celery in ops-center) and test runner —
  check the repo's CLAUDE.md before assuming either.
