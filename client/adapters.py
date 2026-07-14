"""Per-agent config adapters. Each toggles proxy settings for one AI agent.

An adapter exposes enable(proxy_url) / disable() / status() -> bool|None.
claude-code and desktop are implemented; codex is a stub for later.
"""
import json
import os
import signal
import subprocess
import sys
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


class ClaudeDesktop:
    """Route Claude Desktop (Electron) via a local shim.

    Chromium's --proxy-server can't send Basic proxy auth silently, so we point
    Desktop at a no-auth loopback shim (shim.py) that injects the token. We add
    the flag through a user-level .desktop override that shadows the system one,
    and run the shim as a detached background process.

    Runs on the HOST (shim + Desktop share loopback) — not inside the container.
    """
    name = "desktop"
    SHIM_ADDR = "127.0.0.1:8899"
    MARKER = "X-Hopgate=true"

    SYSTEM_LAUNCHERS = (
        Path("/usr/share/applications/com.anthropic.Claude.desktop"),
        Path("/usr/local/share/applications/com.anthropic.Claude.desktop"),
    )

    def __init__(self, override_dir: Path | None = None, system_launcher: Path | None = None):
        self.override_dir = override_dir or (Path.home() / ".local" / "share" / "applications")
        self._system = system_launcher
        self.pidfile = Path.home() / ".config" / "hopgate" / "shim.pid"

    def _system_launcher(self) -> Path | None:
        if self._system is not None:
            return self._system
        return next((p for p in self.SYSTEM_LAUNCHERS if p.exists()), None)

    @property
    def override(self) -> Path:
        name = (self._system_launcher() or Path("com.anthropic.Claude.desktop")).name
        return self.override_dir / name

    def enable(self, proxy_url: str) -> None:
        src = self._system_launcher()
        if src is None:
            raise FileNotFoundError("Claude Desktop launcher not found")
        if self.override.exists() and self.MARKER not in self.override.read_text():
            raise SystemExit(f"refusing to overwrite your own override: {self.override}")

        flag = f"--proxy-server=http://{self.SHIM_ADDR}"
        text = src.read_text().replace("Exec=claude-desktop", f"Exec=claude-desktop {flag}")
        text = text.replace("[Desktop Entry]\n", f"[Desktop Entry]\n{self.MARKER}\n", 1)
        self.override.parent.mkdir(parents=True, exist_ok=True)
        self.override.write_text(text)

        self._start_shim()

    def disable(self) -> None:
        if self.override.exists() and self.MARKER in self.override.read_text():
            self.override.unlink()
        self._stop_shim()

    def status(self) -> bool | None:
        if self._system_launcher() is None:
            return None
        return self.override.exists() and self.MARKER in self.override.read_text()

    # --- shim process lifecycle ---
    def _start_shim(self) -> None:
        if self._shim_alive():
            return
        shim = Path(__file__).parent / "shim.py"
        log = open(Path.home() / ".config" / "hopgate" / "shim.log", "a")
        proc = subprocess.Popen(
            [sys.executable, str(shim), "--listen", self.SHIM_ADDR],
            stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            start_new_session=True,  # detach so it survives the CLI exiting
        )
        self.pidfile.parent.mkdir(parents=True, exist_ok=True)
        self.pidfile.write_text(str(proc.pid))

    def _stop_shim(self) -> None:
        if not self.pidfile.exists():
            return
        try:
            os.kill(int(self.pidfile.read_text()), signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass
        self.pidfile.unlink(missing_ok=True)

    def _shim_alive(self) -> bool:
        if not self.pidfile.exists():
            return False
        try:
            os.kill(int(self.pidfile.read_text()), 0)
            return True
        except (ProcessLookupError, ValueError):
            return False


class _Stub:
    def __init__(self, name: str):
        self.name = name

    def _fail(self):
        raise NotImplementedError(
            f"{self.name} adapter not implemented yet. "
            f"TODO: {self.name} routes proxy via env vars / config.toml."
        )

    enable = disable = status = lambda self, *a: self._fail()


def registry() -> dict[str, object]:
    return {
        "claude-code": ClaudeCode(),
        "codex": _Stub("codex"),
        "desktop": ClaudeDesktop(),
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

    # ClaudeDesktop: exercise the .desktop override rewrite (skip shim process).
    tmp = Path(tempfile.mkdtemp())
    sysfile = tmp / "sys" / "com.anthropic.Claude.desktop"
    sysfile.parent.mkdir(parents=True)
    sysfile.write_text("[Desktop Entry]\nName=Claude\nExec=claude-desktop %U\n")
    d = ClaudeDesktop(override_dir=tmp / "apps", system_launcher=sysfile)
    d._start_shim = lambda: None  # don't spawn a real shim in the selfcheck
    d._stop_shim = lambda: None
    assert d.status() is False
    d.enable("unused")
    ov = d.override.read_text()
    assert "--proxy-server=http://127.0.0.1:8899" in ov
    assert "X-Hopgate=true" in ov
    assert d.status() is True
    d.disable()
    assert not d.override.exists()
    assert d.status() is False
    print("adapters selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
