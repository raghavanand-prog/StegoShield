# StegoShield — Interview Preparation

Technical Q&A grounded in what this project actually implements and
measured, not generic textbook answers.

### 1. What is steganography?

The practice of hiding the *existence* of a message inside another,
innocuous-looking cover object (an image, audio file, text, etc.), so
that an observer doesn't even know a secret message is present — as
opposed to just making the message unreadable.

### 2. How is steganography different from cryptography?

Cryptography makes a message unreadable without a key but does not
hide that a (probably secret) message exists — an encrypted file is
obviously encrypted. Steganography hides the *existence* of the
message. They are complementary, not competing: StegoShield could
encrypt a message before embedding it for defense in depth (not
currently implemented, but a natural extension).

### 3. What is LSB (Least Significant Bit) steganography?

Replacing the lowest-order bit of a pixel's colour channel byte with
one bit of the secret payload. Since the LSB contributes at most 1 to
a value in [0, 255], the visual change is imperceptible.

### 4. Why LSB specifically, and not a more complex embedding scheme?

LSB is simple, fast, has high capacity, and — crucially for a learning
project — is easy to reason about mathematically and to *detect*,
which makes it a good foundation for demonstrating both the offensive
(embedding) and defensive (steganalysis) sides of the problem. Real
adversarial steganography often uses adaptive schemes (HUGO, WOW,
S-UNIWARD) that embed preferentially in "noisy" image regions to evade
exactly the kind of statistical detection built here — documented as
future work.

### 5. What is steganalysis?

The detection side: using statistical or ML techniques to determine
whether a piece of media likely contains a hidden payload, without
necessarily being able to extract it.

### 6. How can LSB steganography be detected?

LSB embedding measurably perturbs statistical properties of a natural
image even though it's visually invisible: it pushes the LSB bit-plane
toward a uniform 50/50 distribution (elevated LSB entropy), it
slightly weakens adjacent-pixel correlation (natural images are
locally smooth; embedded bits are independent of neighbouring
content), and it adds a small amount of high-frequency noise. This
project's `app/steganalysis/features.py` implements exactly these
signals.

### 7. Why use machine learning instead of a fixed threshold rule?

No single statistical feature reliably separates clean from stego
images across varied content and payload sizes (see Experiment B in
`docs/research-notes.md`, where CLEAN accuracy was only ~24% on one
test split — a single feature/threshold would fail similarly or worse).
A model can learn a decision boundary across many weak, individually
unreliable signals simultaneously.

### 8. Why Random Forest as the primary model, when Gradient Boosting has higher balanced accuracy?

This is worth answering with the actual process, not just the
conclusion, because the honest answer is "it's close, and the decision
rests on a stated criterion, not a bigger number." Random Forest is a
strong, interpretable baseline for tabular statistical features that
doesn't require large amounts of data to avoid overfitting (unlike
deep learning), provides native feature importances for
explainability, and is fast enough for real-time inference — all still
true. But the actual selection between it and Gradient Boosting was
done with **9-fold leave-one-source-photo-out cross-validation**
(`scripts/cross_validate_models.py`), not a single split, and Gradient
Boosting *does* win on balanced accuracy (0.616 vs 0.587) and
specificity. Random Forest was chosen because it wins on **TPR at a
fixed, operationally realistic false-positive-rate budget (≤20%)** —
the criterion argued to be most appropriate for a human-in-the-loop
triage tool, where the operational question is "how much signal
survives at a false-alarm rate an analyst can tolerate," not a
symmetric-cost metric. That's a stated judgment call, not an objective
fact — see `docs/research-notes.md` (Experiment D) for the full
comparison table and the counter-argument for Gradient Boosting. An
interviewer asking this question is usually testing whether you can
defend a modeling decision with an explicit criterion instead of "it
had the best number" — this project's answer is built to survive that
follow-up.

### 8a. Tell me about a time your own model was wrong and what you did about it.

The first trained Random Forest looked fine in aggregate (76%
accuracy) until the per-class breakdown showed it was only 23.5%
accurate on CLEAN images — a real false-positive bias, not noise. I
formed a concrete, testable hypothesis instead of just writing
"probably needs more data": the training set had a structural 5:1
STEGO:CLEAN imbalance (the dataset generator embeds every clean crop
at 5 payload levels), and the model's `class_weight="balanced"` was
supposedly correcting for that. I ran a controlled ablation
(`scripts/experiment_class_balance.py`) holding everything else fixed
and varying only that one setting — and found `class_weight="balanced"`
was making the problem *worse*, not better. I didn't trust that on one
train/test split (2 photos), so I re-ran it as leave-one-photo-out
cross-validation across all 9 available photos
(`scripts/cross_validate_models.py`), which confirmed the effect at
larger scale (a pooled 90% false-positive rate with the old setting).
That evidence is now the production configuration
(`class_weight=None`), documented with before/after numbers,
including the real cost it introduces (lower recall at low payload
levels) — not presented as a clean win.

### 9. What features did you extract, and why?

49 features per image across 3 channels (see
`app/steganalysis/features.py`): per-channel mean/std/variance/
skewness/kurtosis, Shannon entropy, LSB-plane mean and entropy,
horizontal/vertical adjacent-pixel correlation, pixel-difference
statistics, a high-pass noise-residual estimate, histogram
energy/uniformity, plus cross-channel (R-G/G-B/R-B) correlation. Each
has a documented steganalysis rationale in the code and in
`docs/interview-questions.md` question 6.

### 10. What is entropy, in this context?

Shannon entropy measures how uniformly a distribution's values are
spread: `H = -Σ p(x) log2 p(x)`. For an image channel, high entropy
means pixel values are spread evenly (closer to noise); natural photo
channels usually sit well below the theoretical max of 8 bits. LSB
*plane* entropy specifically is the strongest direct signal for LSB
steganalysis in this project (top feature importances confirm this).

### 11. What is adjacent-pixel correlation, and why does it matter here?

The Pearson correlation between a pixel and its immediate horizontal
or vertical neighbour. Natural images are locally smooth (correlation
usually > 0.9); LSB embedding weakens this slightly because embedded
bits are statistically independent of the image content around them.

### 12. What is MSE?

Mean Squared Error: the average of the squared per-pixel difference
between two images. `MSE = (1/N) Σ (original - modified)²`. Lower means
more similar; StegoShield's LSB embedding produces MSE well under 0.25
even at 50% capacity utilization (Experiment A).

### 13. What is PSNR, and why can it be misleading?

Peak Signal-to-Noise Ratio in dB: `10·log10(MAX² / MSE)`. Higher means
more similar. It can be misleading because it's a purely pixel-wise
metric — it doesn't account for whether the differences are
perceptually meaningful (e.g. spread evenly across a busy region vs.
concentrated in a flat, low-detail region where they'd be more
visible). That's why this project also reports SSIM.

### 14. What is SSIM, and how is it different from PSNR?

Structural Similarity Index — a perceptual metric (0-1) comparing
luminance, contrast, and structural patterns in local windows rather
than raw per-pixel differences. It correlates better with human visual
perception than PSNR/MSE. StegoShield reports all three because they
capture different things.

### 15. How did you prevent data leakage in the ML pipeline?

By splitting train/validation/test **by source photograph** (a
`GroupShuffleSplit` on `source_image` in
`ml/training/splitting.py`), never by individual crop or sample. Every
crop, every flip/rotation of that crop, and every stego derivative of
it stays entirely within one split — verified by an explicit assertion
in the split function and by `tests/test_ml.py`'s
`test_no_group_overlap_between_splits`. Without this, the model could
"recognize" a specific photo's noise fingerprint rather than learning
general steganalysis signal, inflating reported accuracy.

### 16. What is overfitting, and how would you know if this model overfits?

Overfitting is when a model learns patterns specific to the training
data (including noise) rather than generalizable structure, so it
performs much better on training data than on unseen data. You'd
compare train vs. validation vs. test metrics — a large gap indicates
overfitting. This project found a concrete example of it:
`class_weight="balanced"` was making the Random Forest overfit to
idiosyncrasies of the small (68-crop) clean training set rather than
learning a signature that transfers to unseen photos — see question 8a
and Experiment C/D in `docs/research-notes.md`. `n_estimators=300` was
chosen as a reasonable default rather than tuned to maximize test-set
score (which would itself be a subtle form of overfitting to the test
set) — see Limitations.

### 17. Precision vs. recall — what's the difference?

Precision = TP / (TP + FP): of everything flagged STEGO, how much
really was. Recall = TP / (TP + FN): of everything that really was
STEGO, how much did we catch. They trade off against each other; the
right balance depends on the cost of each error type.

### 18. Why is recall especially important in a security/detection context — and why doesn't this project just maximize it?

A false negative (missing a real hidden payload) can mean an actual
exfiltration or covert-channel attack goes undetected — often treated
as worse than a false positive (a clean image flagged for human
review, costing analyst time). The naive conclusion is "always
maximize recall." This project's own evidence argues that's too
simple: the original configuration achieved 95% recall via a 90%
false-positive rate (cross-validated) — technically high recall, but
functionally useless, since flagging almost everything provides no
triage signal at all ("crying wolf" / alert fatigue is a real,
well-documented failure mode of over-sensitive detection systems, not
a hypothetical). The criterion this project actually uses is **TPR at
a *bounded*, tolerable false-positive-rate budget** — maximize
detection *subject to* keeping the false-alarm rate low enough that
the tool still does useful triage work — not recall in isolation. The
dashboard's risk score is deliberately just a rescaling of the model's
own probability output (not a hand-tuned formula) so that this
recall/precision tradeoff stays visible and tunable via the
classification threshold rather than hidden inside an opaque score.

### 19. False positive vs. false negative — give concrete examples from this project.

False positive: a genuinely clean photo (e.g. `astronaut`) gets
flagged POSSIBLE STEGO because its naturally high-entropy background
resembles the statistical profile of an embedded image — observed
directly in this project's own testing (see `docs/research-notes.md`).
False negative: a lightly-embedded stego image (5% capacity
utilization) is missed because the payload is too small to perturb
statistics enough to cross the decision boundary — also observed
empirically (35.3% detection accuracy at 5% capacity utilization vs.
76.5% at 50%, Experiment B; these numbers dropped from 79.4%/97.1%
after the class-weighting fix in question 8a traded some recall for
much better specificity).

### 20. How is the risk score calculated?

`risk_score = round(P(stego) × 100)`, banded into LOW (0-30) / MEDIUM
(31-60) / HIGH (61-80) / CRITICAL (81-100). It is explicitly documented
in the UI and code as a **project-defined triage score for
demonstration purposes**, not an industry-standard metric — it is a
monotonic rescaling of the model's own probability, not a separately
hand-tuned formula, specifically so it can't misrepresent what the
model actually predicted.

### 21. What are this project's main limitations?

(1) A small, 9-photograph training corpus vs. research-scale corpora
like BOSSbase/ALASKA2 — the most likely root cause of everything else
on this list; (2) a real, only partially resolved CLEAN-image
false-positive rate (~29–37% depending on split, down from ~76–90%
before the class-weighting fix — see question 8a); (3) low embedding
rates are inherently hard to detect, and got *harder* after that same
fix (a real tradeoff, not a free improvement — see Experiment B in
`docs/research-notes.md`); (4) the classifier is trained only against
this project's own LSB encoder and may not generalize to other tools
or to JPEG-domain steganography; (5) the decision threshold is still
the untuned scikit-learn default (0.5), even though the tools to
justify a better one now exist (`tpr_at_fpr` metric, PR curve). All of
this is documented with real before/after numbers, not asserted — see
the README's Limitations section and `docs/security-review.md` for the
full list including security-specific caveats.

### 22. How could a CNN improve this project?

A convolutional network operating directly on pixel data (or the LSB
plane) can learn spatial patterns that hand-crafted statistical
features might miss, and is the dominant approach in modern
steganalysis research (e.g. SRNet, XuNet, ZhuNet). It would very
likely need substantially more training data than this project's
demonstration corpus to outperform the current classical-feature
Random Forest without overfitting — documented as a concrete, ungated
future-work item.

### 23. How could an attacker evade this specific detector?

Several realistic evasion strategies: (a) use adaptive/content-aware
embedding (HUGO/WOW/S-UNIWARD) that concentrates changes in
already-noisy image regions where the statistical footprint is
smaller; (b) keep the embedding rate very low (this project's own
Experiment B shows 5%-utilization stego is the hardest to detect);
(c) apply light post-processing that perturbs the same statistical
features this model relies on without destroying the payload (though
LSB payloads are fragile to most post-processing, which is itself a
limitation of LSB — not of the detector); (d) target a different
embedding domain (JPEG DCT coefficients) this model was never trained
on.

### 24. How would you integrate this into a SOC / real detection pipeline?

As a **triage layer**, not a standalone verdict system: route
uploaded/attached images through the steganalysis API, surface the
risk score and top indicators to an analyst dashboard (SIEM
integration), and use the risk band to prioritize manual review rather
than auto-block — given the documented false-positive rate, automated
blocking on this model alone would be inappropriate. It would sit
alongside, not replace, existing signature- and behaviour-based
detection.

### 25. Why did you choose to build both the encoder and the detector, instead of just the detector?

Building the encoder first was necessary to generate a labeled,
ground-truth dataset at all — there is no public "this image is
definitely LSB-stego, with exactly this many bytes embedded" dataset
to train against otherwise. It also lets the whole
embed→analyze→quality-check→detect pipeline be demonstrated and
validated end-to-end with real, reproducible data rather than relying
on an external black-box dataset.

### 26. Why does the project separate `app/` (the web service) from `ml/` (training)?

So the trained-model artifact and its metadata are a build output of a
reproducible offline pipeline (`scripts/generate_dataset.py` →
`scripts/train_model.py`), not something the web application computes
at request time. The Flask app only loads the pre-trained pipeline
(`app/steganalysis/predictor.py::ModelRegistry`) — this keeps
inference fast, keeps training reproducible/versioned independently of
the app, and mirrors how a real ML system separates training and
serving.

### 27. How did you validate the payload integrity mechanism actually works?

`tests/test_steganography.py::TestPayloadIntegrity` deliberately flips
bits inside an encoded payload's region and asserts the SHA-256
checksum check raises `IntegrityVerificationError` — not just that
decoding "looks different." The header/checksum design
(`app/steganography/payload.py`) is verified both by this direct test
and indirectly by every round-trip test that must first parse the
header correctly.
