"""hopgate — minimal HTTP CONNECT proxy for LLM APIs.

Only tunnels CONNECT to allowlisted hosts on port 443, and only for clients
presenting a valid token via Proxy-Authorization. The tunnelled traffic stays
end-to-end TLS: the proxy never sees request bodies or API keys.
"""
import argparse
import asyncio
import base64
import logging
import os
from pathlib import Path

import tokens

log = logging.getLogger("hopgate")

ALLOWLIST = Path(os.environ.get("HOPGATE_ALLOWLIST", "allowlist.txt"))


def load_allowlist() -> tuple[set[str], list[str]]:
    """Return (exact hosts, suffixes). '.foo.com' entries become suffixes."""
    exact, suffixes = set(), []
    for line in ALLOWLIST.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("."):
            suffixes.append(line)
        else:
            exact.add(line)
    return exact, suffixes


def host_allowed(host: str, exact: set[str], suffixes: list[str]) -> bool:
    if host in exact:
        return True
    return any(host == s[1:] or host.endswith(s) for s in suffixes)


def _extract_token(headers: dict[str, str]) -> str | None:
    auth = headers.get("proxy-authorization", "")
    if not auth.lower().startswith("basic "):
        return None
    try:
        userpass = base64.b64decode(auth[6:]).decode()
    except Exception:
        return None
    # Client sends label:token; we only care about the token part.
    return userpass.split(":", 1)[-1]


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    # ponytail: naive one-direction copy; add backpressure handling if throughput matters.
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def handle(client_r: asyncio.StreamReader, client_w: asyncio.StreamWriter) -> None:
    peer = client_w.get_extra_info("peername")
    try:
        # Auth loop: a client (e.g. curl) may send an unauthenticated CONNECT,
        # get a 407 challenge, then retry with the token on the same connection.
        while True:
            request_line = await client_r.readline()
            if not request_line:
                return
            parts = request_line.decode(errors="replace").split()
            if len(parts) != 3 or parts[0] != "CONNECT":
                await _reply(client_w, 400, "Bad Request")
                return
            target = parts[1]

            headers = {}
            while (line := await client_r.readline()) not in (b"\r\n", b"\n", b""):
                k, _, v = line.decode(errors="replace").partition(":")
                headers[k.strip().lower()] = v.strip()

            token = _extract_token(headers)
            label = tokens.verify(token) if token else None
            if label is not None:
                break
            await _reply(client_w, 407, "Proxy Authentication Required",
                         extra='Proxy-Authenticate: Basic realm="hopgate"\r\n'
                               "Connection: keep-alive\r\n")
            log.info("407 no/invalid token from %s -> %s", peer, target)

        host, _, port = target.rpartition(":")
        exact, suffixes = load_allowlist()
        if port != "443" or not host_allowed(host, exact, suffixes):
            await _reply(client_w, 403, "Forbidden")
            log.info("403 [%s] blocked %s", label, target)
            return

        try:
            up_r, up_w = await asyncio.open_connection(host, 443)
        except OSError:
            await _reply(client_w, 502, "Bad Gateway")
            log.info("502 [%s] upstream fail %s", label, target)
            return

        await _reply(client_w, 200, "Connection Established")
        log.info("200 [%s] tunnel %s", label, target)
        await asyncio.gather(_pipe(client_r, up_w), _pipe(up_r, client_w))
    except Exception as e:
        log.warning("error handling %s: %s", peer, e)
        client_w.close()


async def _reply(w: asyncio.StreamWriter, code: int, msg: str, extra: str = "") -> None:
    w.write(f"HTTP/1.1 {code} {msg}\r\n{extra}\r\n".encode())
    try:
        await w.drain()
    except ConnectionError:
        pass


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", default=":8443", help="[host]:port to listen on")
    args = ap.parse_args()
    host, _, port = args.listen.rpartition(":")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    server = await asyncio.start_server(handle, host or "0.0.0.0", int(port))
    log.info("hopgate listening on %s", args.listen)
    async with server:
        await server.serve_forever()


def _selfcheck() -> None:
    exact, suffixes = {"api.anthropic.com"}, [".anthropic.com"]
    assert host_allowed("api.anthropic.com", exact, suffixes)
    assert host_allowed("foo.anthropic.com", exact, suffixes)
    assert host_allowed("anthropic.com", exact, suffixes)  # ".anthropic.com" covers apex
    assert not host_allowed("evil.com", exact, suffixes)
    assert not host_allowed("notanthropic.com", exact, suffixes)
    print("proxy selfcheck ok")


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["selfcheck"]:
        _selfcheck()
    else:
        asyncio.run(main())
