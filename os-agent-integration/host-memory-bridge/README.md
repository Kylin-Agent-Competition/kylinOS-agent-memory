# Kylin AI Assistant Host Memory Integration (post-D15D RC)

This directory contains the **controlled Kylin V11 host-integration RC** proven on
Kylin AI Assistant 3.0.67. It is intentionally separate from the frozen D15D
release identity at `main@e62d525e`.

## What is proven

The Kylin V11 VM validation established this chain with the real packaged AI
Assistant binary (Build ID `409634237f8c49aa7d235932804a4febf80cb8b3`, SHA-256
`86453fc660a47940c26031d87807cc735ea1cfd628a657f34a5c896cb0c7ccf6`):

1. real Assistant Chat DB user behavior -> `host_memory_bridge.py`;
2. explicit project-language preference -> Memory Service `preference.*`;
3. `memory_context_sync.py` -> active/current context sidecar;
4. pre-chat hook -> real `OsAssistant::chatAsync(const std::string&)`;
5. model-only request augmentation; original UI/Chat DB user text remains unchanged;
6. a real ambiguous programming request selected the active Rust preference.

The compatibility bridge currently recognizes a deliberately small explicit
project-language grammar. It does **not** replace the repository's general
`event.ingest -> EventPipeline -> admission -> source_events` architecture and
must not be presented as the formal >=85% preference-extraction evaluation.

## Why the launcher is inside Kaiming

The real exported desktop entry is:

```text
/opt/kaiming-tools/bin/kaiming run --command=/usr/bin/kylin-aiassistant cn.kylin.kylin-aiassistant --
```

A VM probe showed that `kaiming run` filters arbitrary host environment
variables. A second VM probe showed that a command selected by `--command` can
run from the user's home inside the sandbox and can then set `LD_PRELOAD` and
load the hook successfully. Therefore the RC uses a small **inside-sandbox
wrapper**, not `sudo`, PID discovery, `nsenter`, or modification of the official
assistant ELF.

## User flow

After one install and one log-out/log-in cycle:

```text
login
  -> kylin-memory.service
  -> kylin-memory-host-bridge.service
  -> kylin-memory-context-sync.service
  -> XDG autostart override
  -> kaiming run --command=<inside-sandbox wrapper>
  -> wrapper sets LD_PRELOAD + runtime context path
  -> untouched /usr/bin/kylin-aiassistant --silence
```

The normal application-menu entry is also overridden at user scope, so manually
opening **AI Assistant** uses the same memory-enabled path.

## Install from a source checkout

Prerequisite: the D14A Memory Service release is already installed and
`~/.local/bin/kylin-memory-server` exists.

```bash
bash os-agent-integration/host-memory-bridge/install_host_integration_rc.sh
```

The source-checkout installer builds the C++ hook with `g++`. Before changing
the Assistant launch path it also verifies the exact validated Assistant SHA-256,
checks the hook ABI export, and runs a no-UI Kaiming probe that proves the
**installed** hook and runtime-context path are visible/loadable inside the
sandbox. A future release package should supply a prebuilt verified SO with
`KYLIN_MEMORY_PRECHAT_SO=...` so end users do not need a compiler.

The host bridge persists only an acknowledged Chat DB row cursor under the
user state directory. This is not memory content; it exists so a bridge restart
does not silently skip a preference row whose IPC write was interrupted. On a
first install the cursor is initialized to the current DB tail, so historical
chats are still not backfilled.

Then log out and log back in once and run:

```bash
bash os-agent-integration/host-memory-bridge/verify_host_integration_rc.sh --runtime
```

## Uninstall / rollback

```bash
bash os-agent-integration/host-memory-bridge/uninstall_host_integration_rc.sh
```

The installer backs up pre-existing user desktop/autostart/drop-in overrides on
the first install. Uninstall restores those files when present, otherwise it
removes the RC override and lets the system-level Kylin entries become active
again.

## Claim boundary

This is a **post-D15D competition RC / controlled real-host integration**. It is
not a claim that the frozen D15D package became `release_ready` or
`production_ready`, and it does not promote candidate preference/forget IPC
routes to the repository's default production registry. The installer activates
those routes through a reversible user-level systemd drop-in for this RC only.

## Failure semantics

For the validated Assistant ABI, memory **augmentation** is fail-open: when
runtime context is absent, the request shape is unsupported, or context cannot
be injected, the original request is forwarded unchanged to the real
`OsAssistant::chatAsync`.

ABI resolution is a separate safety boundary. If the downstream
`chatAsync` symbol cannot be resolved with `RTLD_NEXT`, the hook records
`ABI_FAIL_CLOSED real-chatAsync-not-found` and does not attempt an unsafe call
through an unknown ABI. The installer therefore verifies both the exact
validated Assistant SHA-256 and the downstream `libkyai-assistant` symbol before
activating the user-scoped integration.

Accordingly, this RC claims **augmentation fail-open on the validated ABI**,
not unconditional fail-open under arbitrary Assistant binary/library drift.
