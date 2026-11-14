# Diagnose & repair (staged)

The button is visible above the tabs, including Wallpaper. Its first action is an authenticated status refresh only. It does not start/restart Comfy, submit work, apply wallpaper, change settings, grant consent or clear safety receipts. Status is a snapshot, not an active listener/queue/ownership health probe. Managed-service recovery still requires separate owner diagnosis and approval.

## Why a safe guard can still refuse generation

Force selection is saved; Force permission is deliberately memory-only. Restart, Auto OFF, or an automation-policy write revokes it. The GPU guard, connection, automation preference and consent are separate facts. Reconfirm Force permission only after accepting gaming stutter, VR disruption and GPU OOM risk. Existing Auto ON may then resume generation/apply; target and cadence are unchanged. Alternatively choose **Use Guarded instead** to remove Force selection without granting bypass consent. Cancel/close does neither. Unknown/busy/stale state never becomes a safety grant.

A distinct defect made this especially confusing: render dispatch built the manual testing-override policy and then unconditionally replaced it whenever the saved automation policy was `force`, even when Force consent was inactive. Thus a correctly confirmed ten-minute manual override still returned `force_consent_revoked`. Dispatch now keeps the frozen manual override for manual previews, retaining ownership, model, VRAM, expiration and revocation gates. Scheduled work never inherits testing consent. Auto remains paused; no wallpaper is applied by a manual preview.

The old Force generation token is never repaired or reused: rearming consent creates a new generation, and existing closures still reject revoked tokens. This patch does not change scheduler retry identities, release quarantined output, or reconcile pending transactions. `last_error` is retained as previous-attempt history rather than overwriting a successful repair notice every status poll. Current scheduler state remains separately visible. Clearing a historical error is not equivalent to proving readiness.

## Acceptance and deployment

Regression coverage reproduces the exact refused manual request against an ephemeral CPU-only Comfy HTTP fixture, then verifies one fixture prompt and zero wallpaper writes. Negative cases retain VRAM, owner, expired/revoked override and scheduled-force restrictions. A real packaged offscreen Plasma test checks diagnosis without consent, cancel/reset, explicit rearm, status-poll history, and Guarded recovery through the authenticated controller API. The existing forced pipeline tests retain midflight revocation, target/session/pending-transaction gates.

Source and package testing is not deployment. Owner approval, actual loaded-source identification, stopped/idle installation using the reviewed deployment workflow, and separate owner UI acceptance are required. Do not restart an Auto-enabled controller to test this change. Do not run Generate to obtain a status check.
