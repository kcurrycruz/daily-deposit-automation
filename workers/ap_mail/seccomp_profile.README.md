# Container browser sandbox profile

`seccomp_profile.json` is the unchanged official Playwright v1.62.1 Docker
profile from:

https://raw.githubusercontent.com/microsoft/playwright/v1.62.1/utils/docker/seccomp_profile.json

SHA-256: `cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849`

Playwright documents this profile for Chromium sandboxing under a non-root
container user. It retains a default-deny syscall policy and permits the user
namespace operations Chromium needs. Container smoke also retains network
isolation, a read-only root filesystem and bounded temporary storage. The native
GitHub batch runner does not use Docker or this profile.

On Ubuntu native runners, use the preinstalled root-owned Google Chrome setuid
sandbox helper through `CHROME_DEVEL_SANDBOX`, as described by Chromium:

https://chromium.googlesource.com/chromium/src/+/HEAD/docs/security/apparmor-userns-restrictions.md

The workflow verifies its root owner and mode before use. It does not disable
AppArmor, change global kernel settings, or turn Chromium sandboxing off.
