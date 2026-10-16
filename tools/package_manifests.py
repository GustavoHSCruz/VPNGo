#!/usr/bin/env python3
"""Fill the AUR, Homebrew and Scoop templates for one release from its SHA256SUMS."""

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = {
    "PKGBUILD": ROOT / "packaging/aur/PKGBUILD",
    "vpngo.rb": ROOT / "packaging/homebrew/vpngo.rb",
    "vpngo.json": ROOT / "packaging/scoop/vpngo.json",
}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--version", required=True, help="release version without the leading v")
    cli.add_argument("--sums", type=Path, required=True, help="the release's SHA256SUMS file")
    cli.add_argument("--repository", default="GustavoHSCruz/VPNGo", help="GitHub owner/name")
    cli.add_argument("--out", type=Path, required=True, help="output directory")
    args = cli.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        cli.error("package managers only get stable versions such as 1.2.3")

    sums = {}
    for line in args.sums.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        sums[name.lstrip("*")] = digest
    values = {"@VERSION@": args.version, "@REPOSITORY@": args.repository}
    for system, suffix in (("linux", "tar.gz"), ("macos", "tar.gz"), ("windows", "zip")):
        name = f"vpngo-{args.version}-{system}.{suffix}"
        if name not in sums:
            raise SystemExit(f"{name} is not listed in {args.sums}.")
        values[f"@SHA256_{system.upper()}_{suffix.replace('.', '_').upper()}@"] = sums[name]

    args.out.mkdir(parents=True, exist_ok=True)
    for name, template in TEMPLATES.items():
        text = template.read_text(encoding="utf-8")
        for placeholder, value in values.items():
            text = text.replace(placeholder, value)
        leftover = re.findall(r"@[A-Z0-9_]+@", text)
        if leftover:
            raise SystemExit(f"{template} has unfilled placeholders: {', '.join(sorted(set(leftover)))}")
        (args.out / name).write_text(text, encoding="utf-8")
    print(f"Wrote {', '.join(TEMPLATES)} for vpngo {args.version} in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
