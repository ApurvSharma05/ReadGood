// ReadGood front-end behaviour: plain JavaScript on top of Bootstrap.
// Every feature here enhances a page that already works without it.
(function () {
  "use strict";

  const root = document.documentElement;
  const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- Theme ---------- */
  function syncTheme() {
    const dark = root.getAttribute("data-bs-theme") === "dark";
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.querySelector("i").className = dark ? "bi bi-sun" : "bi bi-moon";
      button.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
    });
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = dark ? "#11110f" : "#f4f1ea";
  }

  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-theme-toggle]")) return;
    const next = root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    const apply = () => {
      root.setAttribute("data-bs-theme", next);
      syncTheme();
    };
    try { localStorage.setItem("rg-theme", next); } catch (e) { /* storage blocked */ }
    if (document.startViewTransition && !reducedMotion()) {
      const transition = document.startViewTransition(apply);
      transition.ready.catch(() => {});
      transition.finished.catch(() => {});
    } else {
      apply();
    }
  });

  /* ---------- Covers: fade in, fall back to the typeset card ---------- */
  function settleImage(img) {
    if (!img.closest(".cover")) return;
    if (!img.complete) return;
    // Open Library answers a missing cover with a 1x1 pixel.
    if (img.naturalWidth <= 1) img.remove();
    else img.classList.add("is-loaded");
  }
  document.addEventListener("load", (event) => {
    if (event.target.tagName === "IMG") settleImage(event.target);
  }, true);
  document.addEventListener("error", (event) => {
    const img = event.target;
    if (img.tagName !== "IMG") return;
    if (img.closest(".cover")) img.remove();
    else if (img.closest(".suggest-item")) img.style.visibility = "hidden";
  }, true);

  /* ---------- Toasts ---------- */
  const TOAST_ICONS = { success: "bi-check-circle-fill", error: "bi-exclamation-circle-fill", info: "bi-info-circle-fill" };

  function showToast(message, type) {
    const stack = document.getElementById("toasts");
    if (!stack || !window.bootstrap) return;
    type = type || "info";
    const toast = document.createElement("div");
    toast.className = "toast toast-" + type;
    toast.setAttribute("role", "status");
    const body = document.createElement("div");
    body.className = "toast-body";
    const icon = document.createElement("i");
    icon.className = "bi " + (TOAST_ICONS[type] || TOAST_ICONS.info);
    icon.setAttribute("aria-hidden", "true");
    const text = document.createElement("span");
    text.textContent = message;
    const close = document.createElement("button");
    close.type = "button";
    close.className = "btn-close btn-close-sm";
    close.setAttribute("data-bs-dismiss", "toast");
    close.setAttribute("aria-label", "Close");
    body.append(icon, text, close);
    toast.append(body);
    while (stack.children.length >= 2) stack.firstElementChild.remove(); // keep the stack short
    stack.append(toast);
    toast.addEventListener("hidden.bs.toast", () => toast.remove());
    new bootstrap.Toast(toast, { delay: 3500 }).show();
  }

  /* ---------- Save to library without leaving the page ---------- */
  document.addEventListener("submit", async (event) => {
    const form = event.target.closest("form.js-save");
    if (!form) return;
    event.preventDefault();
    const button = form.querySelector("button");
    if (button.classList.contains("is-saved")) {
      showToast("Already in your library.", "info");
      return;
    }
    button.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "fetch", Accept: "application/json" },
        credentials: "same-origin",
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401 && data.login_url) {
        window.location.assign(data.login_url);
        return;
      }
      if (response.ok && data.ok) {
        button.classList.add("is-saved", "pulse");
        button.querySelector("i").className = "bi bi-bookmark-check-fill";
        button.setAttribute("aria-label", "In your library");
        button.title = "In your library";
        showToast(data.message, "success");
      } else {
        showToast(data.message || "That did not work. Please try again.", "error");
      }
    } catch (error) {
      showToast("You seem to be offline. Please try again.", "error");
    } finally {
      button.disabled = false;
    }
  });

  /* ---------- Auto-submitting selects and star ratings ---------- */
  document.addEventListener("change", (event) => {
    const field = event.target;
    if (field.matches("[data-autosubmit]") && field.form) field.form.requestSubmit();
  });

  /* ---------- Rails ---------- */
  function updateRail(rail) {
    const prev = document.querySelector('[data-rail-prev="' + rail.id + '"]');
    const next = document.querySelector('[data-rail-next="' + rail.id + '"]');
    const max = rail.scrollWidth - rail.clientWidth;
    if (prev) prev.disabled = rail.scrollLeft <= 4;
    if (next) next.disabled = rail.scrollLeft >= max - 4;
  }
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-rail-prev], [data-rail-next]");
    if (!button) return;
    const forward = button.hasAttribute("data-rail-next");
    const rail = document.getElementById(button.dataset.railNext || button.dataset.railPrev);
    if (rail) rail.scrollBy({ left: (forward ? 1 : -1) * rail.clientWidth * 0.8, behavior: reducedMotion() ? "auto" : "smooth" });
  });

  /* ---------- Search palette ---------- */
  function setupPalette() {
    const dialog = document.getElementById("searchDialog");
    if (!dialog || typeof dialog.showModal !== "function") return null;
    const form = dialog.querySelector("form");
    const input = form.querySelector("input");
    const hint = dialog.querySelector("[data-palette-hint]");
    const results = dialog.querySelector("[data-palette-results]");
    const endpoint = form.dataset.suggest;
    let timer = null;
    let controller = null;
    let active = -1;

    const options = () => Array.from(results.querySelectorAll("a"));
    const setActive = (index) => {
      const list = options();
      active = index;
      list.forEach((item, i) => {
        item.classList.toggle("is-active", i === index);
        item.setAttribute("aria-selected", i === index ? "true" : "false");
      });
      if (list[index]) list[index].scrollIntoView({ block: "nearest" });
    };
    const status = (text) => {
      results.replaceChildren();
      const p = document.createElement("p");
      p.className = "palette-status";
      p.textContent = text;
      results.append(p);
    };
    const reset = () => {
      results.replaceChildren();
      hint.hidden = false;
      active = -1;
    };

    function seeAll(query) {
      const all = document.createElement("a");
      all.className = "suggest-all";
      all.href = form.action + "?q=" + encodeURIComponent(query);
      all.setAttribute("role", "option");
      const icon = document.createElement("i");
      icon.className = "bi bi-arrow-return-right";
      icon.setAttribute("aria-hidden", "true");
      all.append(icon, document.createTextNode("See all results for “" + query + "”"));
      return all;
    }

    function render(books, query) {
      results.replaceChildren();
      books.forEach((book) => {
        const link = document.createElement("a");
        link.className = "suggest-item";
        link.href = book.url;
        link.setAttribute("role", "option");
        const img = document.createElement("img");
        img.src = book.cover_url;
        img.alt = "";
        const text = document.createElement("span");
        const title = document.createElement("strong");
        title.textContent = book.title;
        const author = document.createElement("small");
        author.textContent = book.author;
        text.append(title, author);
        link.append(img, text);
        results.append(link);
      });
      results.append(seeAll(query));
      active = -1;
    }

    input.addEventListener("input", () => {
      clearTimeout(timer);
      const query = input.value.trim();
      if (query.length < 3) {
        reset();
        return;
      }
      hint.hidden = true;
      status("Searching…");
      timer = setTimeout(async () => {
        if (controller) controller.abort();
        controller = new AbortController();
        try {
          const response = await fetch(endpoint + "?q=" + encodeURIComponent(query), {
            signal: controller.signal,
            headers: { "X-Requested-With": "fetch" },
          });
          if (input.value.trim() !== query) return;
          if (!response.ok) { status("Search is busy. Press Enter to see full results."); return; }
          const data = await response.json();
          if (data.results && data.results.length) render(data.results, query);
          else { status("No quick matches."); results.append(seeAll(query)); }
        } catch (error) {
          if (error.name !== "AbortError") status("You seem to be offline.");
        }
      }, 250);
    });

    input.addEventListener("keydown", (event) => {
      const list = options();
      if (!list.length) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const step = event.key === "ArrowDown" ? 1 : -1;
        setActive((active + step + list.length) % list.length);
      } else if (event.key === "Enter" && active >= 0 && list[active]) {
        event.preventDefault();
        window.location.assign(list[active].href);
      }
    });

    dialog.addEventListener("click", (event) => {
      if (event.target === dialog || event.target.closest("[data-close-search]")) dialog.close();
    });
    dialog.addEventListener("close", () => {
      input.value = "";
      reset();
    });

    return function open() {
      if (dialog.open) return;
      dialog.showModal();
      input.focus();
    };
  }

  /* ---------- Start ---------- */
  function start() {
    syncTheme();
    document.querySelectorAll(".cover img").forEach(settleImage);

    if (window.bootstrap) {
      document.querySelectorAll("#toasts .toast").forEach((toast) => {
        toast.addEventListener("hidden.bs.toast", () => toast.remove());
        new bootstrap.Toast(toast).show();
      });
    }

    document.querySelectorAll(".rail").forEach((rail) => {
      updateRail(rail);
      rail.addEventListener("scroll", () => updateRail(rail), { passive: true });
    });
    window.addEventListener("resize", () => document.querySelectorAll(".rail").forEach(updateRail));

    const openPalette = setupPalette();
    if (openPalette) {
      document.addEventListener("click", (event) => {
        const trigger = event.target.closest("[data-open-search]");
        if (!trigger || event.metaKey || event.ctrlKey || event.shiftKey) return;
        event.preventDefault();
        openPalette();
      });
      document.addEventListener("keydown", (event) => {
        const target = event.target instanceof Element ? event.target : document.body;
        const typing = target.closest("input, textarea, select, [contenteditable]");
        const slash = event.key === "/" && !typing && !event.ctrlKey && !event.metaKey && !event.altKey;
        const cmdK = (event.key === "k" || event.key === "K") && (event.ctrlKey || event.metaKey);
        if (slash || cmdK) {
          event.preventDefault();
          openPalette();
        }
      });
    }

    // Long descriptions collapse behind a "Read more" button.
    document.querySelectorAll("[data-clamp]").forEach((block) => {
      block.classList.add("is-clamped");
      const toggle = document.querySelector('[data-clamp-toggle="' + block.id + '"]');
      if (!toggle) return;
      if (block.scrollHeight <= block.clientHeight + 4) {
        block.classList.remove("is-clamped");
        return;
      }
      toggle.hidden = false;
      toggle.addEventListener("click", () => {
        const clamped = block.classList.toggle("is-clamped");
        toggle.textContent = clamped ? "Read more" : "Show less";
        toggle.setAttribute("aria-expanded", clamped ? "false" : "true");
      });
    });

    // Show / hide password.
    document.querySelectorAll("[data-pw-toggle]").forEach((button) => {
      const field = document.getElementById(button.dataset.pwToggle);
      button.addEventListener("click", () => {
        const show = field.type === "password";
        field.type = show ? "text" : "password";
        button.querySelector("i").className = show ? "bi bi-eye-slash" : "bi bi-eye";
        button.setAttribute("aria-label", show ? "Hide password" : "Show password");
      });
    });

    // Prevent double submits on ordinary forms.
    document.addEventListener("submit", (event) => {
      const form = event.target;
      if (form.classList.contains("js-save") || form.method.toLowerCase() !== "post") return;
      const button = event.submitter;
      if (button && button.type === "submit") setTimeout(() => { button.disabled = true; }, 0);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
