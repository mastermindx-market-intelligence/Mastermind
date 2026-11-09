# Installed Linux picker source snapshot — test evidence only

`linux_ubuntu03_pick_preimage.py.txt` is a byte-for-byte source snapshot
(SHA-256 `bab2bcc1d71d7b8b2a7d5b78247326d5057815c6ed063143c451990b577e13d8`)
read from the 2026-11-04 installed Ubuntu0/Ubuntu3 Fabric selector
`~/lanes/ext/pick.py`. It contains code, not provider credentials, host
entitlement documents, settings, ledger, queue or account readbacks. The
`.txt` suffix makes it a non-executable test fixture; it is not the canonical
source or a deployable native release.

`../qualify_linux_installed_picker.py` refuses any installed preimage other
than this exact source identity. A different Ubuntu1 picker
(`957b05438170c3e1205d3ea6637241a5b90750b1ea7cf2da93867a659c36714b`)
is explicitly not qualified by this profile. Reread the actual installed
generation and qualify disjoint changes through the existing native
generation publisher before applying anything to that host.

The transform is source-only, preserves the incumbent selector code and
provides a manual-only `pool=experiential` +
`model=glm-5.3-uncensored` path that remains dark without fresh native-owner
witnesses. It never installs a selector, touches a key, or executes a worker.
