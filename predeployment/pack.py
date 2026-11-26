"""Pack the kit folder into the one file to carry into the network (dist/cpc-<version>.tar.gz), called by build.ps1.

Python's tarfile rather than Windows tar, so the archive carries Linux permissions whatever the build machine: every
*.sh executable (0755, so `./install.sh` runs straight after `tar -xzf`), other files 0644, folders 0755, owner root.

    python predeployment/pack.py dist/cpc-<version> dist/cpc-<version>.tar.gz
"""
from __future__ import annotations

import sys
import tarfile
import time
from pathlib import Path


def pack(stage: Path, archive: Path) -> None:
    stamp = int(time.time())

    def normalise(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        info.mtime = stamp
        info.mode = 0o755 if info.isdir() or info.name.endswith(".sh") else 0o644
        return info

    with tarfile.open(archive, "w:gz", compresslevel=6) as tar:
        tar.add(stage, arcname=stage.name, filter=normalise)  # entries in sorted order


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: pack.py <kit folder> <archive.tar.gz>")
    pack(Path(sys.argv[1]), Path(sys.argv[2]))
