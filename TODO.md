# TODO

- [ ] Add authenticated HTTP coverage tests for the new admin mutation routes (`/admin/api/*`, `/admin/session/*`, `/admin/user/*`, `/admin/pass/*`).
- [ ] Add a dedicated operator runbook for expired TickTick session recovery, including Telegram failure modes, SSH fallback, and `session refresh` decision paths.
- [ ] Add automated end-to-end smoke coverage for Telegram admin command dispatch against a disposable test harness.
- [ ] Decide whether `/urls` should remain a standalone Telegram command or be folded into `/status` once operators are comfortable with the unified admin contract.
