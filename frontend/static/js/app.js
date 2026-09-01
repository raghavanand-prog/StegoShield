/* StegoShield shared chrome: model-status pill, mobile sidebar,
   dropzone/file-state helpers, safe alert rendering, formatting utils.
   All dynamic values rendered via textContent - never innerHTML
   interpolation of API responses, filenames, or error messages. */

// ---- Mobile sidebar drawer ------------------------------------------------
(function initMobileNav() {
    const shell = document.getElementById("app-shell");
    const openBtn = document.querySelector("[data-sidebar-open]");
    if (!shell || !openBtn) return;

    const closeEls = document.querySelectorAll("[data-sidebar-close]");
    const sidebar = document.getElementById("sidebar");

    function setOpen(open) {
        shell.classList.toggle("sidebar-open", open);
        openBtn.setAttribute("aria-expanded", String(open));
        document.body.style.overflow = open ? "hidden" : "";
        if (open && sidebar) sidebar.focus({ preventScroll: true });
    }
    openBtn.addEventListener("click", () => setOpen(true));
    closeEls.forEach((el) => el.addEventListener("click", () => setOpen(false)));

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && shell.classList.contains("sidebar-open")) setOpen(false);
    });
    if (sidebar) {
        sidebar.addEventListener("keydown", (e) => {
            if (e.key === "Tab" && !sidebar.contains(document.activeElement)) setOpen(false);
        });
    }
    if (window.matchMedia) {
        const mq = window.matchMedia("(min-width: 901px)");
        const onChange = (e) => e.matches && setOpen(false);
        if (mq.addEventListener) mq.addEventListener("change", onChange);
        else if (mq.addListener) mq.addListener(onChange);
    }
})();

// ---- Model-status pill -----------------------------------------------------
(async function initStatusPill() {
    const pill = document.getElementById("model-status-pill");
    if (!pill) return;
    try {
        const status = await StegoAPI.get("/model-status");
        pill.textContent = "";
        const dot = document.createElement("span");
        const label = document.createElement("span");
        if (status.trained) {
            dot.className = "status-dot status-dot-ok";
            label.textContent = `Model ready · ${(status.test_accuracy * 100).toFixed(1)}% test acc`;
        } else {
            dot.className = "status-dot status-dot-bad";
            label.textContent = "Model not trained";
        }
        pill.appendChild(dot);
        pill.appendChild(label);
    } catch (e) {
        pill.textContent = "";
        const dot = document.createElement("span");
        dot.className = "status-dot status-dot-bad";
        const label = document.createElement("span");
        label.textContent = "Status unavailable";
        pill.appendChild(dot);
        pill.appendChild(label);
    }
})();

// ---- Formatting / classification helpers -----------------------------------
function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function riskBadgeClass(level) {
    const map = { LOW: "badge-low", MEDIUM: "badge-medium", HIGH: "badge-high", CRITICAL: "badge-critical" };
    return map[level] || "badge-neutral";
}

function riskProgressClass(level) {
    const map = { LOW: "risk-low", MEDIUM: "risk-medium", HIGH: "risk-high", CRITICAL: "risk-critical" };
    return map[level] || "";
}

// ---- Dropzone ---------------------------------------------------------------
function setupDropzone(dropzoneEl, inputEl, onFile, opts = {}) {
    const onClear = opts.onClear || (() => {});

    dropzoneEl.addEventListener("click", () => inputEl.click());
    dropzoneEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputEl.click();
        }
    });

    inputEl.addEventListener("change", () => {
        if (inputEl.files.length) onFile(inputEl.files[0]);
    });

    ["dragover", "dragenter"].forEach((evt) =>
        dropzoneEl.addEventListener(evt, (e) => {
            e.preventDefault();
            dropzoneEl.classList.add("dragover");
        })
    );
    ["dragleave", "drop"].forEach((evt) =>
        dropzoneEl.addEventListener(evt, (e) => {
            e.preventDefault();
            dropzoneEl.classList.remove("dragover");
        })
    );
    dropzoneEl.addEventListener("drop", (e) => {
        const file = e.dataTransfer.files[0];
        if (file) {
            inputEl.files = e.dataTransfer.files;
            onFile(file);
        }
    });

    const clearBtn = dropzoneEl.querySelector(".file-clear");
    if (clearBtn) {
        clearBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            inputEl.value = "";
            renderFileState(dropzoneEl, null);
            onClear();
        });
    }
}

// Client-side quick metadata (real, read from the actual file object).
function getImageMeta(file) {
    return new Promise((resolve) => {
        const ext = (file.name.split(".").pop() || "image").toUpperCase();
        const base = { width: null, height: null, format: ext, size: file.size };
        if (!file.type.startsWith("image/")) {
            resolve(base);
            return;
        }
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = () => {
            URL.revokeObjectURL(url);
            resolve({ width: img.naturalWidth, height: img.naturalHeight, format: ext, size: file.size });
        };
        img.onerror = () => {
            URL.revokeObjectURL(url);
            resolve(base);
        };
        img.src = url;
    });
}

function renderFileState(dropzoneEl, file) {
    const placeholder = dropzoneEl.querySelector(".upload-placeholder");
    const state = dropzoneEl.querySelector(".file-state");
    if (!state) return;
    const nameEl = state.querySelector(".file-state-name-text");
    const metaEl = state.querySelector(".file-state-meta");

    if (!file) {
        if (placeholder) placeholder.style.display = "";
        state.style.display = "none";
        return;
    }
    if (placeholder) placeholder.style.display = "none";
    state.style.display = "flex";
    if (nameEl) nameEl.textContent = file.name;
    if (metaEl) metaEl.textContent = `${formatBytes(file.size)} · reading metadata…`;

    getImageMeta(file).then((meta) => {
        if (!metaEl) return;
        const parts = [];
        if (meta.width && meta.height) parts.push(`${meta.width} × ${meta.height} px`);
        parts.push(meta.format);
        parts.push(formatBytes(meta.size));
        metaEl.textContent = parts.join(" · ");
    });
}

// ---- Button busy states -----------------------------------------------------
function setButtonBusy(btn, busyText) {
    if (!btn) return;
    btn.dataset.idleLabel = btn.getAttribute("data-idle-label") || btn.textContent;
    btn.disabled = true;
    btn.classList.add("is-busy");
    btn.textContent = "";
    const sp = document.createElement("span");
    sp.className = "spinner";
    sp.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.textContent = busyText;
    btn.appendChild(sp);
    btn.appendChild(label);
}

function setButtonIdle(btn, label) {
    if (!btn) return;
    btn.disabled = false;
    btn.classList.remove("is-busy");
    btn.textContent = label || btn.dataset.idleLabel || btn.getAttribute("data-idle-label") || "";
}

// ---- Safe alerts -------------------------------------------------------------
// Error messages can echo back attacker-influenced input (e.g. an uploaded
// file's client-supplied filename/extension), so they are rendered as plain
// text (`textContent`), never parsed as markup.
function showAlert(container, type, message) {
    if (!container) return;
    container.textContent = "";
    const div = document.createElement("div");
    div.className = `alert alert-${type}`;
    div.role = "alert";
    div.textContent = message;
    container.appendChild(div);
}

function clearAlert(container) {
    if (container) container.textContent = "";
}
// ---- SHA-256 (used by the Decode page for the extracted payload) -------------
async function sha256Hex(text) {
    if (!window.crypto || !crypto.subtle) return null;
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
}

// ---- Clipboard helper ----------------------------------------------------------
function setupCopyButton(btn, text) {
    if (!btn) return;
    btn.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(text);
            btn.textContent = "Copied";
            btn.classList.add("copied");
            setTimeout(() => {
                btn.textContent = "Copy";
                btn.classList.remove("copied");
            }, 1600);
        } catch (e) {
            btn.textContent = "Failed";
        }
    });
}