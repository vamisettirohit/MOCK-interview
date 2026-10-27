/**
 * Mock Interview AI — Interview History Client Filtering & Search
 */
document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("history-search");
  const categoryFilter = document.getElementById("history-category-filter");
  const difficultyFilter = document.getElementById("history-difficulty-filter");
  const statusFilter = document.getElementById("history-status-filter");
  const rows = document.querySelectorAll(".history-row");
  const filteredCountEl = document.getElementById("history-filtered-count");
  const noMatchBox = document.getElementById("history-no-match");
  const resetBtn = document.getElementById("history-reset-filters");

  function filterRows() {
    const query = (searchInput ? searchInput.value : "").trim().toLowerCase();
    const cat = categoryFilter ? categoryFilter.value.toLowerCase() : "all";
    const diff = difficultyFilter ? difficultyFilter.value.toLowerCase() : "all";
    const status = statusFilter ? statusFilter.value.toLowerCase() : "all";

    let visibleCount = 0;

    rows.forEach((row) => {
      const rowCat = (row.getAttribute("data-category") || "").toLowerCase();
      const rowDiff = (row.getAttribute("data-difficulty") || "").toLowerCase();
      const rowStatus = (row.getAttribute("data-status") || "").toLowerCase();
      const rowText = row.textContent.toLowerCase();

      const matchesQuery = !query || rowText.includes(query);
      const matchesCat = cat === "all" || rowCat.includes(cat);
      const matchesDiff = diff === "all" || rowDiff === diff;
      const matchesStatus = status === "all" || rowStatus === status;

      if (matchesQuery && matchesCat && matchesDiff && matchesStatus) {
        row.style.display = "";
        visibleCount++;
      } else {
        row.style.display = "none";
      }
    });

    if (filteredCountEl) {
      filteredCountEl.textContent = `Showing ${visibleCount} of ${rows.length} sessions`;
    }

    if (noMatchBox) {
      noMatchBox.style.display = visibleCount === 0 && rows.length > 0 ? "block" : "none";
    }
  }

  if (searchInput) searchInput.addEventListener("input", filterRows);
  if (categoryFilter) categoryFilter.addEventListener("change", filterRows);
  if (difficultyFilter) difficultyFilter.addEventListener("change", filterRows);
  if (statusFilter) statusFilter.addEventListener("change", filterRows);

  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      if (searchInput) searchInput.value = "";
      if (categoryFilter) categoryFilter.value = "all";
      if (difficultyFilter) difficultyFilter.value = "all";
      if (statusFilter) statusFilter.value = "all";
      filterRows();
    });
  }

  // Initial count
  if (filteredCountEl) {
    filteredCountEl.textContent = `Showing ${rows.length} of ${rows.length} sessions`;
  }
});
