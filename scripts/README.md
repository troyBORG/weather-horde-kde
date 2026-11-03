# Script guide

These are development and owner-maintenance tools, not a list of commands to run in order. Start with the [main README](../README.md) for everyday use.

## Maintained build and release path

- `package.py` — build the widget/native pairing plugin and controller archive; verify the widget in an isolated package root, not live Plasma.
- `ci_container.sh`, `ci_check.py` — isolated CI entrypoints for native builds, the full suite and public artifacts.
- `ci_release.py`, `public_artifacts.py` — release policy, artifact filtering and verification.
- `make-owner-delivery.py`, `owner-bootstrap.py` — build and check the hash-pinned owner delivery. See [delivery instructions](../docs/owner-installer-hardening.md).

## Current owner installation and diagnostics

- `install-controller-service.py` — install a persistent graphical-session controller, with stopped-controller checks, settings preservation and rollback.
- `deploy-preserving-owner.py` — update an existing stopped persistent installation without starting it or resetting settings.
- `install-auto-pairing.py` — install/verify the widget's native pairing package; check its options before using it. Installation and shell reload are owner actions.
- `diagnose-pairing-owner.py` — owner-session pairing diagnostics.
- `comfy-owner.py`, `install-comfy-service.py` — managed Comfy maintenance/setup. **The service installer still invokes legacy rollout code; it is not the settings-preserving controller update path.**

Read [deployment](../docs/deployment.md) before owner actions. Do not run these as root or against another account's session.

## Development utilities

- `holiday-preview.py` — inspect calendar styling offline.
- `composition-samples.py` — generate frozen-fixture prompt samples; output is not a live weather observation or generated-image proof.
- `verify_desktop.py` — older test wrapper; prefer the complete isolated CI path for release validation.

## Legacy owner helpers: retained, not recommended for updates

`connect-owner.py`, `rollout-owner.py`, `release-owner.py`, `runtime-repair-owner.py`, `recover-dp2-owner.py` and `reconcile-dp2-owner.py` contain older connection, transient rollout, diagnostics and site-specific DP-2 recovery workflows. Some force Auto off; some can render or mutate state when explicitly requested. Do not treat them as generic installation instructions.

They are not all dead code: `install-comfy-service.py` and `recover-dp2-owner.py` depend on `rollout-owner.py`, and recovery uses `reconcile-dp2-owner.py`. Their contracts still have regression tests. Retiring this group requires a separate migration of those workflows, not merely deleting scripts and their tests.

## Removed creation-time leftovers

The cleanup removed unreferenced, snapshot-specific tools:

- `closure_receipt.py`: depended on old process IDs, one exact Git index hash and the old preview service.
- `live_receipt.py`: expected the old preview token directory/service and an unconfigured location.
- `smoke-release.py`: hard-coded version 0.1.6; current CLI/authentication behavior is covered by the test suite.
- `verify_connection_current.py`: required a particular installed checkpoint/widget and a pre-existing test log; not a portable verifier.
- `tests/kconfig-readback.cpp`: standalone exploratory probe, never part of the maintained build/test targets.

Their source remains recoverable from Git history. No collected regression tests or runtime modules were removed.
