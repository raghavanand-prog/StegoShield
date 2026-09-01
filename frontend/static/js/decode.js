const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const previewImg = document.getElementById("preview-img");
const decodeBtn = document.getElementById("decode-btn");
const decodeAlert = document.getElementById("decode-alert");
const decodeResult = document.getElementById("decode-result");
const decodeEmpty = document.getElementById("decode-empty");
const infoPanel = document.getElementById("info-panel");
const decodeStatus = document.getElementById("decode-status");

let currentFile = null;

function setStatus(label, state) {
    if (!decodeStatus) return;
    decodeStatus.textContent = label;
    decodeStatus.className = `status-badge ${state}`;
}

function resetResultView() {
    decodeResult.style.display = "none";
    if (decodeEmpty) decodeEmpty.style.display = "block";
}

setupDropzone(dropzone, fileInput, async (file) => {
    currentFile = file;
    previewImg.src = URL.createObjectURL(file);
    previewImg.style.display = "block";
    decodeBtn.disabled = false;
    clearAlert(decodeAlert);
    resetResultView();
    setStatus("Ready", "st-ready");

    renderFileState(dropzone, file);

    // Image Information is populated from the same /api/capacity endpoint
    // the Encode page uses - real server-computed metadata, not guessed
    // from the filename alone.
    const formData = new FormData();
    formData.append("image", file);
    try {
        const capacity = await StegoAPI.postForm("/capacity", formData);
        document.getElementById("info-filename").textContent = file.name;
        document.getElementById("info-format").textContent = capacity.detected_mime || "—";
        document.getElementById("info-dimensions").textContent = `${capacity.width} × ${capacity.height} px`;
        document.getElementById("info-filesize").textContent = formatBytes(file.size);
        infoPanel.style.display = "block";
    } catch (e) {
        // Not fatal to decoding itself - /api/decode will surface its own,
        // more specific error if the file is actually invalid.
        infoPanel.style.display = "none";
    }
}, {
    onClear: () => {
        currentFile = null;
        previewImg.style.display = "none";
        previewImg.removeAttribute("src");
        infoPanel.style.display = "none";
        decodeBtn.disabled = true;
        clearAlert(decodeAlert);
        resetResultView();
        setStatus("Ready", "st-ready");
    },
});

decodeBtn.addEventListener("click", async () => {
    if (!currentFile) return;
    setButtonBusy(decodeBtn, "Extracting…");
    setStatus("Extracting", "st-proc");
    clearAlert(decodeAlert);
    resetResultView();

    const formData = new FormData();
    formData.append("image", currentFile);

    try {
        const result = await StegoAPI.postForm("/decode", formData);
        document.getElementById("message-output").value = result.message;
        document.getElementById("d-length").textContent = `${result.payload_length_bytes} bytes`;
        document.getElementById("d-version").textContent = `v${result.payload_version}`;
        document.getElementById("d-time").textContent = `${result.processing_time_ms} ms`;

        const badge = document.getElementById("integrity-badge");
        const note = document.getElementById("integrity-note");
        if (result.integrity_verified) {
            badge.textContent = "Verified";
            badge.className = "status-badge st-done";
            note.textContent = "SHA-256 checksum of the extracted payload matches the embedded checksum.";
        } else {
            badge.textContent = "Not confirmable";
            badge.className = "status-badge st-warn";
            note.textContent = "Payload extracted, but integrity could not be confirmed.";
        }

        // Real SHA-256 of the actual extracted message, computed client-side.
        const shaEl = document.getElementById("d-sha");
        shaEl.textContent = "computing…";
        const sha = await sha256Hex(result.message);
        if (sha) {
            shaEl.textContent = sha;
            setupCopyButton(document.getElementById("d-sha-copy"), sha);
        } else {
            shaEl.textContent = "—  (SHA-256 unavailable in this context)";
            const copyBtn = document.getElementById("d-sha-copy");
            if (copyBtn) copyBtn.style.display = "none";
        }

        decodeEmpty.style.display = "none";
        decodeResult.style.display = "block";
        setStatus("Complete", "st-done");
        decodeResult.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
        if (e.code === "no_hidden_data") {
            showAlert(decodeAlert, "warning", e.message);
            setStatus("No payload", "st-warn");
        } else if (e.code === "integrity_failed") {
            showAlert(decodeAlert, "error", `INTEGRITY CHECK FAILED: ${e.message}`);
            setStatus("Integrity failed", "st-err");
        } else {
            showAlert(decodeAlert, "error", e.message);
            setStatus("Failed", "st-err");
        }
        decodeEmpty.style.display = "block";
    } finally {
        setButtonIdle(decodeBtn, "Extract & Verify Payload");
    }
});