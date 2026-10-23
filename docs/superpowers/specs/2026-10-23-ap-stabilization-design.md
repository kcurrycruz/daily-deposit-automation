# AP reliability stabilization

## Intent and scope

Make the existing AP workspace dependable while keeping its current screens,
saved originals, BILL imports, matching rules, and review history. The user
selected stabilization in place, not a native Streamlit rewrite. This is a
bounded first reliability pass, not a promise that every hosting failure can be
fixed inside the application.

## Approaches

- **Selected: stabilize the current embedded app.** Preserve familiar workflows
  and existing storage contracts; remove reproducible rendering and recovery
  problems without introducing another hosting service.
- **Not selected: rebuild with native Streamlit controls.** This would reduce
  the custom communication surface but requires reimplementing review and PDF
  interactions. It is a separate project, not a prerequisite for this pass.

## Changes

1. **Keep active views stable.** Background duplicate notifications update only
   duplicate status/navigation and, when visible, the duplicate workspace. They
   must not recreate the Vendor search field, statement list, open PDF canvas,
   or history preview. Preserve focused duplicate controls and unsaved notes.
   Genuine statement/source changes must still refresh their evidence. Include
   the already committed local PDF stability fix in verification.
2. **Serialize recovery correctly.** Repeated Refresh/Restart clicks join an
   existing operation rather than enqueueing a second restart using an obsolete
   generation. A conflict refresh reads authoritative status; an initial ensure
   failure without a scan ID must recover without a null-property error. Never
   silently replay a stale review write or steal another session's lease.
3. **Tell users what is happening.** Distinguish reading, candidate checks,
   packaging, and review preparation. Show an honest waiting/interrupted state
   when another session owns the scan or progress stops; all records read must
   not imply completion. Avoid claiming the BILL source changed unless that is
   actually established. Expose safe stage/checkpoint/timing diagnostics, not
   credentials, invoice data, or raw backend exception text.
4. **Bound startup failure.** Preserve the minimal loading presentation, but
   surface an actionable failure when the component/bridge cannot initialize;
   do not leave a successful-looking empty workspace or hide an existing error.
   No repeated automatic reloads and no credential handling.

## Constraints and builder calls

Keep Streamlit, JavaScript, Python, the private Supabase bucket, existing schema,
and server-side authorization. No new service, database migration, automatic
financial decision, bill/credit mutation, data deletion, or Daily Deposit change.
Selecting thresholds and the smallest status-only DOM update mechanism is left
to implementation, with tests and the chosen values documented. A durable
independent scan worker or a broader transport replacement requires a separate
design and approval.

## Verification and release

Reproduce each changed behavior in a failing regression first. Run the complete
AP frontend suite, affected backend/bridge tests, build, and whitespace checks.
Use synthetic browser fixtures to verify continuous Vendor typing, navigation,
PDF highlighting, interrupted/expired scans, conflict recovery, and repeated
clicks. Verify source replacement and access denial still fail safely. Run the
broader backend suite before integration; live recovery is a separate check,
not inferred from local tests. Commit locally; merging, pushing, deployment, and
any production administrative change require separate user authorization.

## Approval

Approach and written design approved by the user on October 23, 2026. Prepare
the implementation plan for review before product implementation.
