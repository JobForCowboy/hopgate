# hopgate

A tiny personal jump-host proxy for AI coding agents (Claude Code, Claude Desktop, Codex).

## Problem

Corporate networks often block direct access to LLM APIs. The usual workaround — a VPN to an approved gateway — breaks access to other internal resources, forcing constant toggling.

## Idea

- **Server**: a minimal proxy running on a corporate-approved host that *does* have access to the LLM APIs.
- **Client**: a small utility with per-agent toggles that rewrites the configs of Claude Code / Claude Desktop / Codex to route their API traffic through the jump host instead of connecting directly — and restores them back with one click.

No VPN juggling: only LLM API traffic goes through the hop, everything else stays on the normal network.

## Disclaimer / Acceptable use

hopgate is a personal network-routing tool. You use it with **your own** API keys or subscription to reach services you are already entitled to use, through a host your organization permits.

It is **not** for:
- sharing one account or subscription between multiple users;
- circumventing vendor licensing, rate limits, or terms of service;
- accessing services you are not authorized to use.

Make sure routing traffic this way complies with your employer's network policy and the terms of service of the AI vendors you use.

## How it works

The proxy is a minimal HTTP `CONNECT` tunnel. It only accepts connections that
present a valid token and only tunnels to **allowlisted hosts on port 443**.
Because `CONNECT` traffic stays end-to-end TLS, the proxy never sees request
bodies or your API keys — it sees only `host:443`. The token travels in the
`Proxy-Authorization` header; even if it leaked, the allowlist means it can only
reach the same LLM APIs, never become an open relay. Tokens are revocable.

## Server (on the jump host)

```bash
cd server
python3 tokens.py new laptop        # prints a token once — copy it into the client config
docker compose up -d --build        # listens on :8443
```

Edit `server/allowlist.txt` to control which destinations are permitted (Anthropic
and OpenAI hosts are included by default). Manage tokens with
`python3 tokens.py list | revoke <label>`.

## Client (on your machine)

Create `~/.config/hopgate/config.toml`:

```toml
host = "jump.corp.example"
port = 8443
token = "the-token-from-the-server"
label = "laptop"
```

Then toggle agents. Either run the CLI directly:

```bash
cd client
python3 cli.py status
python3 cli.py on claude-code     # rewrites ~/.claude/settings.json env to use the proxy
python3 cli.py off                # restores every agent to direct
```

…or via Docker (mounts your host config dirs):

```bash
docker compose run --rm hopgate on claude-code
```

Restart the agent after toggling so it picks up the new proxy setting.

**Agent support:** Claude Code works today. Codex and Claude Desktop route via
environment variables rather than a single config file — their adapters are
stubbed and coming next. Client currently targets Linux hosts.

## Status

Working MVP: server proxy + Claude Code client toggle. Codex/Desktop adapters and
a browser GUI are next.

## License

[MIT](LICENSE)
