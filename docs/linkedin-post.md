I spent the last stretch building StegoShield end-to-end: an image
steganography + AI steganalysis platform, and I wanted to share what
it actually is and what I actually learned, numbers included.

**The problem**

Image steganography — hiding data inside an image's pixel data so the
change is invisible to the eye — is a real defensive-security concern,
not just a CTF trick. It's been documented as a technique for
smuggling payloads past content filters and for data exfiltration,
which means SOC and forensics teams increasingly need automated
steganalysis tooling as a triage layer, the same way they'd use YARA
rules or behavioural detection for other threats.

**What I built**

StegoShield is a Flask web app with two halves:

1. An LSB steganography engine (Pillow + NumPy) with a proper payload
format — magic header, version, length, SHA-256 checksum — so decoding
can tell "this isn't a stego image" apart from "this image was
corrupted or tampered with," rather than just failing silently.

2. An AI steganalysis engine: 49 hand-engineered statistical features
per image (LSB-plane entropy, adjacent-pixel correlation, channel
entropy/skew/kurtosis, noise residuals, histogram characteristics)
feeding a Random Forest classifier that outputs CLEAN / POSSIBLE STEGO
with a probability-derived risk score and a feature-level explanation
of *why*.

**The technical work that mattered most**

Getting the ML evaluation methodology right, not just the model. The
dataset is built by tiling and augmenting a small public-domain photo
corpus, then splitting train/validation/test **by source photograph**
(not by individual sample) so no crop — or any stego version of it —
crosses a split boundary. Skip that and you get an accuracy number
that's really just measuring memorization of one photo's noise
fingerprint.

I also ran small experiments instead of just reporting a single
accuracy figure: payload size vs. image quality (MSE/PSNR/SSIM stay
excellent even at 50% capacity utilization — that's *why* LSB is
imperceptible), and payload size vs. detection accuracy.

**The part I actually want to talk about: the model was wrong, and I
found out why**

The first trained model looked fine on paper — 76% accuracy — until I
broke that number down by class instead of trusting the aggregate: it
was only catching 23% of clean images correctly. It had a real
false-positive bias, not a rounding error. I could have stopped there
and just written it up as a "known limitation." Instead I went and
found the actual cause: the training data has 5x more STEGO-labeled
samples than CLEAN ones — not from more real photos, but because the
pipeline embeds every clean crop at 5 payload levels — and the model
was using `class_weight='balanced'` to correct for it. That correction
was the problem: it was overfitting the trees to 68 specific clean
crops instead of learning a signature that generalizes.

I didn't trust that finding on one lucky (or unlucky) train/test split
either. I re-ran it as **9-fold leave-one-photo-out cross-validation**
across every source image, which confirmed it at a larger scale than
the first test showed (a pooled 90% false-positive rate with the old
setting, 62.5% without it) — and I used that same cross-validation to
make an evidence-based call on which of three model families
(Random Forest / Gradient Boosting / Logistic Regression) should be
primary, using an explicit criterion suited to a triage tool (TPR at a
realistic false-positive budget) rather than just picking whichever
had the best headline ROC-AUC.

**Results — real numbers, not cherry-picked, including the ones that
went down**

Current primary model (Random Forest, `class_weight=None`, held-out
test set): **61.0% accuracy, 0.725 ROC-AUC, 70.6% specificity** (was
23.5%). That's not an unambiguous win — detection sensitivity at low
payload levels dropped substantially in the process (5% capacity
utilization: 79% → 35% detected), because the model moved to a more
conservative decision boundary. I reported that tradeoff plainly
instead of only highlighting the improvement, because a "fix" that
trades one failure mode for another isn't actually fixed — it's a
different, better-understood operating point, and I now have the
metrics (TPR-at-fixed-FPR, PR-AUC, balanced accuracy) to say precisely
which one.

**What I learned**

Steganalysis is a genuinely hard, adversarial statistics problem — no
single feature reliably separates clean from stego across varied image
content. But the bigger lesson was methodological: a weak headline
number is a starting point for investigation, not a thing to hide or
apologize for. Diagnosing *why* a model fails, verifying the diagnosis
with proper cross-validation instead of one split, and making the next
decision (which model, which config) on an explicit stated criterion
instead of a raw leaderboard number — that's the actual engineering
work, and it's the part a "76% accuracy" headline would have hidden
completely.

**What's next**

Decision-threshold tuning now that the ROC/PR curves and TPR-at-fixed-FPR
metrics exist to justify a specific operating point; a larger,
research-scale training corpus (BOSSbase/ALASKA2-style) to see whether
the remaining false-positive rate is a dataset-size artifact; a
CNN-based steganalysis path for comparison against the classical
feature set; and extending detection into the JPEG/DCT domain.

Code, tests, security review, and full write-up (including the
"what I got honestly wrong" parts) are on GitHub. Feedback and
pushback welcome, especially from anyone who's worked on steganalysis
or adversarial ML — I'd like to know where this breaks.

#cybersecurity #machinelearning #steganography #steganalysis #python #infosec
