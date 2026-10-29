# Local patches to AdditiveFOAM

`setup/install_stack.sh` applies every `*.patch` here to `external/AdditiveFOAM`
before building. They live here, not in the submodule, so the submodule keeps
pointing at the upstream commit. After `git submodule update`, the submodule
working tree is clean again: rerun the install script (or
`git -C external/AdditiveFOAM apply setup/patches/*.patch` and `./Allwmake -j`).

## marangoni-assignable.patch

**Symptom:** with flow enabled (`nOuterCorrectors 1`) in a closed domain, the
run aborts as soon as a melt pool forms:
`Continuity error cannot be removed by adjusting the outflow`.

**Cause:** the `marangoni` U boundary condition derives from
`transformFvPatchField`, whose `assignable()` returns `true`. `constrainHbyA`
therefore leaves the extrapolated `HbyA` on the top patch, which has a normal
component, so `phiHbyA` carries flux through the top surface. With every
other wall `noSlip`, `adjustPhi` has no outflow to balance it against.

**Fix:** override `assignable()` to return `false`, the same as OpenFOAM's
`partialSlip`, so `HbyA` on the patch takes the BC's own value (tangential
only) and the normal flux is zero. The tangential Marangoni shear is
unchanged. Upstream tutorials never hit this because they all run
conduction-only (`nOuterCorrectors 0`).
