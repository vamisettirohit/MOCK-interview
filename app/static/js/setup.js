/**
 * Mock Interview AI — Interview Setup Wizard Client Handler
 * Connects wizard to POST /api/interviews with real-time AI generation feedback,
 * validation for branch, role, experience, category, difficulty, duration, and question count.
 */
document.addEventListener("DOMContentLoaded", () => {
  const setupForm = document.getElementById("interview-setup-form");
  const submitBtn = document.getElementById("start-session-btn");
  const btnSpinner = document.getElementById("setup-spinner");
  const btnText = document.getElementById("setup-btn-text");
  const errorAlert = document.getElementById("setup-error-alert");
  const errorText = document.getElementById("setup-error-text");

  const customBranchWrapper = document.getElementById("custom-branch-wrapper");
  const customBranchInput = document.getElementById("custom_branch_input");
  const customRoleWrapper = document.getElementById("custom-role-wrapper");
  const customRoleInput = document.getElementById("custom_role_input");

  // Visual selection toggling for branch cards
  document.querySelectorAll(".branch-card input[type='radio']").forEach((radio) => {
    radio.addEventListener("change", () => {
      document.querySelectorAll(".branch-card").forEach((card) => card.classList.remove("selected"));
      radio.closest(".branch-card").classList.add("selected");
      if (radio.value === "Other") {
        if (customBranchWrapper) customBranchWrapper.style.display = "block";
        if (customBranchInput) customBranchInput.focus();
      } else {
        if (customBranchWrapper) customBranchWrapper.style.display = "none";
      }
    });
  });

  // Visual selection toggling for role cards
  document.querySelectorAll(".role-card input[type='radio']").forEach((radio) => {
    radio.addEventListener("change", () => {
      document.querySelectorAll(".role-card").forEach((card) => card.classList.remove("selected"));
      radio.closest(".role-card").classList.add("selected");
      if (radio.value === "Custom") {
        if (customRoleWrapper) customRoleWrapper.style.display = "block";
        if (customRoleInput) customRoleInput.focus();
      } else {
        if (customRoleWrapper) customRoleWrapper.style.display = "none";
      }
    });
  });

  // Visual selection toggling for experience level buttons
  document.querySelectorAll(".exp-btn input[type='radio']").forEach((radio) => {
    radio.addEventListener("change", () => {
      document.querySelectorAll(".exp-btn").forEach((btn) => btn.classList.remove("selected"));
      radio.closest(".exp-btn").classList.add("selected");
    });
  });

  // Visual selection toggling for category cards
  document.querySelectorAll(".category-card input[type='radio']").forEach((radio) => {
    radio.addEventListener("change", () => {
      document.querySelectorAll(".category-card").forEach((card) => card.classList.remove("selected"));
      radio.closest(".category-card").classList.add("selected");
    });
  });

  // Visual selection toggling for difficulty buttons
  document.querySelectorAll(".difficulty-btn input[type='radio']").forEach((radio) => {
    radio.addEventListener("change", () => {
      document.querySelectorAll(".difficulty-btn").forEach((btn) => btn.classList.remove("selected"));
      radio.closest(".difficulty-btn").classList.add("selected");
    });
  });

  function showError(msg) {
    if (errorAlert && errorText) {
      errorText.textContent = msg;
      errorAlert.style.display = "flex";
      errorAlert.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function clearError() {
    if (errorAlert) errorAlert.style.display = "none";
  }

  if (setupForm && submitBtn) {
    setupForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearError();

      const selectedBranchEl = setupForm.querySelector("input[name='branch']:checked");
      const selectedRoleRadio = setupForm.querySelector("input[name='job_role_radio']:checked");
      const selectedExpEl = setupForm.querySelector("input[name='experience_level']:checked");
      const selectedCatEl = setupForm.querySelector("input[name='category']:checked");
      const selectedDiffEl = setupForm.querySelector("input[name='difficulty']:checked");

      const numQuestionsSelect = document.getElementById("num_questions");
      const durationSelect = document.getElementById("duration");
      const topicInput = document.getElementById("topic");

      if (!selectedBranchEl) {
        showError("Please select your engineering branch.");
        return;
      }

      let branch = selectedBranchEl.value;
      if (branch === "Other") {
        const customBranch = customBranchInput ? customBranchInput.value.trim() : "";
        if (!customBranch) {
          showError("Please enter your specialized engineering branch.");
          if (customBranchInput) customBranchInput.focus();
          return;
        }
        branch = customBranch;
      }

      if (!selectedRoleRadio) {
        showError("Please select your target job role.");
        return;
      }

      let jobRole = selectedRoleRadio.value;
      if (jobRole === "Custom") {
        const customRole = customRoleInput ? customRoleInput.value.trim() : "";
        if (!customRole) {
          showError("Please enter your custom target job role.");
          if (customRoleInput) customRoleInput.focus();
          return;
        }
        jobRole = customRole;
      }

      if (!selectedExpEl) {
        showError("Please select your experience level.");
        return;
      }

      if (!selectedCatEl) {
        showError("Please select an interview category.");
        return;
      }

      if (!selectedDiffEl) {
        showError("Please select a target difficulty level.");
        return;
      }

      const totalQuestions = parseInt(numQuestionsSelect ? numQuestionsSelect.value : 3, 10);
      const durationMinutes = parseInt(durationSelect ? durationSelect.value : 15, 10);
      const topic = topicInput ? topicInput.value.trim() : "";

      const payload = {
        branch: branch,
        job_role: jobRole,
        experience_level: selectedExpEl.value,
        category: selectedCatEl.value,
        difficulty: selectedDiffEl.value,
        total_questions: totalQuestions,
        duration_minutes: durationMinutes,
        topic: topic
      };

      // Disable button & show AI formulation spinner
      submitBtn.disabled = true;
      if (btnSpinner) btnSpinner.style.display = "inline-block";
      if (btnText) btnText.textContent = "Groq AI is preparing Question 1...";

      try {
        const response = await fetch("/api/interviews", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
          },
          body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (response.ok && data.success && data.interview && data.interview.id) {
          if (btnText) btnText.textContent = "Entering Interview Room...";
          window.location.href = `/interview/session/${data.interview.id}`;
        } else {
          // Restore button state on error
          submitBtn.disabled = false;
          if (btnSpinner) btnSpinner.style.display = "none";
          if (btnText) btnText.textContent = "Generate Questions & Begin Interview →";
          showError(data.error || "Failed to initialize interview. Please try again.");
        }
      } catch (err) {
        submitBtn.disabled = false;
        if (btnSpinner) btnSpinner.style.display = "none";
        if (btnText) btnText.textContent = "Generate Questions & Begin Interview →";
        showError("A network error occurred while communicating with the server. Please check your connection.");
      }
    });
  }
});
