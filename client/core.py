"""hopgate client core: turn agents' proxy routing on/off.

Kept UI-agnostic so a CLI now and a web UI later share the same logic.
"""
import tomllib
from pathlib import Path

import adapters

CONFIG = Path.home() / ".config" / "hopgate" / "config.toml"


def proxy_url() -> str:
    """Build the proxy URL clients point at, from the client config file."""
    if not CONFIG.exists():
        raise SystemExit(f"missing config: {CONFIG}\n"
                         "create it with host/port/token/label (see README).")
    cfg = tomllib.loads(CONFIG.read_text())
    label = cfg.get("label", "client")
    return f"http://{label}:{cfg['token']}@{cfg['host']}:{cfg['port']}"


def _agents(name: str | None) -> dict[str, object]:
    reg = adapters.registry()
    if name is None:
        return reg
    if name not in reg:
        raise SystemExit(f"unknown agent: {name}. known: {', '.join(reg)}")
    return {name: reg[name]}


def enable(name: str | None = None) -> list[str]:
    url = proxy_url()
    done = []
    for n, a in _agents(name).items():
        try:
            a.enable(url)
            done.append(n)
        except NotImplementedError as e:
            print(f"  skip {n}: {e}")
    return done


def disable(name: str | None = None) -> list[str]:
    done = []
    for n, a in _agents(name).items():
        try:
            a.disable()
            done.append(n)
        except NotImplementedError as e:
            print(f"  skip {n}: {e}")
    return done


def status(name: str | None = None) -> dict[str, bool | None]:
    out = {}
    for n, a in _agents(name).items():
        try:
            out[n] = a.status()
        except NotImplementedError:
            out[n] = None
    return out
