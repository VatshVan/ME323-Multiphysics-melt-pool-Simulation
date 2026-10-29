# Setup: Ubuntu + OpenFOAM-14 + AdditiveFOAM

AdditiveFOAM 2.0.0 (submodule `external/AdditiveFOAM`, commit `8314d3c`)
requires **OpenFOAM-14** from the OpenFOAM Foundation (openfoam.org — not the
ESI `v2xxx` releases). It runs natively on Ubuntu 22.04 (jammy) or 24.04
(noble); `dl.openfoam.org` ships `openfoam14` packages for both.

## 1. Install OpenFOAM-14, build AdditiveFOAM, create the Python venv

From the project root:

```bash
bash setup/install_stack.sh
```

This script (asks for your `sudo` password once):

1. adds the `dl.openfoam.org` apt repository and installs `openfoam14`
   (to `/opt/openfoam14`, ParaView included),
2. fetches the `external/AdditiveFOAM` submodule if needed and builds it with
   `./Allwmake -j` (log: `setup/build.log`); the solver `additiveFoam`, its
   libraries and function objects go to `~/OpenFOAM/<user>-14/platforms/`,
3. creates `.venv/` with AdditiveFOAM's pinned Python packages and ours.

## 2. Every new terminal

```bash
source setup/env.sh
```

## 3. Smoke test (an unmodified AdditiveFOAM tutorial)

```bash
source setup/env.sh
mkdir -p ~/run && cp -r $ADDITIVEFOAM_TUTORIALS/AMB2018-02-B ~/run/
cd ~/run/AMB2018-02-B && ./Allrun
```

Expected: it finishes in a few seconds on 8 processes without errors,
writes time directories up to `0.004`, `log.additiveFoam` reports
`absorbed power: 59.1` while the beam is on and ends with
`Finalising parallel run`, and `log.reconstructPar` ends with `End`.

## Notes

- **Disk space.** OpenFOAM-14 takes roughly 1–2 GB in `/opt`. Result output
  is the larger cost: the 100 µm case writes tens of MB per time directory in
  ASCII. Keep `writeInterval` coarse, consider `writeFormat binary;` and
  `writeCompression on;` in `controlDict`, and delete unneeded processor
  directories after `reconstructPar`.
- **Line endings.** `.gitattributes` forces LF. CRLF line endings (e.g. from a
  Windows checkout) in OpenFOAM dictionaries or `Allrun` scripts break them.
  If an editor converts a file, run `git add --renormalize .`.
- **ParaView.** Open `case.foam` from the generated case with `paraFoam` or
  the ParaView bundled with OpenFOAM-14.
- **Updating the solver.** `git submodule update --remote external/AdditiveFOAM`,
  then rebuild with `./Allwmake -j`. Record the new commit in your results.
