/* Web actions: interactive layer on top of the static book.
 *
 * Pages load this with:  <script src="...web-actions.js" data-base="./"></script>
 * where data-base is the relative path to the site directory containing
 * forge.json (book pages: "./", diff pages: "../../").
 *
 * Provides: sign-in bar (token in localStorage), paragraph actions
 * (discuss / vouch / edit) hooked into overlay.js popups, a review bar
 * on rendered-diff pages (window.BOOK_DIFF_PR), and an open-changes
 * list on any page with a #bk-changes element.
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var BASE = (script && script.getAttribute("data-base")) || "./";
  var F = window.BookForge;
  if (!F) return;
  F.init(BASE);

  // ---- tiny UI helpers ------------------------------------------------------

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }

  function toast(msg, isError) {
    var t = el("div", "bk-toast" + (isError ? " bk-toast-err" : ""), msg);
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add("bk-toast-show"); }, 10);
    setTimeout(function () { t.remove(); }, isError ? 8000 : 5000);
  }

  function modal(title, bodyEl, submitLabel, onSubmit) {
    var back = el("div", "bk-modal-back");
    var box = el("div", "bk-modal");
    box.appendChild(el("h3", "", title));
    box.appendChild(bodyEl);
    var row = el("div", "bk-modal-row");
    var cancel = el("button", "bk-btn", "Cancel");
    var ok = el("button", "bk-btn bk-btn-primary", submitLabel);
    row.appendChild(cancel); row.appendChild(ok);
    box.appendChild(row);
    back.appendChild(box);
    document.body.appendChild(back);
    cancel.onclick = function () { back.remove(); };
    ok.onclick = function () {
      ok.disabled = true; ok.textContent = "…";
      Promise.resolve(onSubmit(box)).then(function (keepOpen) {
        if (!keepOpen) back.remove();
      }).catch(function (e) {
        ok.disabled = false; ok.textContent = submitLabel;
        toast(String(e.message || e), true);
      });
    };
    return box;
  }

  function textarea(value, rows, placeholder) {
    var t = el("textarea", "bk-ta");
    t.value = value || "";
    t.rows = rows || 6;
    if (placeholder) t.placeholder = placeholder;
    return t;
  }

  function requireSignIn() {
    if (F.token()) return true;
    signInDialog();
    return false;
  }

  // ---- sign-in: OAuth (via token-exchange worker) and pasted token -------------

  function siteRoot() {
    return new URL(BASE, window.location.href).href;
  }

  function startOAuth(cfg) {
    var state = Math.random().toString(36).slice(2) + Date.now().toString(36);
    sessionStorage.setItem("bk-oauth-state", state);
    window.location.href = "https://github.com/login/oauth/authorize" +
      "?client_id=" + encodeURIComponent(cfg.oauth.client_id) +
      "&redirect_uri=" + encodeURIComponent(siteRoot()) +
      "&scope=public_repo&state=" + state;
  }

  function handleOAuthReturn(cfg) {
    if (!cfg || !cfg.oauth) return;
    var params = new URLSearchParams(window.location.search);
    var code = params.get("code");
    if (!code) return;
    var expected = sessionStorage.getItem("bk-oauth-state");
    sessionStorage.removeItem("bk-oauth-state");
    window.history.replaceState(null, "", window.location.pathname);
    if (!expected || params.get("state") !== expected) {
      toast("Sign-in failed: state mismatch — please try again.", true);
      return;
    }
    fetch(cfg.oauth.exchange_url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: code }),
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.access_token) throw new Error(d.error || "no token returned");
      F.signIn(d.access_token);
      toast("Signed in with GitHub.");
      renderBar();
    }).catch(function (e) {
      toast("Sign-in failed: " + (e.message || e), true);
    });
  }

  function signInDialog() {
    var wrap = el("div");
    var cfg = F.config();
    if (cfg && cfg.oauth) {
      var oauthBtn = el("button", "bk-btn bk-btn-primary", "Sign in with GitHub");
      oauthBtn.style.width = "100%";
      oauthBtn.onclick = function () { startOAuth(cfg); };
      wrap.appendChild(oauthBtn);
      wrap.appendChild(el("p", "bk-hint", "— or paste a token —"));
    }
    var p = el("p", "bk-hint");
    p.innerHTML = "Paste a personal access token for this repository " +
      "(fine-grained, scoped to Contents, Pull requests and Issues — " +
      "read/write). It is stored only in this browser and sent only to " +
      "the forge API.";
    var input = el("input", "bk-ta");
    input.type = "password";
    input.placeholder = "token";
    wrap.appendChild(p); wrap.appendChild(input);
    modal("Sign in", wrap, "Sign in", function () {
      if (!input.value.trim()) throw new Error("no token given");
      F.signIn(input.value);
      return F.me().then(function (u) {
        toast("Signed in as " + u.login);
        renderBar();
      }).catch(function (e) {
        F.signOut();
        throw new Error("token rejected: " + e.message);
      });
    });
  }

  function renderBar() {
    var old = document.querySelector(".bk-authbar");
    if (old) old.remove();
    var bar = el("div", "bk-authbar");
    if (F.token()) {
      F.me().then(function (u) {
        bar.appendChild(el("span", "", "✎ " + u.login));
        var out = el("a", "bk-authlink", "sign out");
        out.onclick = function () { F.signOut(); renderBar(); };
        bar.appendChild(out);
      }).catch(function () {
        F.signOut();
        var login = el("a", "bk-authlink", "sign in");
        login.onclick = signInDialog;
        bar.appendChild(login);
      });
    } else {
      var login = el("a", "bk-authlink", "✎ sign in to contribute");
      login.onclick = signInDialog;
      bar.appendChild(login);
    }
    document.body.appendChild(bar);
  }

  // ---- paragraph actions (called from overlay.js) -----------------------------

  var discussionCache = {};

  function decorate(popup, info) {
    // info: {hash, excerpt, source}  — source is the chapter file path
    var row = el("div", "bk-actions");

    var discussBtn = el("button", "bk-btn", "💬 discuss");
    discussBtn.onclick = function () {
      if (!requireSignIn()) return;
      var ta = textarea("", 5, "What should be discussed about this paragraph?");
      modal("Start a discussion", ta, "Open issue", function () {
        if (!ta.value.trim()) throw new Error("empty message");
        return F.discuss(info.source, info.hash, info.excerpt, ta.value).then(function (issue) {
          toast("Discussion opened: #" + issue.number);
          window.open(issue.html_url, "_blank");
        });
      });
    };

    var vouchBtn = el("button", "bk-btn", "✓ vouch");
    vouchBtn.onclick = function () {
      if (!requireSignIn()) return;
      var ta = textarea("", 3, "Optional note (what did you check?)");
      modal("Vouch for this paragraph", ta, "Vouch", function () {
        return F.vouch(info.source, info.hash, info.excerpt, ta.value).then(function (r) {
          if (r.direct) {
            toast("Vouch committed. It appears on the site after the next deploy (~1 min).");
          } else {
            toast("No direct write access — vouch opened as change #" + r.pr.number);
            window.open(r.pr.html_url, "_blank");
          }
        });
      });
    };

    var editBtn = el("button", "bk-btn", "✏️ edit");
    editBtn.onclick = function () {
      if (!requireSignIn()) return;
      F.getFile(info.source).then(function (f) {
        var wrap = el("div");
        var ta = textarea(F.b64decode(f.content), 18);
        var sum = el("input", "bk-ta");
        sum.placeholder = "One-line summary of your change";
        wrap.appendChild(ta); wrap.appendChild(sum);
        modal("Edit " + info.source, wrap, "Submit change", function () {
          if (!sum.value.trim()) throw new Error("please give a one-line summary");
          return F.proposeEdit(info.source, ta.value, sum.value).then(function (pr) {
            toast("Change #" + pr.number + " submitted for review.");
            window.open(pr.html_url, "_blank");
          });
        });
      }).catch(function (e) { toast(String(e.message || e), true); });
    };

    row.appendChild(discussBtn);
    row.appendChild(vouchBtn);
    row.appendChild(editBtn);
    popup.appendChild(row);

    // lazily show existing discussions for this paragraph
    var slot = el("div", "bk-discussions");
    popup.appendChild(slot);
    if (discussionCache[info.hash]) {
      fillDiscussions(slot, discussionCache[info.hash]);
    } else {
      F.ready.then(function (cfg) {
        if (!cfg) return;
        F.searchDiscussions(info.hash).then(function (items) {
          discussionCache[info.hash] = items;
          fillDiscussions(slot, items);
        }).catch(function () { /* rate-limited or offline: skip quietly */ });
      });
    }
  }

  function fillDiscussions(slot, items) {
    items.filter(function (i) { return !i.pull_request; }).slice(0, 5).forEach(function (i) {
      var a = el("a", "bk-disc-link", "💬 #" + i.number + " " + i.title.replace(/^Discussion: /, ""));
      a.href = i.html_url; a.target = "_blank";
      slot.appendChild(a);
    });
  }

  // ---- review bar on rendered-diff pages ---------------------------------------

  function reviewBar(prNumber) {
    F.ready.then(function (cfg) {
      if (!cfg) return;
      var bar = el("div", "bk-reviewbar");
      bar.appendChild(el("span", "bk-review-title", "Change #" + prNumber));

      var open = el("a", "bk-btn", "open on forge");
      F.getPR(prNumber).then(function (pr) {
        open.href = pr.html_url; open.target = "_blank";
        if (pr.state !== "open") {
          bar.appendChild(el("span", "bk-review-state", "(" + (pr.merged ? "merged" : pr.state) + ")"));
        }
      }).catch(function () {});
      bar.appendChild(open);

      var req = el("button", "bk-btn", "request changes");
      req.onclick = function () {
        if (!requireSignIn()) return;
        var ta = textarea("", 5, "What needs to change?");
        modal("Request changes on #" + prNumber, ta, "Send", function () {
          if (!ta.value.trim()) throw new Error("empty message");
          return F.review(prNumber, "REQUEST_CHANGES", ta.value).then(function () {
            toast("Changes requested.");
          });
        });
      };
      bar.appendChild(req);

      var approve = el("button", "bk-btn", "approve");
      approve.onclick = function () {
        if (!requireSignIn()) return;
        var ta = textarea("", 3, "Optional comment");
        modal("Approve #" + prNumber, ta, "Approve", function () {
          return F.review(prNumber, "APPROVE", ta.value).then(function () {
            toast("Approved.");
          });
        });
      };
      bar.appendChild(approve);

      var merge = el("button", "bk-btn bk-btn-primary", "merge");
      merge.onclick = function () {
        if (!requireSignIn()) return;
        modal("Merge change #" + prNumber,
          el("p", "bk-hint", "Merges with a merge commit (authorship preserved). The book redeploys automatically."),
          "Merge", function () {
            return F.mergePR(prNumber).then(function () {
              toast("Merged. The site rebuilds in about a minute.");
            });
          });
      };
      bar.appendChild(merge);

      document.body.appendChild(bar);
    });
  }

  // ---- open-changes list (landing page) -----------------------------------------

  function changesList(container) {
    F.ready.then(function (cfg) {
      if (!cfg) { container.textContent = "no forge configured"; return; }
      F.listOpenPRs().then(function (prs) {
        container.textContent = "";
        if (!prs.length) {
          container.appendChild(el("p", "bk-hint", "No changes are currently under review."));
          return;
        }
        prs.forEach(function (pr) {
          var item = el("div", "bk-change");
          var a = el("a", "", "#" + pr.number + " " + pr.title);
          a.href = BASE + "diffs/pr-" + pr.number + "/";
          item.appendChild(a);
          item.appendChild(el("span", "bk-change-meta",
            " by " + (pr.user && pr.user.login || "?") + " · "));
          var gh = el("a", "bk-change-meta", "discussion");
          gh.href = pr.html_url; gh.target = "_blank";
          item.appendChild(gh);
          container.appendChild(item);
        });
      }).catch(function () {
        container.textContent = "could not load open changes (rate limit?)";
      });
    });
  }

  // ---- boot -----------------------------------------------------------------------

  function boot() {
    renderBar();
    window.BookWebActions = { decorate: decorate };
    if (window.BOOK_DIFF_PR) reviewBar(window.BOOK_DIFF_PR);
    var list = document.getElementById("bk-changes");
    if (list) changesList(list);
    F.ready.then(handleOAuthReturn);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
