(async function loadRecentActivity() {
    const el = document.getElementById("recent-activity");
    try {
        const data = await StegoAPI.get("/recent-activity");
        el.textContent = "";

        if (!data.activity.length) {
            const p = document.createElement("p");
            p.className = "text-dim";
            p.textContent = "No analyses run yet this session. Try the Encode or Steganalysis pages.";
            el.appendChild(p);
            return;
        }

        // Built with DOM APIs rather than innerHTML-with-interpolation, even
        // though these fields are all server-computed / fixed-vocabulary
        // (operation name, risk level, prediction, dimensions, timestamp) —
        // never raw user input — to keep every API-response-driven render
        // in this app on the same safe pattern.
        const table = document.createElement("table");
        table.className = "data-table";
        const thead = document.createElement("thead");
        thead.innerHTML = "<tr><th>Operation</th><th>Image</th><th>Time</th></tr>";
        table.appendChild(thead);

        const tbody = document.createElement("tbody");
        data.activity.forEach((item) => {
            const tr = document.createElement("tr");

            const tdOp = document.createElement("td");
            const badge = document.createElement("span");
            if (item.operation === "STEGANALYSIS") {
                badge.className = `badge ${riskBadgeClass(item.risk_level)}`;
                badge.textContent = item.prediction;
            } else {
                badge.className = "badge badge-neutral";
                badge.textContent = item.operation;
            }
            tdOp.appendChild(badge);
            tr.appendChild(tdOp);

            const tdImg = document.createElement("td");
            tdImg.className = "mono";
            tdImg.textContent = item.image_dimensions ? `${item.image_dimensions}px` : "";
            tr.appendChild(tdImg);

            const tdTime = document.createElement("td");
            tdTime.className = "text-dim";
            tdTime.textContent = item.timestamp;
            tr.appendChild(tdTime);

            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        el.appendChild(table);
    } catch (e) {
        el.textContent = "";
        const p = document.createElement("p");
        p.className = "text-dim";
        p.textContent = "Unable to load recent activity.";
        el.appendChild(p);
    }
})();
