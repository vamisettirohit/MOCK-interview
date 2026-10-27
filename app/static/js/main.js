// Main Global Scripts for Mock Interview AI
document.addEventListener("DOMContentLoaded", () => {
  // Alert dismiss buttons
  const alertCloses = document.querySelectorAll(".alert-close");
  alertCloses.forEach(btn => {
    btn.addEventListener("click", () => {
      const alert = btn.closest(".alert");
      if (alert) {
        alert.style.opacity = "0";
        alert.style.transform = "translateY(-8px)";
        alert.style.transition = "all 200ms ease";
        setTimeout(() => alert.remove(), 200);
      }
    });
  });

  // Auto-dismiss success flash messages after 5 seconds
  const autoAlerts = document.querySelectorAll(".alert-success, .alert-info");
  autoAlerts.forEach(alert => {
    setTimeout(() => {
      if (alert && alert.parentElement) {
        alert.style.opacity = "0";
        alert.style.transition = "opacity 300ms ease";
        setTimeout(() => alert.remove(), 300);
      }
    }, 5000);
  });
});
