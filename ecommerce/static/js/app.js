(() => {
  "use strict";

  function showFeedback(target, message, kind = "danger") {
    if (!target) return;
    target.className = `alert alert-${kind} mt-2`;
    target.textContent = message;
  }

  async function submitCartForm(form) {
    const feedback = form.closest("section")?.querySelector(".cart-feedback") || document.getElementById("cart-feedback");
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
      handler.openIframe();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initializeCartForms();
    initializePaystack();
  });
})();
