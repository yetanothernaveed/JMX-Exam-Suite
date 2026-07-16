# jmx

A minimal CLI (`jmx`) + privileged background daemon (`jmxd`) pair,
talking over a Unix domain socket. `jmx hello` is the first command;
the design leaves room to add more without restructuring anything.

## Architecture

```
 firejail sandbox                    system (higher privilege)
┌─────────────────┐                 ┌───────────────────────────┐
│  jmx hello       │  AF_UNIX       │  jmxd (systemd service)    │
│  (unprivileged)  │ ───────────►   │  listens on                │
│                  │ ◄───────────   │  /run/jmx/jmx.sock         │
└─────────────────┘   "Hi!"         └───────────────────────────┘
```

- **Transport**: `SOCK_STREAM` Unix domain socket at `/run/jmx/jmx.sock`.
  Chosen over TCP/loopback because it's filesystem-permission-based
  (no port to scan or firewall to misconfigure) and unaffected by
  firejail's network restrictions (`--net=none` etc. only touch
  `AF_INET`/`AF_INET6`, not `AF_UNIX`).
- **Wire protocol**: 4-byte big-endian length prefix + UTF-8 payload,
  both directions (see `src/common.hpp`). Deliberately simple, but
  framed properly so it won't break the moment a command needs to
  return more than one line.
- **Daemon**: single-threaded accept loop, allowlist-dispatches on the
  literal command string (`handleCommand()` in `src/daemon.cpp`). Logs
  every connecting peer's real uid/gid/pid via `SO_PEERCRED` — this is
  the hook to add authorization checks once commands do more than say
  hello.
- **Client**: connects, sends the command, prints whatever comes back,
  exits non-zero on error or unknown command.
- **Process supervision**: systemd, not a hand-rolled fork-daemonize —
  gives you auto-restart, logging via journald, and a `RuntimeDirectory`
  that's created/cleaned automatically.

### Why not just run commands as root directly from the CLI (e.g. via sudo)?

Because the CLI runs inside firejail as an unprivileged, sandboxed
process — that's the point of the sandbox. The daemon is the one
process that's trusted to cross the privilege boundary, and it only
crosses it for the exact, hardcoded set of operations you implement in
`handleCommand()`. Keep that function as a strict allowlist; never let
it build a shell command or file path from client-supplied text.

## Build

```
cmake -S . -B build
cmake --build build
```

(Or directly: `g++ -std=c++17 -O2 -o jmxd src/daemon.cpp` and the same
for `src/client.cpp` → `jmx`.)

## Step-by-step: installing jmxd as a persistent privileged service

1. **Install the binaries**

   ```
   sudo cmake --install build
   # or manually:
   sudo install -m 755 build/jmxd /usr/local/bin/jmxd
   sudo install -m 755 build/jmx  /usr/local/bin/jmx
   ```

2. **Create a dedicated group for socket access** (recommended instead
   of leaving the socket world-writable). Add every user who should be
   able to run `jmx` commands to it:

   ```
   sudo groupadd --system jmx
   sudo usermod -aG jmx <username>
   ```

   The user will need to log out/in (or run `newgrp jmx`) for the
   group membership to take effect. `jmxd` checks for this group at
   startup and, if present, sets the socket to `root:jmx 0660`; if the
   group doesn't exist it falls back to `root:root 0600` (root-only).

3. **Install the systemd unit**

   ```
   sudo cp systemd/jmxd.service /etc/systemd/system/jmxd.service
   sudo systemctl daemon-reload
   ```

4. **Enable and start it**

   ```
   sudo systemctl enable --now jmxd
   sudo systemctl status jmxd
   ```

   `enable` makes it start on every boot; `Restart=on-failure` in the
   unit makes it come back if it ever crashes. It keeps running
   regardless of which unprivileged user is logged in or logged out —
   it's a system service, not tied to any user session.

5. **Check the logs**

   ```
   journalctl -u jmxd -f
   ```

   You should see `starting, listening on /run/jmx/jmx.sock`, and a
   `connection from uid=... gid=... pid=...` line each time `jmx` is run.

6. **Test from an unprivileged shell**

   ```
   jmx hello
   # Hi!
   ```
## To build using CMake presets
    ```
    cmake --workflow --preset ci-install
    ```


## Running the CLI from inside firejail

Two things to check the first time you wire this into a firejail
profile:

- **The user must be in the `jmx` group** (step 2 above) *before*
  firejail starts, since firejail inherits the launching process's
  credentials — it doesn't grant new group membership.
- **`/run/jmx` must be visible inside the sandbox.** Most default
  firejail profiles don't privatize `/run`, so this generally works
  out of the box. If your profile is more restrictive (custom
  `blacklist`/`private` directives touching `/run`), whitelist it
  explicitly:

  ```
  firejail --whitelist=/run/jmx jmx hello
  ```

  or add `whitelist /run/jmx` to the sandbox's `.profile` file. Unix
  domain sockets aren't affected by `--net=none`, `--netfilter`, or
  other network-layer restrictions, so you don't need to poke any
  holes in those for this to work.

## Extending beyond `hello`

- Add new branches to `handleCommand()` in `src/daemon.cpp` — keep it
  an explicit allowlist, not a generic dispatcher.
- Use the logged `SO_PEERCRED` uid to decide per-user authorization if
  different users should be allowed different commands.
- If a command needs arguments, extend the wire format (e.g. send
  `"copy_file\nsrc\ndst"` or switch the payload to a small JSON object)
  rather than parsing free-form text — validate every field strictly on
  the daemon side, and never pass client-supplied strings to
  `system()`/`popen()`/`exec*()` with a shell.
- If you outgrow the single-threaded accept loop (slow commands
  blocking others), hand each accepted `fd` off to a thread or a
  `fork()`'d child instead of processing inline.
