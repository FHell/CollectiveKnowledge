/* Web actions: interactive layer on top of the static book.
 *
 * Pages load this with:  <script src="...web-actions.js" data-base="./"></script>
 * where data-base is the relative path to the site directory containing
 * forge.json (book pages: "./", diff pages: "../../").
 *
 * Provides: sign-in bar (Forgejo token in localStorage, or one-click
 * OAuth2+PKCE against the forge), paragraph actions (discuss / vouch /
 * edit) hooked into overlay.js popups, and — on rendered-diff pages
 * (window.BOOK_DIFF_PR) — a review bar plus the change's discussion
 * thread with an in-place reply box. Any page with a #bk-changes element
 * gets the open-changes list.
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

  // ---- sign-in: Forgejo OAuth2 + PKCE (public client, no secret, no
  // server of our own) and pasted application token --------------------------

  function siteRoot() {
    return new URL(BASE, window.location.href).href;
  }

  function b64url(bytes) {
    var s = "";
    new Uint8Array(bytes).forEach(function (b) { s += String.fromCharCode(b); });
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function startOAuth(cfg) {
    var verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
    var state = b64url(crypto.getRandomValues(new Uint8Array(16)));
    sessionStorage.setItem("bk-oauth-verifier", verifier);
    sessionStorage.setItem("bk-oauth-state", state);
    crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))
      .then(function (digest) {
        window.location.href = cfg.base + "/login/oauth/authorize" +
          "?client_id=" + encodeURIComponent(cfg.oauth.client_id) +
          "&redirect_uri=" + encodeURIComponent(siteRoot()) +
          "&response_type=code" +
          "&code_challenge_method=S256" +
          "&code_challenge=" + b64url(digest) +
          "&state=" + state;
      });
  }

  function handleOAuthReturn(cfg) {
    if (!cfg || !cfg.oauth) return;
    var params = new URLSearchParams(window.location.search);
    var code = params.get("code");
    if (!code) return;
    var expected = sessionStorage.getItem("bk-oauth-state");
    var verifier = sessionStorage.getItem("bk-oauth-verifier");
    sessionStorage.removeItem("bk-oauth-state");
    sessionStorage.removeItem("bk-oauth-verifier");
    window.history.replaceState(null, "", window.location.pathname);
    if (!expected || params.get("state") !== expected || !verifier) {
      toast("Sign-in failed: state mismatch — please try again.", true);
      return;
    }
    fetch(cfg.base + "/login/oauth/access_token", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        client_id: cfg.oauth.client_id,
        code: code,
        grant_type: "authorization_code",
        redirect_uri: siteRoot(),
        code_verifier: verifier,
      }),
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.access_token) throw new Error(d.error_description || d.error || "no token returned");
      F.signIn(d.access_token);
      toast("Signed in.");
      renderBar();
    }).catch(function (e) {
      toast("Sign-in failed: " + (e.message || e) +
        " — you can paste an application token instead.", true);
    });
  }

  function signInDialog() {
    var wrap = el("div");
    var cfg = F.config();
    // one-click OAuth needs a registered public client and the WebCrypto
    // API (secure context); otherwise only the token path is offered
    if (cfg && cfg.oauth && window.crypto && crypto.subtle) {
      var host = "";
      try { host = new URL(cfg.base).host; } catch (e) { /* keep generic */ }
      var oauthBtn = el("button", "bk-btn bk-btn-primary",
        "Sign in" + (host ? " at " + host : ""));
      oauthBtn.style.width = "100%";
      oauthBtn.onclick = function () { startOAuth(cfg); };
      wrap.appendChild(oauthBtn);
      wrap.appendChild(el("p", "bk-hint", "— or paste a token —"));
    }
    var p = el("p", "bk-hint");
    p.textContent = "Paste your Forgejo application token (forge Settings → " +
      "Applications → Generate token, with repository and issue read/write " +
      "scope — or the token your instructor gave you). It is stored only " +
      "in this browser and sent only to the forge API.";
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
      modal("Start a discussion", ta, "Open discussion", function () {
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
        }).catch(function () { /* offline: skip quietly */ });
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

  // ---- discussion thread on rendered-diff pages ---------------------------------
  //
  // The change (PR) discussion, hosted on our own forge, shown and
  // answerable in place below the rendered diff.

  function fmtDate(iso) {
    return (iso || "").replace("T", " ").slice(0, 16);
  }

  var STATE_LABEL = {
    APPROVED: "approved",
    REQUEST_CHANGES: "requested changes",
    COMMENT: "commented",
  };

  function threadItem(author, date, badge, body) {
    var item = el("div", "bk-comment");
    var head = el("div", "bk-comment-head");
    head.appendChild(el("strong", "", author || "?"));
    if (badge) {
      head.appendChild(el("span",
        "bk-badge" + (badge === "requested changes" ? " bk-badge-warn" :
                      badge === "approved" ? " bk-badge-ok" : ""),
        badge));
    }
    head.appendChild(el("span", "bk-comment-date", fmtDate(date)));
    item.appendChild(head);
    if (body && body.trim()) {
      // forge-sourced text is untrusted: render as plain text only
      item.appendChild(el("div", "bk-comment-body", body));
    }
    return item;
  }

  function loadThread(prNumber, listSlot) {
    return Promise.all([
      F.getPR(prNumber),
      F.listComments(prNumber).catch(function () { return []; }),
      F.listReviews(prNumber).catch(function () { return []; }),
    ]).then(function (res) {
      var pr = res[0], comments = res[1] || [], reviews = res[2] || [];
      var items = [];
      items.push({
        author: pr.user && pr.user.login,
        date: pr.created_at || pr.updated_at,
        badge: "opened this change",
        body: pr.body || "",
        sort: pr.created_at || "",
      });
      comments.forEach(function (c) {
        items.push({
          author: c.user && c.user.login,
          date: c.created_at,
          badge: null,
          body: c.body || "",
          sort: c.created_at || "",
        });
      });
      reviews.forEach(function (r) {
        var label = STATE_LABEL[r.state] || (r.state || "").toLowerCase();
        items.push({
          author: r.user && r.user.login,
          date: r.submitted_at,
          badge: label,
          body: r.body || "",
          sort: r.submitted_at || "",
        });
      });
      items.sort(function (a, b) { return a.sort < b.sort ? -1 : a.sort > b.sort ? 1 : 0; });
      listSlot.textContent = "";
      items.forEach(function (i) {
        listSlot.appendChild(threadItem(i.author, i.date, i.badge, i.body));
      });
      return items.length;
    });
  }

  function discussionThread(prNumber) {
    var sec = el("section", "bk-thread");
    sec.appendChild(el("h2", "bk-thread-title", "Discussion"));
    var listSlot = el("div", "bk-thread-list");
    listSlot.appendChild(el("p", "bk-hint", "loading discussion…"));
    sec.appendChild(listSlot);

    var ta = textarea("", 3, "Reply to this change…");
    var row = el("div", "bk-thread-replyrow");
    var send = el("button", "bk-btn bk-btn-primary", "Reply");
    send.onclick = function () {
      if (!requireSignIn()) return;
      if (!ta.value.trim()) { toast("empty message", true); return; }
      send.disabled = true; send.textContent = "…";
      F.commentOnIssue(prNumber, ta.value).then(function () {
        ta.value = "";
        return loadThread(prNumber, listSlot);
      }).then(function () {
        toast("Reply posted.");
      }).catch(function (e) {
        toast(String(e.message || e), true);
      }).finally(function () {
        send.disabled = false; send.textContent = "Reply";
      });
    };
    row.appendChild(send);
    sec.appendChild(ta);
    sec.appendChild(row);

    document.body.appendChild(sec);
    loadThread(prNumber, listSlot).catch(function () {
      listSlot.textContent = "";
      listSlot.appendChild(el("p", "bk-hint",
        "could not load the discussion (forge unreachable?)"));
    });
    return { refresh: function () { return loadThread(prNumber, listSlot); } };
  }

  // ---- review bar on rendered-diff pages ---------------------------------------

  function reviewBar(prNumber, thread) {
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

    function refreshThread() {
      if (thread) thread.refresh().catch(function () {});
    }

    var req = el("button", "bk-btn", "request changes");
    req.onclick = function () {
      if (!requireSignIn()) return;
      var ta = textarea("", 5, "What needs to change?");
      modal("Request changes on #" + prNumber, ta, "Send", function () {
        if (!ta.value.trim()) throw new Error("empty message");
        return F.review(prNumber, "REQUEST_CHANGES", ta.value).then(function () {
          toast("Changes requested.");
          refreshThread();
        });
      });
    };
    bar.appendChild(req);

    var approve = el("button", "bk-btn", "approve");
    approve.onclick = function () {
      if (!requireSignIn()) return;
      var ta = textarea("", 3, "Optional comment");
      modal("Approve #" + prNumber, ta, "Approve", function () {
        return F.review(prNumber, "APPROVED", ta.value).then(function () {
          toast("Approved.");
          refreshThread();
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
            refreshThread();
          });
        });
    };
    bar.appendChild(merge);

    document.body.appendChild(bar);
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
        container.textContent = "could not load open changes";
      });
    });
  }

  // ---- boot -----------------------------------------------------------------------

  function boot() {
    renderBar();
    window.BookWebActions = { decorate: decorate };
    if (window.BOOK_DIFF_PR) {
      F.ready.then(function (cfg) {
        if (!cfg) return;
        var thread = discussionThread(window.BOOK_DIFF_PR);
        reviewBar(window.BOOK_DIFF_PR, thread);
      });
    }
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
