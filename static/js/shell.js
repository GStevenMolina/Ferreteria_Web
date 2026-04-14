(function () {
  const sidebar = document.getElementById("sidebar");
  const btnToggle = document.getElementById("btnToggleMenu");
  if (!sidebar || !btnToggle) return;

  const savedCollapsed = localStorage.getItem("sidebarCollapsed") === "1";
  if (savedCollapsed) sidebar.classList.add("is-collapsed");
  btnToggle.title = savedCollapsed ? "Expandir menú" : "Plegar menú";

  btnToggle.addEventListener("click", () => {
    const collapsed = sidebar.classList.toggle("is-collapsed");
    localStorage.setItem("sidebarCollapsed", collapsed ? "1" : "0");
    btnToggle.title = collapsed ? "Expandir menú" : "Plegar menú";
  });
})();