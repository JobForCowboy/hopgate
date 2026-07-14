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

## Status

Early design stage. No code yet.

## License

[MIT](LICENSE)
