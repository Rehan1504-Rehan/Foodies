/* ==========================================================================
   FOODIES front-end behaviour
   - AJAX cart operations (server still prices everything)
   - toasts, modals, sidebar, quantity steppers, live order tracking
   ========================================================================== */
(function () {
  "use strict";

  const FOODIES = window.FOODIES || {};
  const csrfToken = () => {
    const match = document.cookie.match(/(^|;)\s*csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[2]) : (FOODIES.csrfToken || "");
  };

  /* ------------------------------------------------------------- toasts */
  function toast(message, type = "success", timeout = 3800) {
    let stack = document.querySelector(".fd-toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "fd-toast-stack";
      document.body.appendChild(stack);
    }
    const icons = { success: "bi-check-circle-fill", error: "bi-exclamation-octagon-fill", warning: "bi-exclamation-triangle-fill", info: "bi-info-circle-fill" };
    const el = document.createElement("div");
    el.className = `fd-toast ${type}`;
    el.setAttribute("role", "status");
    el.innerHTML = `<i class="bi ${icons[type] || icons.info}"></i><div class="flex-grow-1 small fw-semibold">${message}</div>
      <button class="btn-close" aria-label="Close"></button>`;
    el.querySelector(".btn-close").addEventListener("click", () => el.remove());
    stack.appendChild(el);
    setTimeout(() => el.remove(), timeout);
  }
  window.foodiesToast = toast;

  /* ---------------------------------------------------------- ajax util */
  async function post(url, data = {}) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams(data).toString(),
      credentials: "same-origin",
    });
    let payload = {};
    try { payload = await response.json(); } catch (e) { payload = { ok: false, message: "Unexpected server response." }; }
    return { ok: response.ok, status: response.status, payload };
  }

  /* ------------------------------------------------------- money format */
  function money(value) {
    const n = Number(value || 0);
    return `${FOODIES.currency || "₹"}${n.toFixed(2)}`;
  }

  function updateCartBadges(count) {
    document.querySelectorAll("[data-cart-count]").forEach((el) => {
      el.textContent = count;
      el.classList.toggle("d-none", !count);
    });
  }

  function applyPricing(pricing) {
    if (!pricing) return;
    document.querySelectorAll("[data-price]").forEach((el) => {
      const key = el.dataset.price;
      if (pricing[key] !== undefined && pricing[key] !== null) {
        el.textContent = key === "item_count" ? pricing[key] : money(pricing[key]);
      }
    });
  }

  /* --------------------------------------------------------- add to cart */
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-add-to-cart]");
    if (!button) return;
    event.preventDefault();
    if (button.dataset.requiresAuth === "1") {
      window.location.href = FOODIES.loginUrl || "/accounts/login/";
      return;
    }
    const url = button.dataset.addToCart;
    button.disabled = true;
    const original = button.innerHTML;
    button.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    const { ok, payload } = await post(url, { quantity: button.dataset.quantity || 1 });
    button.disabled = false;
    if (ok && payload.ok) {
      button.innerHTML = original;
      updateCartBadges(payload.cart_count);
      applyPricing(payload.pricing);
      toast(payload.message || "Added to cart", "success");
      document.querySelectorAll(`[data-qty-for="${payload.food_item_id || button.dataset.foodId}"]`).forEach((el) => {
        el.classList.remove("d-none");
      });
      const counter = document.querySelector(`[data-qty-value="${button.dataset.foodId}"]`);
      if (counter) counter.textContent = payload.quantity;
      const wrap = document.querySelector(`[data-qty-wrap="${button.dataset.foodId}"]`);
      if (wrap) { wrap.classList.remove("d-none"); button.classList.add("d-none"); }
    } else {
      button.innerHTML = original;
      toast(payload.message || payload.detail || "Could not add this item.", "error");
    }
  });

  /* ------------------------------------------------- quantity plus/minus */
  document.addEventListener("click", async (event) => {
    const control = event.target.closest("[data-cart-qty]");
    if (!control) return;
    event.preventDefault();
    const foodId = control.dataset.foodId;
    const action = control.dataset.cartQty; // increase | decrease
    const { ok, payload } = await post(`/cart/update/${foodId}/`, { action });
    if (!ok || !payload.ok) {
      toast(payload.message || "Could not update the cart.", "error");
      return;
    }
    updateCartBadges(payload.cart_count);
    applyPricing(payload.pricing);
    const counter = document.querySelector(`[data-qty-value="${foodId}"]`);
    if (payload.removed) {
      const wrap = document.querySelector(`[data-qty-wrap="${foodId}"]`);
      const addBtn = document.querySelector(`[data-add-to-cart][data-food-id="${foodId}"]`);
      if (wrap) wrap.classList.add("d-none");
      if (addBtn) addBtn.classList.remove("d-none");
      const row = document.querySelector(`[data-cart-row="${foodId}"]`);
      if (row) row.remove();
      if (!document.querySelector("[data-cart-row]")) window.location.reload();
    } else if (counter) {
      counter.textContent = payload.quantity;
    }
    const lineTotal = document.querySelector(`[data-line-total="${foodId}"]`);
    if (lineTotal && payload.line_total !== undefined) lineTotal.textContent = money(payload.line_total);
  });

  /* ------------------------------------------------------- favourite toggles */
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-favorite-url]");
    if (!button) return;
    event.preventDefault();
    if (button.dataset.requiresAuth === "1") {
      window.location.href = FOODIES.loginUrl || "/accounts/login/";
      return;
    }
    const { ok, payload } = await post(button.dataset.favoriteUrl);
    if (!ok || !payload.ok) {
      toast(payload.message || "Could not update favourites.", "error");
      return;
    }
    button.classList.toggle("active", payload.favorited);
    const icon = button.querySelector("i");
    if (icon) icon.className = `bi ${payload.favorited ? "bi-heart-fill" : "bi-heart"}`;
    toast(payload.message, "success");
  });

  /* --------------------------------------------------- confirm modals */
  document.addEventListener("submit", (event) => {
    const form = event.target.closest("form[data-confirm]");
    if (!form || form.dataset.confirmed === "1") return;
    event.preventDefault();
    openConfirm(form.dataset.confirm, form.dataset.confirmTitle || "Please confirm", () => {
      form.dataset.confirmed = "1";
      form.submit();
    });
  });

  function openConfirm(message, title, onConfirm) {
    let modalEl = document.getElementById("fdConfirmModal");
    if (!modalEl) {
      modalEl = document.createElement("div");
      modalEl.id = "fdConfirmModal";
      modalEl.className = "modal fade";
      modalEl.innerHTML = `
        <div class="modal-dialog modal-dialog-centered modal-sm">
          <div class="modal-content rounded-2xl border-0">
            <div class="modal-body p-4 text-center">
              <div class="fd-empty-icon mx-auto mb-3" style="width:72px;height:72px;font-size:1.8rem">⚠️</div>
              <h5 class="fw-bold mb-2" data-confirm-title></h5>
              <p class="text-muted-2 small mb-4" data-confirm-message></p>
              <div class="d-flex gap-2">
                <button class="btn btn-light w-50 rounded-pill" data-bs-dismiss="modal">Cancel</button>
                <button class="btn btn-brand w-50" data-confirm-ok>Confirm</button>
              </div>
            </div>
          </div>
        </div>`;
      document.body.appendChild(modalEl);
    }
    modalEl.querySelector("[data-confirm-title]").textContent = title;
    modalEl.querySelector("[data-confirm-message]").textContent = message;
    const okButton = modalEl.querySelector("[data-confirm-ok]");
    const clone = okButton.cloneNode(true);
    okButton.replaceWith(clone);
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    clone.addEventListener("click", () => { modal.hide(); onConfirm(); });
    modal.show();
  }
  window.foodiesConfirm = openConfirm;

  /* ------------------------------------------------------- sidebar toggle */
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-sidebar-toggle]")) {
      document.querySelector(".fd-sidebar")?.classList.toggle("open");
      document.querySelector(".fd-backdrop")?.classList.toggle("show");
    }
    if (event.target.closest(".fd-backdrop")) {
      document.querySelector(".fd-sidebar")?.classList.remove("open");
      document.querySelector(".fd-backdrop")?.classList.remove("show");
    }
  });

  /* ------------------------------------------------------ copy coupon code */
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy]");
    if (!button) return;
    event.preventDefault();
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      toast(`Coupon ${button.dataset.copy} copied — apply it at checkout!`, "success");
    } catch (e) {
      toast(`Coupon code: ${button.dataset.copy}`, "info");
    }
  });

  /* ----------------------------------------------------------- order tracking */
  const tracker = document.querySelector("[data-track-url]");
  if (tracker) {
    const pollMs = 15000;
    const render = (data) => {
      document.querySelectorAll("[data-track-status]").forEach((el) => { el.textContent = data.status_label; });
      const bar = document.querySelector("[data-track-progress]");
      if (bar) bar.style.width = `${data.progress}%`;
      const icons = { done: "bi-check-lg", cancelled: "bi-x-lg", current: "bi-record-circle", todo: "bi-circle" };
      document.querySelectorAll("[data-track-step]").forEach((el) => {
        const label = el.dataset.trackStep;
        const step = data.steps.find((s) => s.label === label);
        if (!step) return;
        el.className = step.state;
        const dot = el.querySelector(".fd-track-dot");
        if (dot) dot.innerHTML = `<i class="bi ${icons[step.state] || "bi-circle"}"></i>`;
      });
    };
    const tick = async () => {
      try {
        const response = await fetch(tracker.dataset.trackUrl, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });
        if (response.ok) render(await response.json());
      } catch (e) { /* offline — keep last known status */ }
    };
    setInterval(tick, pollMs);
  }

  /* --------------------------------------------------------- file previews */
  document.querySelectorAll("[data-image-input]").forEach((input) => {
    input.addEventListener("change", () => {
      const preview = document.querySelector(input.dataset.imageInput);
      if (preview && input.files && input.files[0]) {
        preview.src = URL.createObjectURL(input.files[0]);
        preview.classList.remove("d-none");
      }
    });
  });

  /* ---------------------------------------------- auto-dismiss server toasts */
  document.querySelectorAll(".fd-toast[data-autohide]").forEach((el) => {
    setTimeout(() => el.remove(), Number(el.dataset.autohide) || 4200);
  });

  /* ------------------------------------------------------- checkout helpers */
  const paymentInputs = document.querySelectorAll("[data-payment-method]");
  paymentInputs.forEach((input) => {
    input.addEventListener("change", () => {
      document.querySelectorAll("[data-payment-card]").forEach((card) => {
        card.classList.toggle("active", card.querySelector("input")?.checked);
      });
    });
  });

  /* ------------------------------------------------------------ password eye */
  document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-toggle-password]");
    if (!toggle) return;
    const input = document.querySelector(toggle.dataset.togglePassword);
    if (!input) return;
    input.type = input.type === "password" ? "text" : "password";
    toggle.querySelector("i")?.classList.toggle("bi-eye");
    toggle.querySelector("i")?.classList.toggle("bi-eye-slash");
  });

  document.dispatchEvent(new CustomEvent("foodies:ready"));
})();
