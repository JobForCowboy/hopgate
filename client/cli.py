"""hopgate CLI: hopgate on|off|status [agent]."""
import argparse

import core


def main() -> None:
    ap = argparse.ArgumentParser(prog="hopgate", description="Route AI agents through the hopgate proxy.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("on", "off", "status"):
        p = sub.add_parser(cmd)
        p.add_argument("agent", nargs="?", help="claude-code | codex | desktop (default: all)")
    args = ap.parse_args()

    if args.cmd == "status":
        for name, st in core.status(args.agent).items():
            mark = {True: "ON ", False: "off", None: " - "}[st]
            print(f"  [{mark}] {name}")
        return

    if args.cmd == "on":
        done = core.enable(args.agent)
        verb = "routed through hopgate"
    else:
        done = core.disable(args.agent)
        verb = "restored to direct"

    for n in done:
        print(f"  {n}: {verb}")
    if done:
        print("Restart the agent(s) to pick up the change.")


if __name__ == "__main__":
    main()
