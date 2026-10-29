# Setup: WSL2 + OpenFOAM-14 + AdditiveFOAM

AdditiveFOAM 2.0.0 (submodule `external/AdditiveFOAM`, commit `8314d3c`)
requires **OpenFOAM-14** from the OpenFOAM Foundation (openfoam.org — not the
ESI `v2xxx` releases). OpenFOAM runs on Linux, so on this Windows machine we
use WSL2 with Ubuntu 24.04.

## 1. Install WSL2 + Ubuntu (once, needs admin + reboot)

In an **administrator** PowerShell:

```powershell
wsl --install -d Ubuntu-24.04
```

Reboot, open "Ubuntu 24.04" from the Start menu, and create a Linux user
name and password.

## 2. Install OpenFOAM-14, build AdditiveFOAM, create the Python venv

In the Ubuntu terminal:

```bash
cd /mnt/d/Final_project
bash setup/install_stack.sh
```

This script:

1. adds the `dl.openfoam.org` apt repository and installs `openfoam14`
   (to `/opt/openfoam14`, ParaView included),
2. builds AdditiveFOAM with `./Allwmake -j` (log: `setup/build.log`); the
   solver `additiveFoam`, its libraries and function objects go to
   `~/OpenFOAM/<user>-14/platforms/`,
3. creates `.venv/` with AdditiveFOAM's pinned Python packages and ours.

## 3. Every new terminal

```bash
source /mnt/d/Final_project/setup/env.sh
```

## 4. Smoke test (an unmodified AdditiveFOAM tutorial)

```bash
source /mnt/d/Final_project/setup/env.sh
mkdir -p ~/run && cp -r $ADDITIVEFOAM_TUTORIALS/AMB2018-02-B ~/run/
cd ~/run/AMB2018-02-B && ./Allrun
```

Expected: it finishes without errors, writes time directories up to
`0.004`, and the `log.additiveFoam` file ends with `End`.

## Notes

- **Line endings.** `.gitattributes` forces LF. Windows CRLF line endings in
  OpenFOAM dictionaries or `Allrun` scripts break them in Linux. If an
  editor converts a file, run `git add --renormalize .`.
- **Performance.** `/mnt/d` is a Windows drive accessed through WSL, so file
  I/O there is slower than in the Linux home directory. For long production
  runs, copy the case to `~/run/` and copy `postProcessing/` and the chosen
  time directories back afterwards.
- **ParaView.** Open `case.foam` from the generated case in ParaView. You can
  use the Windows ParaView build and open it from
  `\\wsl$\Ubuntu-24.04\...` or from `D:\Final_project\cases\...`.
- **Updating the solver.** `git submodule update --remote external/AdditiveFOAM`,
  then rebuild with `./Allwmake -j`. Record the new commit in your results.
