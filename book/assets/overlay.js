/* Paragraph overlay: click a paragraph to see who wrote it (blame.json)
 * and who vouches for it (vouches.json). All fetches are relative so the
 * site works under any URL prefix. */
(function () {
  "use strict";

  var blame = {};
  var vouches = {};

  function load(name, into) {
    return fetch(name)
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (d) { Object.assign(into, d); })
      .catch(function () { /* static file missing: degrade silently */ });
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  var pop = null;

  function popup() {
    if (!pop) {
      pop = document.createElement("div");
      pop.className = "bk-pop";
      pop.hidden = true;
      document.body.appendChild(pop);
    }
    return pop;
  }

  function show(target) {
    var h = target.getAttribute("data-phash");
    var b = (blame.byHash || {})[h];
    var vs = vouches[h] || [];
    var html = "";
    if (b && b.author) {
      html += '<div class="bk-pop-author">&#9998; ' + esc(b.author) +
        (b.date ? " &middot; " + esc(b.date) : "") +
        (b.commit ? ' &middot; <code>' + esc(b.commit.slice(0, 8)) + "</code>" : "") +
        "</div>";
    } else {
      html += '<div class="bk-pop-author bk-pop-none">no authorship info</div>';
    }
    if (vs.length) {
      html += vs.map(function (v) {
        return '<div class="bk-pop-vouch">&#10003; vouched by <strong>' +
          esc(v.voucher) + "</strong>" +
          (v.date ? " &middot; " + esc(v.date) : "") +
          (v.note ? " &mdash; " + esc(v.note) : "") + "</div>";
      }).join("");
    } else {
      html += '<div class="bk-pop-vouch bk-pop-none">no vouches yet</div>';
    }
    var p = popup();
    p.innerHTML = html;
    // let the (optional) web-actions layer add discuss/vouch/edit controls
    if (window.BookWebActions) {
      var main = target.closest("[data-source]");
      window.BookWebActions.decorate(p, {
        hash: h,
        excerpt: target.textContent.slice(0, 200),
        source: (b && b.file) || (main && main.getAttribute("data-source")) || "",
      });
    }
    var r = target.getBoundingClientRect();
    p.style.top = window.scrollY + r.bottom + 6 + "px";
    p.style.left = window.scrollX + r.left + "px";
    p.hidden = false;
  }

  function init() {
    Promise.all([load("blame.json", blame), load("vouches.json", vouches)]).then(function () {
      var hs = Object.keys(vouches);
      document.querySelectorAll("[data-phash]").forEach(function (el) {
        el.classList.add("bk-para");
        if (hs.indexOf(el.getAttribute("data-phash")) !== -1) {
          el.classList.add("bk-vouched");
        }
      });
    });
    document.addEventListener("click", function (e) {
      var t = e.target.closest ? e.target.closest("[data-phash]") : null;
      if (t) { show(t); } else if (pop) { pop.hidden = true; }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
