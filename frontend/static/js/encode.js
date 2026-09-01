const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const previewImg = document.getElementById("preview-img");
const capacityPanel = document.getElementById("capacity-panel");
const messageInput = document.getElementById("message-input");
const messageSizeHint = document.getElementById("message-size-hint");
const capacityBarWrap = document.getElementById("capacity-bar-wrap");
const capacityFill = document.getElementById("capacity-fill");
const capacityPct = document.getElementById("capacity-pct");
const encodeBtn = document.getElementById("encode-btn");
const encodeAlert = document.getElementById("encode-alert");
const resultsSection = document.getElementById("results-section");

let currentFile = null;
let currentCapacity = null;

const LOSSLESS_EXTS = new Set(["png", "bmp"]);

function byteLength(str) {
    return new TextEncoder().encode(str).length;
}

function refreshMessageStats() {
    const bytes = byteLength(messageInput.value);
    messageSizeHint.textContent = `${bytes} bytes`;

    if (currentCapacity) {
        const total = currentCapacity.total_capacity_bytes;
        const used = bytes + currentCapacity.header_overhead_bytes;
        const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
        capacityFill.style.width = `${pct}%`;
        capacityPct.textContent = `${pct.toFixed(1)}%`;
        capacityFill.style.background =
            pct > 95 ? "var(--danger)" : pct > 70 ? "var(--warning)" : "";
    }

    const overCapacity = currentCapacity && bytes > currentCapacity.max_message_bytes;
    if (overCapacity) {
        showAlert(
            encodeAlert,
            "error",
            `Message exceeds image capacity. Maximum supported payload: ${formatBytes(currentCapacity.max_message_bytes)}.`
        );
    } else {
        clearAlert(encodeAlert);
    }
    encodeBtn.disabled = !currentFile || bytes === 0 || overCapacity;
}

function resetResults() {
    resultsSection.style.display = "none";
    const downloadLink = document.getElementById("download-link");
    if (downloadLink) downloadLink.removeAttribute("href");
}

async function handleFile(file) {
    currentFile = file;
    currentCapacity = null;
    capacityPanel.style.display = "none";
    capacityBarWrap.style.display = "none";
    clearAlert(encodeAlert);
    resetResults();

    renderFileState(dropzone, file);
    previewImg.src = URL.createObjectURL(file);
    previewImg.style.display = "block";

    const ext = file.name.split(".").pop().toLowerCase();
    if (!LOSSLESS_EXTS.has(ext)) {
        showAlert(
            encodeAlert,
            "error",
            "Encoding requires a lossless image format (PNG or BMP). JPEG compression would destroy a hidden payload."
        );
        encodeBtn.disabled = true;
        return;
    }

    const formData = new FormData();
    formData.append("image", file);
    try {
        const capacity = await StegoAPI.postForm("/capacity", formData);
        currentCapacity = capacity;

        // Filename/size come from the client File object (never echoed back
        // by the server) and are rendered via textContent - a filename is
        // attacker-influenced input.
        document.getElementById("info-filename").textContent = file.name;
        document.getElementById("info-format").textContent = capacity.detected_mime || "—";
        document.getElementById("info-dimensions").textContent = `${capacity.width} × ${capacity.height} px`;
        document.getElementById("info-filesize").textContent = formatBytes(file.size);

        document.getElementById("cap-channels").textContent = capacity.channels;
        document.getElementById("cap-overhead").textContent = formatBytes(capacity.header_overhead_bytes);
        document.getElementById("cap-max").textContent = formatBytes(capacity.max_message_bytes);
        capacityPanel.style.display = "block";
        capacityBarWrap.style.display = "block";
        refreshMessageStats();
    } catch (e) {
        showAlert(encodeAlert, "error", e.message);
        currentCapacity = null;
        encodeBtn.disabled = true;
    }
}

setupDropzone(dropzone, fileInput, handleFile, {
    onClear: () => {
        currentFile = null;
        currentCapacity = null;
        capacityPanel.style.display = "none";
        capacityBarWrap.style.display = "none";
        previewImg.style.display = "none";
        previewImg.removeAttribute("src");
        messageInput.value = "";
        refreshMessageStats();
        resetResults();
    },
});

messageInput.addEventListener("input", refreshMessageStats);
encodeBtn.addEventListener("click", async () => {
    if (!currentFile) return;
    setButtonBusy(encodeBtn, "Encoding…");
    clearAlert(encodeAlert);
    resetResults();

    const formData = new FormData();
    formData.append("image", currentFile);
    formData.append("message", messageInput.value);

    try {
        const result = await StegoAPI.postForm("/encode", formData);
        renderResults(result);
    } catch (e) {
        showAlert(encodeAlert, "error", e.message);
    } finally {
        setButtonIdle(encodeBtn, "Encode Message");
        refreshMessageStats();
    }
});

function renderResults(result) {
    resultsSection.style.display = "block";

    document.getElementById("q-mse").textContent = result.quality.mse;
    document.getElementById("q-psnr").textContent = result.quality.psnr_display;
    document.getElementById("q-ssim").textContent = result.quality.ssim;
    document.getElementById("q-explain").textContent =
        "PSNR above ~40 dB and SSIM near 1.0 indicate the stego image is visually indistinguishable from the original.";

    document.getElementById("r-msgsize").textContent = formatBytes(result.message_bytes);
    document.getElementById("r-util").textContent = `${result.utilization_percent}%`;
    document.getElementById("r-time").textContent = `${result.processing_time_ms} ms`;

    const stegoDataUrl = `data:image/png;base64,${result.stego_image_png_base64}`;
    const downloadLink = document.getElementById("download-link");
    downloadLink.href = stegoDataUrl;

    if (result.visual_analysis) {
        document.getElementById("img-original").src = `data:image/png;base64,${result.visual_analysis.original_png_b64}`;
        document.getElementById("img-stego").src = stegoDataUrl;
        document.getElementById("img-diff").src = `data:image/png;base64,${result.visual_analysis.difference_png_b64}`;
        document.getElementById("img-hist").src = `data:image/png;base64,${result.visual_analysis.histogram_png_b64}`;
    }

    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}