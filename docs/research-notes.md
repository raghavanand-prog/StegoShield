# StegoShield — Research Notes

This document frames StegoShield as a starting point for a research
project rather than only a portfolio demo: the questions it raises, the
experiments already run to answer some of them with real data, and the
honest limitations of the current dataset and pipeline.

## Research questions

1. **How does payload size affect steganographic detectability?**
   Answered empirically below (Experiment B) — accuracy rises
   monotonically with embedding rate on this dataset.
2. **Which statistical image features are most useful for LSB
   steganalysis?** Partially answered via the trained Random Forest's
   feature importances (see `ml/models/model_metadata.json` /
   the Model Performance page) — LSB-plane mean/entropy features
   dominate, consistent with the steganalysis literature.
3. **How does payload capacity affect PSNR/SSIM?** Answered
   empirically below (Experiment A).
4. **How does ML performance change across different classifier
   families** (linear vs. tree ensemble vs. boosting) **on the same
   leak-safe split?** Answered by `scripts/train_model.py`'s
   three-model comparison.
5. **How well does the model generalize to unseen source images?**
   Partially answered — the group-based test split (`chelsea`,
   `retina`) is entirely disjoint from training images, so the
   reported test metrics already measure cross-image generalization,
   not just cross-crop generalization. Full generalization to
   real-world, arbitrary photographs remains open (see Limitations).
6. **Does correcting for training-label class imbalance fix the
   CLEAN-image false-positive bias?** Answered empirically below
   (Experiment C, confirmed by 9-fold cross-validation in Experiment
   D) — no, not with naive `class_weight='balanced'`, which measurably
   *worsens* it (a pooled 90% false-positive rate across all 9 held-out
   photos); removing it substantially reduces the problem (down to
   62.5% pooled FPR) but does not eliminate it, and trades away real
   detection sensitivity at low payload levels in the process.
7. **Given a real tradeoff between model families with no single
   "best" answer, how should the primary model be chosen for a
   detection system?** Answered in Experiment D: not by raw ROC-AUC,
   but by an explicit, stated criterion appropriate to the
   application's actual use case (TPR at an operationally realistic
   false-positive-rate budget, for a human-in-the-loop triage tool) —
   with the alternative criterion and its different answer (Gradient
   Boosting, under a symmetric-cost assumption) reported alongside it
   rather than hidden.

## Experiment A — Payload size vs. image quality

**Method:** `scripts/run_experiments.py` encodes a payload at each
target capacity-utilization level into every base cover image (256×256
crop) and measures MSE / PSNR / SSIM against the unmodified original.

**Real results** (averaged across all 9 base images; see
`data/dataset/experiment_results.json` for the full per-image data):

| Payload level (target capacity utilization) | Mean MSE | Mean PSNR (dB) | Mean SSIM |
|---|---|---|---|
| 5%  | 0.0251 | 64.14 | 0.99965 |
| 10% | 0.0498 | 61.16 | 0.99917 |
| 20% | 0.0997 | 58.14 | 0.99824 |
| 30% | 0.1499 | 56.38 | 0.99736 |
| 50% | 0.2498 | 54.15 | 0.99572 |

**Interpretation:** MSE grows almost exactly linearly with payload
size (as expected — each embedded bit contributes an independent,
bounded ±1 pixel perturbation), while PSNR falls off logarithmically.
Even at 50% capacity utilization — embedding into half of every usable
bit position — PSNR stays above 54 dB and SSIM above 0.995, both well
within the range conventionally considered visually indistinguishable
from the original. This quantifies *why* LSB steganography is
imperceptible even at fairly high embedding rates, and why visual
inspection alone is not a viable steganalysis strategy — motivating
the statistical/ML approach in Module 6.

## Experiment B — Payload size vs. detection accuracy

**Method:** Using the trained Random Forest and the **held-out test
split** (source images `chelsea` and `retina`, never seen during
training), accuracy is computed separately for the CLEAN samples and
for STEGO samples at each payload level.

**Real results** (current production model — Random Forest,
`class_weight=None`; see Experiments C and D below for why):

| Sample group | n | Accuracy | Accuracy before the class-weighting fix (Experiment C/D) |
|---|---|---|---|
| CLEAN (0%) | 68 | **0.7059** | 0.2353 |
| STEGO @ 5%  | 68 | 0.3529 | 0.7941 |
| STEGO @ 10% | 68 | 0.4265 | 0.8088 |
| STEGO @ 20% | 68 | 0.6912 | 0.8824 |
| STEGO @ 30% | 68 | 0.7206 | 0.8824 |
| STEGO @ 50% | 68 | 0.7647 | 0.9706 |

**Interpretation — this is a real tradeoff, not an unambiguous
improvement.** The class-weighting fix (Experiments C/D) more than
triples CLEAN accuracy (23.5% → 70.6%), which is the headline
improvement. But it comes at a real, honestly-reported cost: STEGO
detection accuracy drops at every payload level, most sharply at low
payloads (5%: 79.4% → 35.3%; 10%: 80.9% → 42.7%) and substantially even
at high payloads (50%: 97.1% → 76.5%). The model moved to a more
conservative decision boundary — it now needs stronger evidence before
calling an image STEGO, which helps on clean images and hurts on
subtly-embedded ones. The underlying ranking quality genuinely
improved (ROC-AUC 0.608 → 0.725, PR-AUC 0.917 → 0.922 — see Experiment
D), but the *default* 0.5 probability threshold does not exploit that
improvement optimally; see Future Work (decision-threshold tuning).

**Low-payload detection being hard in the first place is expected**
and literature-consistent — larger payloads perturb more of the LSB
plane and are statistically easier to distinguish from a clean image —
but this project's specific low-payload numbers should now be read
against the CLEAN accuracy tradeoff above, not in isolation.

The **CLEAN-image false-positive problem is real and only partially
resolved, not fixed.** Even after the fix, 70.6% CLEAN accuracy still
means roughly **3 in 10 clean images are wrongly flagged**. Combined
with the still-modest ROC-AUC (0.725), this indicates the model has
learned a real but imperfect signal that does not generalize cleanly
to every new source image — most likely because the training corpus (9
base photographs) is too small and too visually heterogeneous for the
Random Forest to learn a clean-image "baseline" that holds across very
different image content (e.g. `retina`'s dense biological texture vs.
`astronaut`'s smooth studio photography). This is documented honestly
rather than cherry-picking a more flattering result, and remains the
single biggest lever for improving this project (see Future Work / a
larger corpus such as BOSSbase or ALASKA2).

## Experiment C — Does training-label class balancing explain the CLEAN false-positive bias?

**Motivation.** Experiment B's CLEAN accuracy of 23.5% needed a real
diagnosis, not just a "small dataset" hand-wave. One concrete,
testable hypothesis: `ml/dataset/generator.py` embeds every clean crop
at 5 payload levels, so the training set is structurally 5:1
STEGO:CLEAN (340 vs 68 samples) — not from having more real clean
photos, but from replicating the *same* 68 crops five times under
different embeddings. The production Random Forest already trains
with `class_weight='balanced'` specifically to correct for this. Does
it actually help?

**Method** (`scripts/experiment_class_balance.py`): three Random
Forest models, otherwise **identical** (`n_estimators=300`,
`random_state=42`, same features, same leak-safe group split — train
on 5 photos, test on the same 2 held-out photos, `chelsea`/`retina`,
used everywhere else in this document), varying only how the 5:1
imbalance is handled during training:

- **A — `class_weight='balanced'`** (the current production setting)
  on the full imbalanced training set.
- **B — `class_weight=None`**, same imbalanced training set (isolates
  whether "balanced" mode itself is responsible for the bias).
- **C — `class_weight=None`**, STEGO randomly undersampled to 68
  samples so the training set is a true 1:1 (a second, independent way
  to correct the same imbalance).

**Real results** (test set: 68 clean / 340 stego, same split as
Experiment B; full output in
`data/dataset/class_balance_experiment_results.json`):

| Condition | Accuracy | CLEAN accuracy | STEGO recall | ROC-AUC | TN | FP | FN | TP |
|---|---|---|---|---|---|---|---|---|
| A — `class_weight='balanced'` (production) | 76.2% | **23.5%** | 86.8% | 0.608 | 16 | 52 | 45 | 295 |
| B — `class_weight=None` | 61.0% | **70.6%** | 59.1% | 0.725 | 48 | 20 | 139 | 201 |
| C — undersampled 1:1, `class_weight=None` | **78.2%** | 47.1% | 84.4% | **0.728** | 32 | 36 | 53 | 287 |

**Interpretation.** The hypothesis was directionally right but the
mechanism was backwards: `class_weight='balanced'` is not neutral here
— it is actively *worse* than doing nothing, on every metric except
raw STEGO recall. Removing it (condition B) more than triples CLEAN
accuracy (23.5% → 70.6%) and raises ROC-AUC from 0.608 to 0.725, a
large, threshold-independent improvement in the model's underlying
ranking quality. Explicit 1:1 undersampling (condition C) lands
between the two and gives the best overall accuracy and ROC-AUC of the
three.

A plausible mechanism, **stated as a hypothesis, not a proven
mechanism**: `class_weight='balanced'` in a Random Forest reweights
the impurity criterion used to choose tree splits, not just a final
decision threshold. With only 68 independent clean crops from 5
training photos, upweighting each one ~5x pushes the trees toward
splits that isolate small, possibly idiosyncratic pockets of those
*specific* clean crops — a form of overfitting to the training photos'
individual texture/noise fingerprints (a "cover-source mismatch"
effect well documented in the steganalysis literature) rather than
learning a clean-image signature that transfers to the two unseen test
photos. Condition B, without that reweighting pressure, ends up with a
more conservative and apparently more transferable decision boundary.

**This finding was not treated as settled on 2 photos alone.** The
entire test set here is 2 source photos, so before promoting this
change to production it was re-tested with 9-fold cross-validation
across every available photo — see Experiment D immediately below. The
result held up, and this configuration (`class_weight=None`) is now
the production default in `ml/training/train_model.py`.

## Experiment D — 9-fold cross-validated primary-model selection

**Motivation.** Two open questions after Experiment C: (1) does the
class-weighting finding hold up across more than one held-out photo
pair, and (2) which of the three model families (Random Forest,
Gradient Boosting, Logistic Regression) should be the *primary*
deployed model — the project had been defaulting to Random Forest
without a stated, defensible reason, and Gradient Boosting has a
higher single-split ROC-AUC (0.639 vs 0.608, under the old
`class_weight='balanced'` Random Forest).

**Method** (`scripts/cross_validate_models.py`): **leave-one-source-
photo-out cross-validation** — `sklearn.model_selection.
LeaveOneGroupOut`, grouped by `source_image`. Every one of the 9
available photos is held out in turn (8 photos train, 1 tests), so
every one of the 960 samples gets exactly one out-of-fold prediction,
still fully source-image-disjoint (no photo's crops, or any payload-
level derivative of them, ever appear in both a fold's training and
its own test set). Four configurations were compared, holding
`n_estimators=300`/`random_state=42`/features/split method fixed:
Random Forest with `class_weight='balanced'` (the old default),
Random Forest with `class_weight=None` (Experiment C's candidate),
Gradient Boosting (doesn't support `class_weight` in scikit-learn),
and Logistic Regression with `class_weight='balanced'`.

Two aggregations are reported: **pooled** (all 960 out-of-fold
predictions concatenated and scored once — the headline number, not
distorted by small photos like `chelsea`/`colorwheel`/`logo` (24
samples each) carrying equal weight to large ones like `retina` (384
samples)) and **per-fold mean ± std** (how much a metric varies from
one held-out photo to another).

**Real results** (pooled, all 960 samples; full output including
per-fold breakdowns in `data/dataset/cross_validation_results.json`):

| Config | Accuracy | Balanced Acc. | Specificity | FPR | Recall | ROC-AUC | PR-AUC | TPR @ FPR≤20% |
|---|---|---|---|---|---|---|---|---|
| Random Forest, `class_weight='balanced'` (old default) | 81.0% | 52.6% | 10.0% | **90.0%** | 95.3% | 0.660 | 0.917 | 0.483 |
| **Random Forest, `class_weight=None`** | 72.8% | 58.7% | 37.5% | 62.5% | 79.9% | **0.697** | **0.921** | **0.544** |
| Gradient Boosting | 69.3% | **61.6%** | **50.0%** | 50.0% | 73.1% | 0.685 | 0.919 | 0.425 |
| Logistic Regression, `class_weight='balanced'` | 69.2% | 50.5% | 22.5% | 77.5% | 78.5% | 0.529 | 0.843 | 0.251 |

**Finding 1 — the class-weighting result replicates, and is worse than
the single-split version suggested.** Pooled across all 9 held-out
photos, `class_weight='balanced'` produces a **90% false-positive
rate** — close to the degenerate "flag almost everything" failure mode,
which trivially inflates recall (95.3%) without providing real triage
signal. `class_weight=None` cuts that to 62.5% FPR and improves ROC-AUC
(0.660 → 0.697), balanced accuracy (0.526 → 0.587), and TPR at a
20%-FPR budget (0.483 → 0.544) — this is a larger effect than
Experiment C's 2-photo estimate, not a smaller one, so it isn't an
artifact of that particular photo pair. **This is why
`class_weight=None` is now the production Random Forest
configuration.**

**Finding 2 — the primary-model choice is a genuine, close tradeoff,
decided by an explicit stated criterion, not by whichever number was
highest.** Random Forest (`class_weight=None`) and Gradient Boosting
are close on multiple axes, and each wins on a different, defensible
metric:

- Random Forest wins on **ROC-AUC** (0.697 vs 0.685), **PR-AUC** (0.921
  vs 0.919), and **TPR at a ≤20% false-positive-rate budget** (0.544
  vs 0.425).
- Gradient Boosting wins on **balanced accuracy** (0.616 vs 0.587) and
  **specificity** (0.500 vs 0.375) — it makes fewer false-positive
  errors in absolute terms and treats both classes' errors as equally
  costly.

**The criterion adopted here is TPR at a fixed, operationally
realistic FPR budget (≤20%)**, because this application is framed
throughout as a human-in-the-loop *triage* aid (see the API's own "for
demonstration and triage purposes only" disclaimer) — an analyst
reviews what gets flagged, rather than the system acting autonomously.
For a triage tool, the operationally relevant question is "how much
real signal survives at a false-alarm rate an analyst could actually
tolerate," not a full-curve average that includes operating points
(e.g. an 80% false-positive rate) nobody would ever deploy at, and not
a symmetric-cost metric that implicitly treats a missed detection and
one extra image to review as equally bad. Under that criterion, Random
Forest (`class_weight=None`) is selected as primary.

**This is a judgment call, stated plainly rather than hidden:**
Gradient Boosting's balanced-accuracy and specificity advantage is
real, and would be the more defensible choice under a symmetric-cost
assumption, or in a deployment where false alarms are considered as
costly as missed detections. Nothing here should be read as "Random
Forest is objectively better" — it is better *under the specific,
stated criterion this project judged most appropriate for a triage
tool*, and that judgment is falsifiable: a reader who weighs costs
differently has a completely reasonable basis (this same table) to
prefer Gradient Boosting instead.

**Limitations of this cross-validation, stated for the same reason:**
9 folds is still a small number of groups, and per-fold sample counts
are very uneven (24 to 384 samples per photo — see the per-fold
breakdown in `data/dataset/cross_validation_results.json`), so
individual fold metrics are noisy even though the pooled metric uses
every sample. This is a substantially more robust estimate than a
single split, not a definitive one — a larger, independent photo
corpus (see Dataset limitations) is still the right next step before
treating any of these numbers as general claims about LSB
steganalysis rather than about this specific project's pipeline and
9-photo corpus.

## Dataset limitations (read before citing these numbers as general claims)

- **Small photo corpus.** All cover images derive from 9 public-domain
  photographs bundled with `scikit-image`, tiled and augmented
  (flip/rotate) into 240 unique crops, 960 total labeled samples after
  payload-level expansion. This is orders of magnitude smaller than
  research-grade corpora such as **BOSSbase** (10,000 images) or
  **ALASKA2** (75,000+ images) used in published steganalysis papers.
- **Correlated samples within a source image.** Crops and their flips
  from the same base photo share content/texture, so they are not
  fully independent samples — mitigated, but not eliminated, by the
  group-based split that keeps each base photo entirely within one of
  train/val/test.
- **Synthetic payloads.** Embedded messages are random printable ASCII
  text, not real-world payload content (which might have different
  entropy characteristics, e.g. already-compressed or encrypted data).
- **Single embedding algorithm.** The model is trained only against
  StegoShield's own sequential LSB embedder. It has not been evaluated
  against other steganography tools, randomized/scattered bit
  placement, or JPEG-domain (DCT-coefficient) steganography.

## Future work

- **Decision-threshold tuning.** The production model still predicts
  at the default 0.5 probability threshold. Experiment D's improved
  ROC-AUC (0.725) and the new `tpr_at_fpr` metric make it possible to
  pick an explicit, justified operating point (e.g. "the threshold
  that achieves a 15% false-positive rate") instead of the untuned
  default — the natural next step now that Experiment D exists, not
  done here since it's a further behavior change beyond this pass.
- Retrain against a research-scale corpus (BOSSbase/ALASKA2) to test
  whether the CLEAN-image false-positive problem in Experiment B is a
  dataset-size artifact or a genuine feature-set limitation — the
  9-photo corpus is now the clearest remaining bottleneck (Experiment
  D's cross-validation ruled out "just an unlucky split" as the
  explanation, which makes the small corpus itself the more likely
  remaining cause).
- Add a CNN-based steganalysis path (e.g. a small residual network
  over the LSB plane, in the spirit of SRNet/XuNet) as an optional
  advanced module, and compare against the classical-feature Random
  Forest on the same split.
- Extend to JPEG steganalysis (DCT-coefficient statistics) rather than
  spatial-domain LSB only.
- Study adaptive/content-aware embedding (e.g. HUGO, WOW, S-UNIWARD)
  as a harder detection target than naive sequential LSB.
- Investigate adversarial robustness: can an attacker perturb a stego
  image to evade this specific classifier while preserving the hidden
  payload (an adversarial-ML question directly relevant to real-world
  steganalysis deployment)?
