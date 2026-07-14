"""Token store for hopgate proxy: issue / list / revoke / verify.

Tokens are shown once at creation; only their sha256 hashes are stored.
"""
import hashlib
import hmac
import json
import os
import secrets
import sys
from pathlib import Path

STORE = Path(os.environ.get("HOPGATE_TOKENS", "tokens.json"))


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _load() -> dict[str, str]:
    if not STORE.exists():
        return {}
    return json.loads(STORE.read_text())


def _save(data: dict[str, str]) -> None:
    STORE.write_text(json.dumps(data, indent=2))
    os.chmod(STORE, 0o600)


def new(label: str) -> str:
    data = _load()
    if label in data:
        raise SystemExit(f"label {label!r} already exists")
    token = secrets.token_urlsafe(24)
    data[label] = _hash(token)
    _save(data)
    return token


def revoke(label: str) -> None:
    data = _load()
    if data.pop(label, None) is None:
        raise SystemExit(f"no such label: {label!r}")
    _save(data)


def verify(token: str) -> str | None:
    """Return the label for a valid token, else None (constant-time compare)."""
    h = _hash(token)
    for label, stored in _load().items():
        if hmac.compare_digest(h, stored):
            return label
    return None


def _cli(argv: list[str]) -> None:
    match argv:
        case ["new", label]:
            print(new(label))
        case ["list"]:
            for label in _load():
                print(label)
        case ["revoke", label]:
            revoke(label)
        case _:
            raise SystemExit("usage: tokens.py new <label> | list | revoke <label>")


def _selfcheck() -> None:
    global STORE
    import tempfile
    STORE = Path(tempfile.mkdtemp()) / "t.json"
    t = new("laptop")
    assert verify(t) == "laptop"
    assert verify("wrong") is None
    revoke("laptop")
    assert verify(t) is None
    print("tokens selfcheck ok")


if __name__ == "__main__":
    if sys.argv[1:2] == ["selfcheck"]:
        _selfcheck()
    else:
        _cli(sys.argv[1:])
