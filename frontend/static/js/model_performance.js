(async function loadModelPerformance() {
    let meta;
    try {
        meta = await StegoAPI.get("/model-performance");
    } catch (e) {
        return; // "not trained" alert already shown server-side
    }

    const primary = meta.primary_model;
    const test = meta.models[primary].test;

    document.getElementById("m-accuracy").textContent = `${(test.accuracy * 100).toFixed(1)}%`;
    document.getElementById("m-balanced-accuracy").textContent = `${(test.balanced_accuracy * 100).toFixed(1)}%`;
    document.getElementById("m-precision").textContent = `${(test.precision * 100).toFixed(1)}%`;
    document.getElementById("m-recall").textContent = `${(test.recall * 100).toFixed(1)}%`;
    document.getElementById("m-specificity").textContent = `${(test.specificity * 100).toFixed(1)}%`;
    document.getElementById("m-fpr").textContent = `${(test.false_positive_rate * 100).toFixed(1)}%`;
    document.getElementById("m-f1").textContent = `${(test.f1_score * 100).toFixed(1)}%`;
    document.getElementById("m-pr-auc").textContent = test.pr_auc !== null ? test.pr_auc.toFixed(3) : "n/a";

    document.getElementById("confusion-matrix-title").textContent =
        `Confusion Matrix — ${primary.replace(/_/g, " ")} (test set)`;

    const cm = test.confusion_matrix;
    renderTable(document.getElementById("confusion-table"), (table) => {
        table.appendChild(headerRow(["", "Predicted CLEAN", "Predicted STEGO"]));
        table.appendChild(row([strongCell("Actual CLEAN"), monoCell(cm.true_negative), monoCell(cm.false_positive)]));
        table.appendChild(row([strongCell("Actual STEGO"), monoCell(cm.false_negative), monoCell(cm.true_positive)]));
    });

    // ROC curve
    if (test.roc_curve) {
        const ctx = document.getElementById("roc-chart");
        new Chart(ctx, {
            type: "line",
            data: {
                labels: test.roc_curve.fpr.map((v) => v.toFixed(2)),
                datasets: [
                    {
                        label: `ROC (AUC=${test.roc_auc.toFixed(3)})`,
                        data: test.roc_curve.tpr,
                        borderColor: "#3b82f6",
                        backgroundColor: "rgba(59,130,246,0.1)",
                        fill: true,
                        tension: 0.15,
                        pointRadius: 0,
                    },
                    {
                        label: "Random baseline",
                        data: test.roc_curve.fpr,
                        borderColor: "#475569",
                        borderDash: [4, 4],
                        pointRadius: 0,
                        fill: false,
                    },
                ],
            },
            options: chartOptions("False Positive Rate", "True Positive Rate"),
        });
    }

    // Precision-Recall curve
    if (test.pr_curve) {
        new Chart(document.getElementById("pr-chart"), {
            type: "line",
            data: {
                labels: test.pr_curve.recall.map((v) => v.toFixed(2)),
                datasets: [
                    {
                        label: `PR (AUC=${test.pr_auc.toFixed(3)})`,
                        data: test.pr_curve.precision,
                        borderColor: "#06b6d4",
                        backgroundColor: "rgba(6,182,212,0.1)",
                        fill: true,
                        tension: 0.15,
                        pointRadius: 0,
                    },
                ],
            },
            options: chartOptions("Recall", "Precision"),
        });
    }

    // TPR at fixed FPR budget - the stated primary-model selection criterion.
    if (test.tpr_at_fpr) {
        renderTable(document.getElementById("tpr-fpr-table"), (table) => {
            table.appendChild(headerRow(["FPR budget", "Best achievable TPR (recall)"]));
            table.appendChild(row([monoCell("≤ 10%"), monoCell(`${(test.tpr_at_fpr.at_fpr_10 * 100).toFixed(1)}%`)]));
            table.appendChild(row([monoCell("≤ 20%"), monoCell(`${(test.tpr_at_fpr.at_fpr_20 * 100).toFixed(1)}%`)]));
        });
    }

    // Model comparison table
    renderTable(document.getElementById("comparison-table"), (table) => {
        table.appendChild(
            headerRow(["Model", "Accuracy", "Balanced Acc.", "Precision", "Recall", "FPR", "F1", "ROC-AUC", "PR-AUC"])
        );
        Object.entries(meta.models).forEach(([name, res]) => {
            const t = res.test;
            const auc = t.roc_auc !== null ? t.roc_auc.toFixed(3) : "n/a";
            const prAuc = t.pr_auc !== null ? t.pr_auc.toFixed(3) : "n/a";
            const isPrimary = name === primary;

            const nameCell = document.createElement("td");
            nameCell.appendChild(document.createTextNode(name.replace(/_/g, " ")));
            if (isPrimary) {
                nameCell.appendChild(document.createTextNode(" "));
                const badge = document.createElement("span");
                badge.className = "badge badge-primary";
                badge.textContent = "primary";
                nameCell.appendChild(badge);
            }

            table.appendChild(
                row([
                    nameCell,
                    monoCell(`${(t.accuracy * 100).toFixed(1)}%`),
                    monoCell(`${(t.balanced_accuracy * 100).toFixed(1)}%`),
                    monoCell(`${(t.precision * 100).toFixed(1)}%`),
                    monoCell(`${(t.recall * 100).toFixed(1)}%`),
                    monoCell(`${(t.false_positive_rate * 100).toFixed(1)}%`),
                    monoCell(`${(t.f1_score * 100).toFixed(1)}%`),
                    monoCell(auc),
                    monoCell(prAuc),
                ])
            );
        });
    });

    // Primary-model selection rationale, if the metadata carries it
    // (added when the model was last retrained via scripts/train_model.py).
    if (meta.primary_model_selection) {
        const sel = meta.primary_model_selection;
        document.getElementById("primary-model-rationale").textContent =
            `Selection criterion: ${sel.criterion} ${sel.rationale}`;
        document.getElementById("primary-model-rationale-section").hidden = false;
    }

    // Feature importance chart
    const top = meta.feature_importance.slice(0, 10);
    new Chart(document.getElementById("importance-chart"), {
        type: "bar",
        data: {
            labels: top.map((f) => f.feature),
            datasets: [
                {
                    label: "Importance",
                    data: top.map((f) => f.importance),
                    backgroundColor: "#06b6d4",
                },
            ],
        },
        options: {
            indexAxis: "y",
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: "#a8b3cc" }, grid: { color: "#1e2638" } },
                y: { ticks: { color: "#a8b3cc", font: { size: 10.5 } }, grid: { display: false } },
            },
        },
    });

    // Dataset details
    const split = meta.dataset_split;
    renderTable(document.getElementById("dataset-table"), (table) => {
        table.appendChild(headerRow(["Split", "Samples", "Clean", "Stego", "Source images"]));
        ["train", "val", "test"].forEach((k) => {
            table.appendChild(
                row([
                    textCell(k),
                    monoCell(split[k].samples),
                    monoCell(split[k].clean),
                    monoCell(split[k].stego),
                    textCell(split[k].source_images.join(", "), "text-dim"),
                ])
            );
        });
        table.appendChild(row([textCell("Feature count"), monoCell(meta.n_features, "mono", 4)]));
        table.appendChild(row([textCell("Trained at"), monoCell(meta.trained_at, "mono", 4)]));
        table.appendChild(row([textCell("Random seed"), monoCell(meta.seed, "mono", 4)]));
    });
})();

// ---- Safe table-building helpers (DOM APIs only, never innerHTML with
// interpolated values) ----------------------------------------------------
function renderTable(tableEl, builder) {
    tableEl.textContent = "";
    builder(tableEl);
}
function row(cells) {
    const tr = document.createElement("tr");
    cells.forEach((c) => tr.appendChild(c));
    return tr;
}
function headerRow(labels) {
    const tr = document.createElement("tr");
    labels.forEach((label) => {
        const th = document.createElement("th");
        th.textContent = label;
        tr.appendChild(th);
    });
    return tr;
}
function textCell(text, className) {
    const td = document.createElement("td");
    if (className) td.className = className;
    td.textContent = text;
    return td;
}
function monoCell(value, className = "mono", colspan) {
    const td = textCell(value, className);
    if (colspan) td.colSpan = colspan;
    return td;
}
function strongCell(text) {
    const td = document.createElement("td");
    const strong = document.createElement("strong");
    strong.textContent = text;
    td.appendChild(strong);
    return td;
}

function chartOptions(xLabel, yLabel) {
    return {
        plugins: { legend: { labels: { color: "#a8b3cc" } } },
        scales: {
            x: { title: { display: true, text: xLabel, color: "#a8b3cc" }, ticks: { color: "#a8b3cc" }, grid: { color: "#1e2638" } },
            y: { title: { display: true, text: yLabel, color: "#a8b3cc" }, ticks: { color: "#a8b3cc" }, grid: { color: "#1e2638" }, min: 0, max: 1 },
        },
    };
}
