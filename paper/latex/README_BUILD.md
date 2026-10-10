# Paper 3 — Three-Figure LaTeX Manuscript

**Document:** *Bounded Maintenance Recoverability for Selective Lifecycle Escalation of Digital-Twin Models*.

## Contents
- `main.tex` — single authoritative complete IEEEtran manuscript (eight sections, three figures, four tables, Algorithm 1, 24 numbered references)
- `references_ordered.tex` — bibliography in first-citation order
- `references_verified.bib`, `REFERENCE_VERIFICATION_MANIFEST.json` — earlier citation provenance records
- `figures/Fig1_Selective_Lifecycle_Escalation.pdf` — user's original approved Fig.1, unchanged
- `figures/Fig2_Paired_Service_Loss.pdf` — user's final experimental Fig.2, unchanged
- `figures/Fig3_Selective_Search.pdf` — user's final experimental Fig.3, unchanged
- `main.pdf` — compiled 9-page IEEEtran PDF
- `FINAL_SCIENTIFIC_REVIEW.md` — editorial audit, evidence limits, remaining author decisions
- `BUILD_QA.json`, `FILE_SHA256.json` — layout/citation/reference and file-integrity checks

## Build
From this directory:

```bash
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

No BibTeX or external images are required; the `references_ordered.tex` file is directly included.
Use a TeX distribution with `IEEEtran.cls`, `algorithm`, `algpseudocode`, `amsmath`, `booktabs`, `microtype`, etc. This directory can be zipped and uploaded to Overleaf.

## Scope and remaining release checks

This is the **complete three-figure integrated manuscript**, grounded in the archived batch20 integrity-correction report; it is not an independent recomputation of the local Windows raw experimental records. The experiment was performed after previous outcomes had been observed and must not be described as a newly unseen heldout experiment.

1. **Authors:** `main.tex` intentionally retains a placeholder; the paper-specific author order/affiliations and destination venue must be confirmed before submission.
2. **Fig.1:** Its image was preserved exactly as provided. On close review, the bottom ``Commit Selected Action`` node's outgoing route to the RI/reset branch is not drawn as unambiguously as the prose and Algorithm 1. Request a precise vector-arrow repair before formal submission if required; do not silently change the approved source image.
3. **Page 7:** IEEEtran collects the principal results table and Fig.2/Fig.3 on a full float page. It compiles without overfull boxes; refine once the destination journal template/page limit is known.
4. **Scientific boundaries:** theoretical full-class recoverability, finite-policy hindsight labels and online admission score are distinct; the B8 difference interval crosses zero; search update counts are not measured end-to-end compute cost.
