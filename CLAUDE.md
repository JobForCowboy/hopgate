# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

hopgate lets a developer reach LLM APIs (Anthropic, OpenAI) from inside a corporate
network that blocks them directly, by tunnelling through a company-approved jump
host — **for personal use only** (your own keys/subscription, never account sharing
or ToS circumvention). Two parts: a proxy on the jump host (`server/`) and a client
that toggles local AI agents' configs to route through it (`client/`).

## Commands

No build step, no dependencies — pure Python 3.12 stdlib (`tomllib`, `asyncio`).

```bash
# Self-checks (each module has its own; run after changing that module)
python3 server/proxy.py selfcheck      # allowlist matching
python3 server/tokens.py selfcheck     # issue -> verify -> revoke
python3 client/adapters.py             # claude-code + desktop adapter round-trips

# Server (on the jump host)
python3 server/tokens.py new <label>   # prints a token ONCE, stores only its sha256
python3 server/tokens.py list | revoke <label>
cd server && docker compose up -d --build   # proxy on :8443

# Client (on your machine; needs ~/.config/hopgate/config.toml)
python3 client/cli.py on|off|status [claude-code|codex|desktop]
```

There is no test framework — verification is the per-module `selfcheck`/`__main__`
blocks plus manual end-to-end curl. New non-trivial logic should extend the
relevant module's `_selfcheck()` with an `assert`, not add a framework.

### Manual end-to-end check

```bash
python3 server/proxy.py --listen :8901 &            # start proxy
TOKEN=$(python3 server/tokens.py new laptop)
curl -x "http://laptop:$TOKEN@localhost:8901" https://api.anthropic.com/v1/models  # 401 from API = tunnel OK
curl -x "http://laptop:$TOKEN@localhost:8901" https://example.com                  # 403 = allowlist blocks
```

## Architecture

**Security model (do not weaken):** the proxy is HTTP `CONNECT`-only, so tunnelled
traffic stays end-to-end TLS — it never sees API keys, only `host:443`. Two hard
limits keep a leaked token from becoming an open relay: destination must be in
`server/allowlist.txt`, and port must be 443. Both checks live in
`server/proxy.py:handle`. Tokens are stored as sha256 hashes and compared with
`hmac.compare_digest`.

**Client is UI-agnostic on purpose.** `client/core.py` holds all logic (enable/
disable/status per agent); `client/cli.py` is a thin argparse shell over it. A future
web GUI is meant to be another thin layer over `core.py` — keep logic out of the
entry points.

**Adapters** (`client/adapters.py`) exist because each agent wires up a proxy
differently; each exposes `enable(proxy_url)` / `disable()` / `status()`:
- `ClaudeCode` — edits `env.HTTPS_PROXY`/`HTTP_PROXY` in `~/.claude/settings.json`.
  Uses a `_hopgate` marker key to remember the user's prior values and restore them
  exactly on disable, never clobbering their own proxy settings.
- `ClaudeDesktop` — Electron/Chromium can't send Basic proxy auth silently, so this
  runs `client/shim.py` (a no-auth loopback CONNECT proxy that injects the token and
  forwards to the jump host) and writes a **user-level** `.desktop` override adding
  `--proxy-server=http://127.0.0.1:8899`. It never touches the root-owned system
  launcher. Marker: `X-Hopgate=true`. **This path only works on the host**, not in
  the client container — the shim and Desktop must share loopback.
- `codex` — stub (`_Stub`), raises `NotImplementedError`.

**The two Docker setups differ:** `server/` runs the proxy on the jump host;
`client/` mounts host config dirs (`~/.claude`, `~/.config/hopgate`) so a container
can edit them. The desktop adapter is the exception — run it directly on the host.

## Gotchas

- `pkill -f 'proxy.py …'` will kill your own shell (the pattern matches the pkill
  command's own line). Use the bracket trick: `pkill -f '[p]roxy.py'`.
- Claude Desktop is single-instance; a second launch just focuses the existing
  window. To test proxy routing, kill the running instance first and launch a test
  one with a separate `--user-data-dir`.

## Never commit

`server/tokens.json` and any `config.toml` (real tokens live there) — both are
already in `.gitignore`.
