"""Per-agent config adapters. Each toggles proxy settings for one AI agent.

An adapter exposes enable(proxy_url) / disable() / status() -> bool|None.
Only claude-code is implemented; codex and desktop are stubs for later.
"""
import json
from pathlib import Path

# Marker so we only touch keys we added, never a user's own proxy settings.
MARKER = "_hopgate"


class ClaudeCode:
    name = "claude-code"

    def __init__(self, settings_path: Path | None = None):
        self.path = settings_path or (Path.home() / ".claude" / "settings.json")

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text() or "{}")

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2) + "\n")

    def enable(self, proxy_url: str) -> None:
        data = self._load()
        env = data.setdefault("env", {})
        if MARKER not in data:
            # Remember what was there so disable() can restore exactly.
            data[MARKER] = {k: env.get(k) for k in ("HTTPS_PROXY", "HTTP_PROXY")}
        env["HTTPS_PROXY"] = proxy_url
        env["HTTP_PROXY"] = proxy_url
        self._save(data)

    def disable(self) -> None:
        data = self._load()
        saved = data.pop(MARKER, None)
        env = data.get("env", {})
        for k in ("HTTPS_PROXY", "HTTP_PROXY"):
            prev = (saved or {}).get(k)
            if prev is None:
                env.pop(k, None)
            else:
                env[k] = prev
        if env == {}:
            data.pop("env", None)
        self._save(data)

    def status(self) -> bool | None:
        """True=on via hopgate, False=off, None=agent not configured/installed."""
        if not self.path.exists():
            return None
        return MARKER in self._load()


class _Stub:
    def __init__(self, name: str):
        self.name = name

    def _fail(self):
        raise NotImplementedError(
            f"{self.name} adapter not implemented yet. "
            f"TODO: {self.name} routes proxy via env vars, not a single config file."
        )

    enable = disable = status = lambda self, *a: self._fail()


def registry() -> dict[str, object]:
    return {
        "claude-code": ClaudeCode(),
        "codex": _Stub("codex"),
        "desktop": _Stub("desktop"),
    }


def _selfcheck() -> None:
    import tempfile
    p = Path(tempfile.mkdtemp()) / "settings.json"
    # Pre-existing user settings with an unrelated key and a real HTTP_PROXY.
    p.write_text(json.dumps({"model": "x", "env": {"HTTP_PROXY": "http://corp:1"}}))
    a = ClaudeCode(p)
    assert a.status() is False
    a.enable("http://laptop:tok@jump:8443")
    d = json.loads(p.read_text())
    assert d["env"]["HTTPS_PROXY"] == "http://laptop:tok@jump:8443"
    assert a.status() is True
    a.disable()
    d = json.loads(p.read_text())
    assert d["model"] == "x"                       # untouched
    assert d["env"]["HTTP_PROXY"] == "http://corp:1"  # restored, not deleted
    assert "HTTPS_PROXY" not in d["env"]           # ours removed
    assert a.status() is False
    print("adapters selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
