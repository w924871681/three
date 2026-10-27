# Experimental path portability patch (2026-10-27)

`root_paths.patch` changes five frozen execution/coordination source copies so their repository root is derived from their own `code/verification/paper3_canonical_inputs/...` location rather than the original `D:\dt-talk\DT_LIFECYCLE_ESCALATION`. The patch is a preliminary artifact for a separate disposable copy; original files and existing evidence remain unchanged.

**Not a runnable end-to-end reproduction release.** Applying it changes source hashes bound by scientific manifests. Environment descriptors, frozen input/receipt paths, runtime startup policies, and other components still refer to original locations and/or hashes. Do not disable guards or relabel old certificates. A portable runtime must explicitly rebuild and independently check those bindings, restore inputs and environment, run the complete controlled experiment, and compare its outputs with the archived corrected results before claiming reproducibility. The historical numerical-equivalence limitation remains.

The patch was generated against the files in commit `219c28ae5181c7b5f92e88f5af70d1df3e021a0c`. Static verification only: all five modified Python texts parse and their calculated root resolves to `code/` in the source layout. No model, scheduler, experiment, manifest requalification, relocation, or fresh-download test was performed.

Review the patch, then only in a separate copy:

```text
git apply --check portable_experiment/root_paths.patch
```

It must not be applied to the archived scientific worktree or mistaken for complete support. The environment and data are available at https://github.com/w924871681/three/releases/tag/paper3-full-data-env-20261010 . The independent reproducibility procedure remains unfinished.
