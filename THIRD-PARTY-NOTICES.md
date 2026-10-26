# Third-party notices

Fallout 2 Co-op Manager is an independent launcher. It is not affiliated with
Bethesda, Interplay, Black Isle Studios, Valve, Nord Security, or the upstream
co-op projects.

## Co-op engine bundled in Windows releases

The release package includes the **unmodified** Windows executables and notices
from [gusmarcum/fallout2-coop v1.4.3](https://github.com/gusmarcum/fallout2-coop/releases/tag/v1.4.3).
That project derives from [Cahb/fallout2-ce-coop v0.4](https://github.com/Cahb/fallout2-ce-coop)
and [Fallout 2 Community Edition](https://github.com/alexbatalov/fallout2-ce).

The engine is offered under its **Sustainable Use License**, reproduced in
[third_party/engine-LICENSE.md](third_party/engine-LICENSE.md). In particular,
its distribution is restricted to free-of-charge, non-commercial purposes.
The manager's MIT license does not change those engine terms.

Upstream author and dependency notices are preserved in
[third_party/engine-AUTHORS.md](third_party/engine-AUTHORS.md). The complete
original README, changelog, license and author notices are also embedded in the
Windows package and copied into each prepared game folder. Engine source is
available in the upstream repository at the linked release tag.

## Runtime and packaging

The Windows executable bundles CPython, Tcl/Tk, and the PyInstaller bootloader.
Their license notices are supplied in the release's `third_party/runtime`
directory. PyInstaller's bootloader exception permits distribution of packaged
applications under their own terms.

## Fallout 2 game data

No original game data, Steam files, save games, or modified game assets are
distributed. Every player must obtain their own licensed copy of Fallout 2.
