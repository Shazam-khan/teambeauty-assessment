/* Theme app extension client — fetches reviews + AI summary, handles
   form submission. No framework, plain ES2017.

   Each block instance has a root with these data attributes:
     data-sku       — product SKU from the storefront Liquid context
     data-shop      — shop permanent domain (foo.myshopify.com)
     data-app-url   — Remix app base URL (set in block settings)
*/
(function () {
  function init(root) {
    var sku = root.getAttribute("data-sku") || "";
    var shop = root.getAttribute("data-shop") || "";
    var appUrl = (root.getAttribute("data-app-url") || "").replace(/\/+$/, "");

    if (!sku || !shop || !appUrl) {
      return; // Liquid already renders an inline warning in this case.
    }

    var summaryEl = root.querySelector('[data-tb="summary"]');
    var listEl = root.querySelector('[data-tb="list"]');
    var formEl = root.querySelector('[data-tb="form"]');
    var statusEl = root.querySelector('[data-tb="status"]');

    function setStatus(text, state) {
      if (!statusEl) return;
      statusEl.textContent = text;
      if (state) statusEl.setAttribute("data-state", state);
      else statusEl.removeAttribute("data-state");
    }

    function renderSummary(summary, count) {
      if (!summaryEl) return;
      if (count > 0) {
        summaryEl.innerHTML =
          '<strong>AI summary (' + count + ' review' + (count === 1 ? "" : "s") + '):</strong> '
          + escapeHtml(summary);
      } else {
        summaryEl.innerHTML = '<em>No reviews yet — be the first.</em>';
      }
    }

    function renderList(reviews) {
      if (!listEl) return;
      if (reviews.length === 0) {
        listEl.innerHTML = '<li class="tb-reviews__list-empty">No reviews yet.</li>';
        return;
      }
      listEl.innerHTML = reviews.map(function (r) {
        var stars = "★".repeat(r.rating) + "☆".repeat(5 - r.rating);
        var date = new Date(r.created_at).toLocaleDateString();
        return (
          '<li>' +
            '<span class="tb-reviews__rating">' + stars + '</span>' +
            '<span class="tb-reviews__author">' + escapeHtml(r.customer_name) + '</span>' +
            '<span class="tb-reviews__date">' + date + '</span>' +
            '<div class="tb-reviews__text">' + escapeHtml(r.review_text) + '</div>' +
          '</li>'
        );
      }).join("");
    }

    function escapeHtml(s) {
      return String(s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function loadReviews() {
      return fetch(appUrl + "/api/reviews/" + encodeURIComponent(sku) + "?shop=" + encodeURIComponent(shop))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          renderList(data.reviews || []);
          return data.reviews || [];
        })
        .catch(function (e) {
          if (listEl) listEl.innerHTML = '<li>Failed to load reviews.</li>';
          console.error(e);
        });
    }

    function loadSummary() {
      return fetch(appUrl + "/api/summary/" + encodeURIComponent(sku) + "?shop=" + encodeURIComponent(shop))
        .then(function (r) { return r.json(); })
        .then(function (data) { renderSummary(data.summary || "", data.review_count || 0); })
        .catch(function (e) {
          if (summaryEl) summaryEl.textContent = "AI summary unavailable.";
          console.error(e);
        });
    }

    if (formEl) {
      formEl.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var btn = formEl.querySelector('button[type="submit"]');
        if (btn) btn.setAttribute("disabled", "disabled");
        setStatus("Submitting...");

        var fd = new FormData(formEl);
        var payload = {
          shop_domain: shop,
          customer_name: String(fd.get("customer_name") || "").trim(),
          rating: Number(fd.get("rating")),
          review_text: String(fd.get("review_text") || "").trim(),
        };

        fetch(appUrl + "/api/reviews/" + encodeURIComponent(sku), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
          .then(function (r) {
            return r.json().then(function (data) {
              if (!r.ok) throw new Error(data.error || "Request failed");
              return data;
            });
          })
          .then(function () {
            setStatus("Thanks for the review!", "ok");
            formEl.reset();
            return Promise.all([loadReviews(), loadSummary()]);
          })
          .catch(function (e) {
            setStatus(e.message || "Could not submit review.", "error");
          })
          .finally(function () {
            if (btn) btn.removeAttribute("disabled");
          });
      });
    }

    loadReviews();
    loadSummary();
  }

  function bootstrap() {
    document.querySelectorAll(".tb-reviews").forEach(init);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
  } else {
    bootstrap();
  }
})();
