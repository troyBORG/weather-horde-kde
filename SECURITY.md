# Security

The controller is a local authenticated service, not an Internet-facing server. Keep its loopback binding, token checks and request-origin protections. The native QML helper reads only the same user's private token under validated ownership/permissions. Do not forward the service externally, share tokens, execute as root or borrow another user's D-Bus session.

Owner installers, model/queue identity checks, render safety and transactional wallpaper readback are security boundaries. Unknown state should fail closed. Testing override is explicit, bounded consent, not a bypass for ownership or malformed inputs.

Before reporting a bug, remove tokens, settings/location, usernames, home/mount paths, process arguments, image metadata, activity identifiers and private desktop screenshots. Provide a synthetic reproducer and reviewed source revision instead of raw state archives. Do not post a vulnerability containing credentials in a public issue. No dedicated private reporting address has been approved yet; ask the maintainer for a private channel before sharing sensitive details.

No security audit certification is claimed. Secret scanning cannot establish that source contains no personal information. Owner selection and Comfy paths are explicit deployment configuration; review them as executable-code trust decisions. Geographic defaults and legacy recovery targets are not changed by path portability.
