const dzOriginal = document.getElementById("dropzone-original");
const fiOriginal = document.getElementById("file-original");
const previewOriginal = document.getElementById("preview-original");

const dzModified = document.getElementById("dropzone-modified");
const fiModified = document.getElementById("file-modified");
const previewModified = document.getElementById("preview-modified");

const compareBtn = document.getElementById("compare-btn");
const compareAlert = document.getElementById("compare-alert");
const resultsSection = document.getElementById("results-section");

let originalFile = null;
let modifiedFile = null;

function updateButton() {
    compareBtn.disabled = !(originalFile && modifiedFile);
}

setupDropzone(dzOriginal, fiOriginal, (file) => {
    originalFile = file;
    previewOriginal.src = URL.createObjectURL(file);
    previewOriginal.style.display = "block";
    renderFileState(dzOriginal, file);
    updateButton();
}, {
    onClear: () => {
        originalFile = null;
        previewOriginal.style.display = "none";
        previewOriginal.removeAttribute("src");
        updateButton();
    },
});

setupDropzone(dzModified, fiModified, (file) => {
    modifiedFile = file;
    previewModified.src = URL.createObjectURL(file);
    previewModified.style.display = "block";
    renderFileState(dzModified, file);
    updateButton();
}, {
    onClear: () => {
        modifiedFile = null;
        previewModified.style.display = "none";
        previewModified.removeAttribute("src");
        updateButton();
    },
});

compareBtn.addEventListener("click", async () => {
    setButtonBusy(compareBtn, "Comparing…");
    clearAlert(compareAlert);

    const formData = new FormData();
    formData.append("original", originalFile);
    formData.append("modified", modifiedFile);

    try {
        const result = await StegoAPI.postForm("/image-analysis", formData);
        renderResults(result);
    } catch (e) {
        showAlert(compareAlert, "error", e.message);
    } finally {
        setButtonIdle(compareBtn, "Compare Images");
        updateButton();
    }
});

function renderResults(result) {
    resultsSection.style.display = "block";
    document.getElementById("q-mse").textContent = result.quality.mse;
    document.getElementById("q-psnr").textContent = result.quality.psnr_display;
    document.getElementById("q-ssim").textContent = result.quality.ssim;

    // Real dimension info from the client-side File objects(
    // same source the upload widgets already use for their metadata line).
    const origMeta = document.getElementById("meta-original");
    if (origMeta && originalFile) {
        origMeta.textContent = `${originalFile.name} · ${formatBytes(originalFile.size)}`;
    }
    const modMeta = document.getElementById("meta-modified");
    if (modMeta && modifiedFile) {
        modMeta.textContent = `${modifiedFile.name} · ${formatBytes(modifiedFile.size)}`;
    }

    const va = result.visual_analysis;
    document.getElementById("img-original").src = `data:image/png;base64,${va.original_png_b64}`;
    document.getElementById("img-modified").src = `data:image/png;base64,${va.stego_png_b64}`;
    document.getElementById("img-diff").src = `data:image/png;base64,${va.difference_png_b64}`;
    document.getElementById("img-hist").src = `data:image/png;base64,${va.histogram_png_b64}`;

    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}