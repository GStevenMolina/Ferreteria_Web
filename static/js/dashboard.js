(function () {
  function readJsonScript(id) {
    const node = document.getElementById(id);
    if (!node) return [];
    try { return JSON.parse(node.textContent || "[]"); } catch (error) { return []; }
  }

  if (typeof Chart === "undefined") return;

  const topProductsLabels = readJsonScript("dashboard-top-products-labels");
  const topProductsValues = readJsonScript("dashboard-top-products-values");
  const flowLabels = readJsonScript("dashboard-flow-labels");
  const flowPurchases = readJsonScript("dashboard-flow-purchases");
  const flowSales = readJsonScript("dashboard-flow-sales");
  const categoryLabels = readJsonScript("dashboard-category-labels");
  const categoryValues = readJsonScript("dashboard-category-values");

  const sharedOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: "#e5e7eb", boxWidth: 12, boxHeight: 12 } },
      tooltip: { backgroundColor: "rgba(15, 23, 42, 0.95)", titleColor: "#fff", bodyColor: "#e5e7eb", borderColor: "rgba(255,255,255,.12)", borderWidth: 1 },
    },
  };

  const topProductsCanvas = document.getElementById("topProductsChart");
  if (topProductsCanvas) {
    new Chart(topProductsCanvas, {
      type: "bar",
      data: { labels: topProductsLabels, datasets: [{ label: "Unidades vendidas", data: topProductsValues, borderRadius: 10, backgroundColor: "rgba(56, 189, 248, 0.78)" }] },
      options: { ...sharedOptions, indexAxis: "y", scales: { x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148, 163, 184, 0.12)" } }, y: { ticks: { color: "#cbd5e1" }, grid: { display: false } } } },
    });
  }

  const flowCanvas = document.getElementById("flowChart");
  if (flowCanvas) {
    new Chart(flowCanvas, {
      type: "line",
      data: { labels: flowLabels, datasets: [{ label: "Compras", data: flowPurchases, borderColor: "#22c55e", backgroundColor: "rgba(34, 197, 94, 0.18)", tension: 0.35, fill: true }, { label: "Ventas", data: flowSales, borderColor: "#38bdf8", backgroundColor: "rgba(56, 189, 248, 0.12)", tension: 0.35, fill: true }] },
      options: { ...sharedOptions, scales: { x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148, 163, 184, 0.12)" } }, y: { ticks: { color: "#94a3b8", callback(value) { return `C$ ${value}`; } }, grid: { color: "rgba(148, 163, 184, 0.12)" } } } },
    });
  }

  const categoryCanvas = document.getElementById("categoryChart");
  if (categoryCanvas) {
    new Chart(categoryCanvas, {
      type: "doughnut",
      data: { labels: categoryLabels, datasets: [{ data: categoryValues, backgroundColor: ["#38bdf8", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#14b8a6", "#f97316"], borderColor: "rgba(2, 6, 23, 0.8)", borderWidth: 2 }] },
      options: { ...sharedOptions, cutout: "62%" },
    });
  }
})();