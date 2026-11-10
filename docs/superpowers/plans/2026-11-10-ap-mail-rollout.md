# AP mail rollout implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, with one fresh whole-branch review before integration.

**Goal:** Connect the existing private AP workspace and accept one Gmail statement after Linux checks pass.

**Architecture:** Retain the existing Gmail read-only grant, paused SQL connection and separately gated GitHub batch runner. Repair packaging and sandbox startup without changing extraction or financial review rules.

**Tech stack:** Python 3.12, Node 24, Playwright 1.62.1, PostgreSQL and GitHub Actions.

**Spec:** `docs/ap-gmail-intake-free-setup.md`

## Constraints and review focus

- Scheduled imports stay disabled until controlled acceptance succeeds.
- Credentials, recovery exports and live financial data stay outside the public repository.
- Chromium sandbox remains enabled; no global Ubuntu security changes.
- A missing sandbox helper must fail closed. Child IPC must continue excluding credentials.
- Container builds must include the complete local build dependency chain.
- Preserve existing statements, revisions, completions and duplicate reviews.
- Google External Testing authorization is temporary, not durable unattended operation.

## Tasks

- [x] Confirm the existing project, workspace and private bucket through read-only SQL.
- [x] Download private baseline counts and all AP function, constraint and trigger definitions.
- [ ] Reproduce Linux startup and container build failures from CI evidence.
- [ ] Add a child-environment regression proving sandbox configuration survives while secrets do not; observe RED, implement the minimal allowlist change, observe GREEN.
- [ ] Add the missing build dependency to Docker COPY/context allowlists. Configure Linux to use the existing root-owned Chrome sandbox helper; use Playwright's official container seccomp profile for the sandbox.
- [ ] Run affected local tests and real Linux/container acceptance. Review the complete change before integration and repinning the scheduler.
- [ ] Prepare the exact missing prerequisite/mail migration bundle and inspect ACLs and history preservation. Obtain action-time approval for database access changes and GitHub database credential storage.
- [ ] Apply the reviewed updates, create the paused mailbox binding, configure exact nonsecret runtime variables and verify baseline history counts.
- [ ] With scheduled imports off, run initial mailbox inventory and a deliberately selected single-statement acceptance. Verify private original, extracted rows, BILL comparison and unchanged human history.
- [ ] Report actual results and remaining authorization/activation requirements.
