(() => {
  "use strict";

  function showFeedback(target, message, kind = "danger") {
    if (!target) return;
    target.className = `alert alert-${kind} mt-2`;
    target.textContent = message;
  }

  async function submitCartForm(form) {
    const feedback = form.closest("section")?.querySelector(".cart-feedback") || document.getElementById("cart-feedback");
    if (form.getAttribute("aria-busy") === "true") return;
    const submitButton = form.querySelector('[type="submit"]');
    form.setAttribute("aria-busy", "true");
    if (submitButton) submitButton.disabled = true;
    try {
      const response = await fetch(form.dataset.url || form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "The cart could not be updated.");
      const badge = document.getElementById("cart_qty");
      if (badge && payload.qty !== undefined) badge.textContent = payload.qty;
      if (form.classList.contains("cart-add-form")) {
        showFeedback(feedback, "Item added to your cart.", "success");
      } else {
        window.location.reload();
      }
    } catch (error) {
      showFeedback(feedback, error.message || "The cart could not be updated.");
    } finally {
      form.removeAttribute("aria-busy");
      if (submitButton) submitButton.disabled = false;
    }
  }

  function initializeCartForms() {
    document.querySelectorAll("[data-cart-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        submitCartForm(form);
      });
    });
  }

  function initializePaystack() {
    const button = document.getElementById("paystack-button");
    if (!button) return;
    button.addEventListener("click", () => {
      const feedback = document.getElementById("payment-feedback");
      if (!window.PaystackPop) {
        showFeedback(feedback, "The secure payment dialog could not load. Please refresh and try again.");
        return;
      }
      const amount = Number.parseInt(button.dataset.amount, 10);
      if (!button.dataset.key || !button.dataset.reference || !Number.isInteger(amount)) {
        showFeedback(feedback, "This payment cannot be initialized safely.");
        return;
      }
      try {
        const handler = window.PaystackPop.setup({
          key: button.dataset.key,
          email: button.dataset.email,
          amount,
          ref: button.dataset.reference,
          onClose: () => { window.location.assign(button.dataset.pendingUrl); },
          callback: () => {
            const verificationForm = document.getElementById("verification-form");
            if (verificationForm) verificationForm.submit();
          },
        });
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
        handler.openIframe();
      } catch (error) {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        showFeedback(feedback, "The secure payment dialog could not open. Please refresh and try again.");
      }
    });
  }

  function initializeAutoSubmit() {
    document.querySelectorAll("[data-auto-submit]").forEach((control) => {
      control.addEventListener("change", () => control.form?.submit());
    });
  }

  function initializeGalleryThumbnails() {
    document.querySelectorAll(".gallery-thumbnail").forEach((button) => {
      button.addEventListener("click", () => {
        button.parentElement?.querySelectorAll(".gallery-thumbnail").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initializeCartForms();
    initializePaystack();
    initializeAutoSubmit();
    initializeGalleryThumbnails();
  });
})();
