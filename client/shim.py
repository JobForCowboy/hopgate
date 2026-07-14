"""Local CONNECT shim for Chromium/Electron apps (Claude Desktop).

Chromium's --proxy-server can't silently send Basic proxy auth, so the app
points at this no-auth loopback proxy instead. The shim injects the hopgate
token and forwards each CONNECT to the real upstream proxy.

Binds 127.0.0.1 only — it must never be reachable off the local machine.
"""
import argparse
import asyncio
import base64
import tomllib
from pathlib import Path

CONFIG = Path.home() / ".config" / "hopgate" / "config.toml"


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    # ponytail: naive copy, same as server/proxy.py; fine for loopback.
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


def _auth_header(label: str, token: str) -> str:
    cred = base64.b64encode(f"{label}:{token}".encode()).decode()
    return f"Proxy-Authorization: Basic {cred}\r\n"


async def _drain_headers(reader: asyncio.StreamReader) -> None:
    while (line := await reader.readline()) not in (b"\r\n", b"\n", b""):
        pass


def make_handler(up_host: str, up_port: int, auth: str):
    async def handle(cli_r, cli_w):
        try:
            request_line = await cli_r.readline()
            parts = request_line.decode(errors="replace").split()
            if len(parts) != 3 or parts[0] != "CONNECT":
                cli_w.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                await cli_w.drain()
                cli_w.close()
                return
            target = parts[1]
            await _drain_headers(cli_r)

            up_r, up_w = await asyncio.open_connection(up_host, up_port)
            up_w.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n{auth}\r\n".encode())
            await up_w.drain()

            status = await up_r.readline()
            await _drain_headers(up_r)
            if b" 200 " not in status:
                cli_w.write(status or b"HTTP/1.1 502 Bad Gateway\r\n")
                cli_w.write(b"\r\n")
                await cli_w.drain()
                cli_w.close()
                up_w.close()
                return

            cli_w.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await cli_w.drain()
            await asyncio.gather(_pipe(cli_r, up_w), _pipe(up_r, cli_w))
        except Exception:
            cli_w.close()

    return handle


def _from_config() -> tuple[str, int, str]:
    cfg = tomllib.loads(CONFIG.read_text())
    return cfg["host"], int(cfg["port"]), _auth_header(cfg.get("label", "client"), cfg["token"])


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", default="127.0.0.1:8899")
    args = ap.parse_args()
    host, _, port = args.listen.rpartition(":")
    up_host, up_port, auth = _from_config()

    server = await asyncio.start_server(make_handler(up_host, up_port, auth), host, int(port))
    print(f"hopgate shim: {args.listen} -> {up_host}:{up_port}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
