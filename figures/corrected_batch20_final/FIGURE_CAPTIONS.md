# Paper 3 corrected batch20 figure captions

These captions accompany figures generated exclusively from the verified integrity-correction replication. They do not authorize manuscript edits. Proposed denotes the saved method identifier `P7.7`; B8 denotes always-open model-level search.

## Fig. 2 — Paired lifecycle service-loss comparison

**Paired lifecycle service-loss comparison.** (a) Observed Proposed-minus-baseline mean differences and saved marginal 95% paired center-bootstrap intervals (20 centers; 4,000 shared center resamples; seed 2904). Negative differences indicate lower service loss for Proposed. The main forest uses one complete linear scale; the separately labeled B8 linear zoom contains zero and both interval endpoints. The B8 difference is approximately +2.802 × 10⁻⁵, with interval [−1.859 × 10⁻⁷, +8.424 × 10⁻⁵], which crosses zero and establishes neither superiority, equivalence nor noninferiority. (b) Observed Proposed-minus-B8 differences for all 20 centers in center-ID order, retaining 18 zero differences. Each center's service MSE is averaged over 24 stages, three seeds and four scenarios. Center points are descriptive paired observations, without connecting lines or newly calculated intervals. Equal observed values are not a statistical equivalence conclusion.

Recommended placement: main text immediately after the primary service-loss results; `figure*`, width `\textwidth` (nominal 7.16 inches), native artwork height 4.5 inches. Do not reduce the two-panel composite to a single IEEE column.

```latex
\begin{figure*}[t]
  \centering
  \includegraphics[width=\textwidth]{figures/paper3_corrected_batch20_final/Fig2_Paired_Service_Loss.pdf}
  \caption{Paired lifecycle service-loss comparison. (a) Observed
  Proposed-minus-baseline mean differences and saved marginal 95\%
  paired center-bootstrap intervals (20 centers; 4,000 shared center
  resamples; seed 2904). Negative differences indicate lower service loss
  for Proposed. The main forest uses one complete linear scale; the
  separately labeled B8 linear zoom contains zero and both interval
  endpoints. The B8 difference is approximately $+2.802\times10^{-5}$,
  with interval $[-1.859\times10^{-7},\,+8.424\times10^{-5}]$, which
  crosses zero and establishes neither superiority, equivalence nor
  noninferiority. (b) Observed Proposed-minus-B8 differences for all
  20 centers in center-ID order, retaining 18 zero differences. Each
  center's service MSE is averaged over 24 stages, three seeds and four
  scenarios. Center points are descriptive paired observations, without
  connecting lines or newly calculated intervals. Equal observed values
  are not a statistical equivalence conclusion.}
  \label{fig:corrected-paired-service-loss}
\end{figure*}
```

## Fig. 3 — Selective model-level search and action behavior

**Selective model-level search and action behavior.** B8 (blue) and Proposed (orange, hatched) are compared over the complete evaluation matrix: 20 centers × three seeds × four scenarios × 24 stages, giving 5,760 stage decisions per method. The zero-based panels separate (a) search admission (5,760/5,760 versus 1,918/5,760 stages), (b) candidate-search optimizer updates (2,664,000 versus 871,400), and (c) committed re-instantiations (RI; 105 versus 104). Values are descriptive rates or totals from the saved experiment, with no additional inferential intervals. Each evaluated search candidate receives 50 optimizer updates; this is a per-candidate budget, not a global search budget. Search admission does not force RI, and candidate-search workload is distinct from action penalties, attributed decision time and measured end-to-end computational cost.

Recommended placement: main text in selective search and action analysis; `figure*`, width `\textwidth` (nominal 7.16 inches), native artwork height 2.8 inches. Each panel reports a different unit; compare methods within a panel rather than heights across panels.

```latex
\begin{figure*}[t]
  \centering
  \includegraphics[width=\textwidth]{figures/paper3_corrected_batch20_final/Fig3_Selective_Search.pdf}
  \caption{Selective model-level search and action behavior. B8 (blue)
  and Proposed (orange, hatched) are compared over the complete evaluation
  matrix: 20 centers $\times$ three seeds $\times$ four scenarios
  $\times$ 24 stages, giving 5,760 stage decisions per method. The
  zero-based panels separate (a) search admission (5,760/5,760 versus
  1,918/5,760 stages), (b) candidate-search optimizer updates (2,664,000
  versus 871,400), and (c) committed re-instantiations (RI; 105 versus
  104). Values are descriptive rates or totals from the saved experiment,
  with no additional inferential intervals. Each evaluated search
  candidate receives 50 optimizer updates; this is a per-candidate
  budget, not a global search budget. Search admission does not force RI,
  and candidate-search workload is distinct from action penalties,
  attributed decision time and measured end-to-end computational cost.}
  \label{fig:corrected-selective-search}
\end{figure*}
```

## Optional Fig. 4 decision

Fig. 4 is omitted because the manuscript's `tab:scenario` already provides the four-scenario Proposed/B8 service-loss comparison together with action information. Corrected scenario-center data are available for all 20 centers and all four scenarios; omission is an editorial redundancy decision, not a decision based on effect direction or statistical significance. The scenario table needs a later authorized update to the corrected values. No table or manuscript file is edited by this figure task.
