# Private AP email intake

This module is a staged deployment. It contains no token values or default cloud target. Both the PDF queue and five-minute schedule start **paused**. It never configures public invokers. Runtime accounts receive access only to the selected Gmail secret and the existing server-key secret. The server key remains a broad Supabase service credential, so the Python runtime fixes the workspace and exposes only the listed operations.

Read [the owner setup and recovery guide](../../docs/ap-gmail-intake-setup.md) before applying anything. Confirm the Google project/region, AP workspace, private bucket, Gmail account, and an authorized synthetic database first. Applying these files, authorizing Gmail, and enabling the schedule are separate owner actions.

Use a reviewed, git-ignored `.tfvars` file containing **IDs and secret references only**, matching the required variables. `plan.ps1 -VariablesFile <absolute-file>` initializes providers, checks formatting, validates, and produces a plan. It does not apply it. Keep Terraform state private even though token values are not input variables.

Google provider and beta provider are pinned to 8.10.0; beta is used only to create the required Google-managed service identities. Fixed custom audiences avoid a service referring to its own not-yet-created URL. The actual task URL must still be a private Cloud Run `run.app` service; its task signer, project, and custom audience remain pinned. This module's next apply restores the configured paused queue/schedule; intentional activation happens only after acceptance.

Local validation commands (no apply):

```powershell
terraform -chdir=deploy/ap_mail init -backend=false -input=false
terraform -chdir=deploy/ap_mail fmt -check
terraform -chdir=deploy/ap_mail validate
docker build -f workers/ap_mail/Dockerfile -t ap-mail-smoke .
docker run --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g --entrypoint python ap-mail-smoke -m workers.ap_mail.smoke
```

Keep Chromium's sandbox enabled. A failed Linux/container smoke blocks rollout; do not add `--no-sandbox` to make a test pass. Cloud Run execution also needs an authorized synthetic round trip because a local Docker pass does not establish that the service sandbox permits nested Chromium isolation.
