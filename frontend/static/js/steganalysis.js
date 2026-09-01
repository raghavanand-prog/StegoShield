const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const previewImg = document.getElementById("preview-img");
const analyzeBtn = document.getElementById("analyze-btn");
const analyzeAlert = document.getElementById("analyze-alert");
const verdictEmpty = document.getElementById("verdict-empty");
const verdictPanel = document.getElementById("verdict-panel");
const evidenceSection = document.getElementById("evidence-section");
const interpretationSection = document.getElementById("interpretation-section");
const resultSection = document.getElementById("result-section");
const statusBadge = document.getElementById("analysis-status");

let currentFile = null;

function setStatus(label, state) {
    if (!statusBadge) return;
    statusBadge.textContent = label;
    statusBadge.className = `status-badge ${state}`;
}

function resetResults() {
    if (resultSection) resultSection.style.display = "none";
    if (verdictEmpty) verdictEmpty.style.display = "block";
    if (verdictPanel) verdictPanel.style.display = "none";
    if (evidenceSection) evidenceSection.style.display = "none";
    if (interpretationSection) interpretationSection.style.display = "none";
}

setupDropzone(dropzone, fileInput, (file) => {
    currentFile = file;
    previewImg.src = URL.createObjectURL(file);
    previewImg.style.display = "block";
    analyzeBtn.disabled = false;
    clearAlert(analyzeAlert);
    resetResults();
    setStatus("Ready", "st-ready");

    renderFileState(dropzone, file);
}, {
    onClear: () => {
        currentFile = null;
        previewImg.style.display = "none";
        previewImg.removeAttribute("src");
        analyzeBtn.disabled = true;
        clearAlert(analyzeAlert);
        resetResults();
        setStatus("Ready", "st-ready");
    },
});

analyzeBtn.addEventListener("click", async () => {
    if (!currentFile) return;
    setButtonBusy(analyzeBtn, "Analyzing…");
    setStatus("Analyzing", "st-proc");
    clearAlert(analyzeAlert);

    const formData = new FormData();
    formData.append("image", currentFile);

    try {
        const result = await StegoAPI.postForm("/steganalysis", formData);
        renderVerdict(result);
        setStatus("Complete", "st-done");
    } catch (e) {
        showAlert(analyzeAlert, "error", e.message);
        setStatus("Failed", "st-err");
    } finally {
        setButtonIdle(analyzeBtn, "Run Steganalysis");
    }
});

function renderVerdict(result) {
    if (resultSection) resultSection.style.display = "block";
    verdictEmpty.style.display = "none";
    verdictPanel.style.display = "block";

    const predictionBadge = document.getElementById("prediction-badge");
    predictionBadge.textContent = result.prediction;
    predictionBadge.className = `badge ${result.prediction === "CLEAN" ? "badge-clean" : "badge-stego"}`;

    const riskBadge = document.getElementById("risk-badge");
    riskBadge.textContent = result.risk_level;
    riskBadge.className = `badge ${riskBadgeClass(result.risk_level)}`;

    const pct = (result.stego_probability * 100).toFixed(1);
    document.getElementById("prob-pct").textContent = `${pct}%`;
    const fill = document.getElementById("prob-fill");
    fill.style.width = `${pct}%`;
    fill.className = `progress-fill ${riskProgressClass(result.risk_level)}`;

    document.getElementById("risk-score").textContent = `${result.risk_score} / 100`;
    document.getElementById("v-dims").textContent = result.image_dimensions;
    document.getElementById("v-time").textContent = `${result.processing_time_ms} ms`;
    document.getElementById("risk-desc").textContent = result.risk_description;
    document.getElementById("risk-disclaimer").textContent = result.disclaimer;
    document.getElementById("model-name-value").textContent = result.model_name;

    renderEvidenceTable(result.explanation);
    renderInterpretation(result.indicators, result.prediction);

    verdictPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}
// Evidence rows are API-response-driven and rendered purely via DOM APIs
// (createElement/textContent) - the same safe pattern used across this app.
function renderEvidenceTable(explanation) {
    const tbody = document.getElementById("evidence-tbody");
    tbody.textContent = "";

    if (!explanation || !explanation.length) {
        evidenceSection.style.display = "none";
        return;
    }
    evidenceSection.style.display = "block";

    explanation.forEach((item) => {
        const tr = document.createElement("tr");

        const tdFeature = document.createElement("td");
        tdFeature.className = "col-strong";
        tdFeature.textContent = item.friendly_name;
        tr.appendChild(tdFeature);

        const tdObservation = document.createElement("td");
        const magnitude = item.direction === "above" ? "Elevated" : "Reduced";
        tdObservation.textContent = `${item.description} ${magnitude.toLowerCase()} vs. clean baseline (${Math.abs(item.z_score).toFixed(1)}σ ${item.direction}).`;
        tr.appendChild(tdObservation);

        const tdValue = document.createElement("td");
        tdValue.className = "mono";
        tdValue.textContent = `${item.value} (baseline ${item.clean_baseline_mean})`;
        tr.appendChild(tdValue);

        const tdImportance = document.createElement("td");
        tdImportance.className = "mono text-dim";
        tdImportance.textContent = item.model_importance;
        tr.appendChild(tdImportance);

        tbody.appendChild(tr);
    });
}

function renderInterpretation(indicators, prediction) {
    const list = document.getElementById("interpretation-list");
    list.textContent = "";

    if (!indicators || !indicators.length) {
        interpretationSection.style.display = "none";
        return;
    }
    interpretationSection.style.display = "block";

    const intro = document.getElementById("interpretation-intro");
    intro.textContent =
        prediction === "CLEAN"
            ? "No individual signal was strong enough to flag this image, though the factors below were the closest to the clean/stego boundary."
            : "The following statistical signals contributed most to this image being flagged as possible steganography, ranked by combined deviation and model importance.";

    indicators.forEach((text) => {
        const li = document.createElement("li");
        const marker = document.createElement("span");
        marker.className = "indicator-marker";
        marker.textContent = "▲";
        marker.setAttribute("aria-hidden", "true");
        const span = document.createElement("span");
        span.textContent = text;
        li.appendChild(marker);
        li.appendChild(span);
        list.appendChild(li);
    });
}