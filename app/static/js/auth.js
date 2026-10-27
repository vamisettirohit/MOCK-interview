/**
 * Mock Interview AI — Authentication Client Handler
 * Provides client-side validation, pending states, password toggling, and duplicate-submit prevention.
 */
document.addEventListener("DOMContentLoaded", () => {
  // 1. Password Visibility Toggle
  const toggleButtons = document.querySelectorAll(".password-toggle-btn");
  toggleButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-target");
      const input = document.getElementById(targetId);
      if (input) {
        const isPassword = input.getAttribute("type") === "password";
        input.setAttribute("type", isPassword ? "text" : "password");
        btn.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
        btn.innerHTML = isPassword ? "👁️‍🗨️" : "👁️";
      }
    });
  });

  // 2. Client-side Form Validation & Double-Submission Prevention
  const authForm = document.getElementById("auth-form");
  const submitBtn = document.getElementById("auth-submit-btn");
  const errorAlert = document.getElementById("auth-error-alert");
  const errorText = document.getElementById("auth-error-text");

  function showError(msg) {
    if (errorAlert && errorText) {
      errorText.textContent = msg;
      errorAlert.style.display = "flex";
      errorAlert.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function clearError() {
    if (errorAlert) {
      errorAlert.style.display = "none";
    }
  }

  if (authForm && submitBtn) {
    authForm.addEventListener("submit", (e) => {
      clearError();
      const emailInput = document.getElementById("email");
      const passwordInput = document.getElementById("password");
      const confirmInput = document.getElementById("confirm_password");
      const nameInput = document.getElementById("name");

      // Validate Name if on register page
      if (nameInput) {
        const nameVal = nameInput.value.trim();
        if (nameVal.length < 2) {
          e.preventDefault();
          showError("Full name must be at least 2 characters long.");
          nameInput.focus();
          return;
        }
      }

      // Validate Email
      if (emailInput) {
        const emailVal = emailInput.value.trim();
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(emailVal)) {
          e.preventDefault();
          showError("Please enter a valid email address.");
          emailInput.focus();
          return;
        }
      }

      // Validate Password length
      if (passwordInput) {
        const passVal = passwordInput.value;
        if (passVal.length < 6) {
          e.preventDefault();
          showError("Password must be at least 6 characters long.");
          passwordInput.focus();
          return;
        }
      }

      // Validate Confirm Password if present
      if (confirmInput && passwordInput) {
        if (passwordInput.value !== confirmInput.value) {
          e.preventDefault();
          showError("Passwords do not match. Please verify.");
          confirmInput.focus();
          return;
        }
      }

      // Prevent duplicate submissions while form is submitting
      if (submitBtn.disabled) {
        e.preventDefault();
        return;
      }

      submitBtn.disabled = true;
      const originalText = submitBtn.getAttribute("data-original-text") || submitBtn.textContent;
      submitBtn.setAttribute("data-original-text", originalText);

      const spinner = submitBtn.querySelector(".btn-spinner");
      const btnText = submitBtn.querySelector(".btn-text");

      if (spinner) spinner.style.display = "inline-block";
      if (btnText) {
        btnText.textContent = nameInput ? "Creating Account..." : "Signing In...";
      } else {
        submitBtn.textContent = nameInput ? "Creating Account..." : "Signing In...";
      }
    });
  }
});
