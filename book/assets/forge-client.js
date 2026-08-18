/* BookForge — browser client for the Forgejo/Gitea REST API. The static
 * site has no backend of its own: the self-hosted forge is the backend,
 * git is the database. The user's token lives in localStorage and is
 * sent only to the forge API origin.
 *
 * Configuration comes from forge.json (written by `book build`):
 *   { provider: "forgejo", base, api, owner, repo, branch, html,
 *     oauth?: {client_id} }
 */
window.BookForge = (function () {
  "use strict";

  var TOKEN_KEY = "book-forge-token";
  var cfg = null;
  var readyResolve;
  var ready = new Promise(function (res) { readyResolve = res; });

  function init(baseUrl) {
    return fetch(baseUrl + "forge.json")
      .then(function (r) { if (!r.ok) throw new Error("no forge.json"); return r.json(); })
      .then(function (c) { cfg = c; readyResolve(c); return c; })
      .catch(function () { readyResolve(null); return null; });
  }

  function token() { return localStorage.getItem(TOKEN_KEY) || ""; }
  function signIn(t) { localStorage.setItem(TOKEN_KEY, t.trim()); }
  function signOut() { localStorage.removeItem(TOKEN_KEY); }

  function api(method, path, body) {
    var headers = { Accept: "application/json" };
    if (token()) headers.Authorization = "token " + token();
    if (body) headers["Content-Type"] = "application/json";
    return fetch(cfg.api + path, {
      method: method,
      headers: headers,
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (r) {
      if (!r.ok) {
        return r.text().then(function (t) {
          var err = new Error(method + " " + path + " → " + r.status + ": " + t.slice(0, 200));
          err.status = r.status;
          throw err;
        });
      }
      return r.status === 204 ? null : r.json();
    });
  }

  function repoPath(rest) { return "/repos/" + cfg.owner + "/" + cfg.repo + rest; }

  // UTF-8-safe base64
  function b64encode(s) { return btoa(unescape(encodeURIComponent(s))); }
  function b64decode(b) { return decodeURIComponent(escape(atob(b.replace(/\s/g, "")))); }

  // ---- reads (work unauthenticated on public repos) -----------------------

  function me() { return api("GET", "/user"); }

  function listOpenPRs() {
    return api("GET", repoPath("/pulls?state=open&limit=50"));
  }

  function getPR(n) { return api("GET", repoPath("/pulls/" + n)); }

  function listComments(n) {
    return api("GET", repoPath("/issues/" + n + "/comments"));
  }

  function listReviews(n) {
    return api("GET", repoPath("/pulls/" + n + "/reviews"));
  }

  function getFile(path, ref) {
    return api("GET", repoPath("/contents/" + path + "?ref=" + (ref || cfg.branch)));
  }

  function searchDiscussions(hash) {
    return api("GET", repoPath("/issues?q=" + encodeURIComponent(hash) + "&type=issue&state=all"));
  }

  // ---- writes --------------------------------------------------------------

  function createIssue(title, body) {
    return api("POST", repoPath("/issues"), { title: title, body: body });
  }

  function commentOnIssue(n, body) {
    return api("POST", repoPath("/issues/" + n + "/comments"), { body: body });
  }

  function createBranch(name) {
    return api("POST", repoPath("/branches"), {
      new_branch_name: name, old_branch_name: cfg.branch,
    });
  }

  function putFile(path, branch, message, content, sha) {
    return api("PUT", repoPath("/contents/" + path), {
      message: message, content: b64encode(content), branch: branch, sha: sha,
    });
  }

  function createPR(head, title, body) {
    return api("POST", repoPath("/pulls"), {
      head: head, base: cfg.branch, title: title, body: body,
    });
  }

  function review(n, event, body) {
    // Gitea/Forgejo review events: APPROVED | REQUEST_CHANGES | COMMENT
    return api("POST", repoPath("/pulls/" + n + "/reviews"), { event: event, body: body || "" });
  }

  function mergePR(n) {
    // merge commit, never squash: preserves per-paragraph authorship
    return api("POST", repoPath("/pulls/" + n + "/merge"), { Do: "merge" });
  }

  // ---- composite verbs -------------------------------------------------------

  function webBranch(login) {
    return "web/" + login + "-" + Date.now().toString(36);
  }

  /* Propose a new version of a chapter: branch + commit + PR. */
  function proposeEdit(file, newContent, summary) {
    var user, branch;
    return me().then(function (u) {
      user = u;
      branch = webBranch(user.login);
      return getFile(file);
    }).then(function (f) {
      return createBranch(branch).then(function () {
        return putFile(file, branch, summary || "edit " + file + " (via web)", newContent, f.sha);
      });
    }).then(function () {
      return createPR(branch, summary || "Edit " + file,
        "Proposed via the web editor on the published book.");
    });
  }

  /* Record a vouch in meta/vouches.yaml. Tries a direct commit to the
   * default branch (maintainers); falls back to branch + PR when the
   * branch is protected for this user. Append format matches the CLI's
   * YAML output, so both writers coexist. */
  function vouch(file, hash, excerpt, note) {
    var user;
    return me().then(function (u) {
      user = u;
      return getFile("meta/vouches.yaml");
    }).then(function (f) {
      var text = b64decode(f.content);
      if (/^vouches:\s*\[\]\s*$/m.test(text) || !/^vouches:/m.test(text)) {
        text = "vouches:\n";
      }
      var today = new Date().toISOString().slice(0, 10);
      var rec =
        "- file: " + JSON.stringify(file) + "\n" +
        "  hash: " + JSON.stringify(hash) + "\n" +
        "  excerpt: " + JSON.stringify((excerpt || "").slice(0, 80)) + "\n" +
        "  voucher: " + JSON.stringify(user.login) + "\n" +
        "  email: ''\n" +
        "  note: " + JSON.stringify(note || "") + "\n" +
        "  date: '" + today + "'\n" +
        "  commit: web\n";
      var newText = text.replace(/\s*$/, "") + "\n" + rec;
      var msg = "vouch: " + user.login + " vouches for " + file + " (via web)";
      return putFile("meta/vouches.yaml", cfg.branch, msg, newText, f.sha)
        .then(function () { return { direct: true }; })
        .catch(function () {
          var branch = webBranch(user.login);
          return createBranch(branch).then(function () {
            return putFile("meta/vouches.yaml", branch, msg, newText, f.sha);
          }).then(function () {
            return createPR(branch, "Vouch: " + file,
              "Vouch recorded via the web interface for paragraph `" + hash + "`.");
          }).then(function (pr) { return { direct: false, pr: pr }; });
        });
    });
  }

  /* Open a discussion issue anchored to a paragraph content hash. */
  function discuss(file, hash, excerpt, message) {
    var title = "Discussion: " + file + " ¶" + hash;
    var body =
      "> " + (excerpt || "").slice(0, 200) + "\n\n" + message +
      "\n\n---\nParagraph `" + hash + "` in `" + file +
      "` — opened from the published book.";
    return createIssue(title, body);
  }

  return {
    init: init, ready: ready,
    token: token, signIn: signIn, signOut: signOut,
    me: me, config: function () { return cfg; },
    listOpenPRs: listOpenPRs, getPR: getPR, getFile: getFile, b64decode: b64decode,
    listComments: listComments, listReviews: listReviews,
    searchDiscussions: searchDiscussions,
    proposeEdit: proposeEdit, vouch: vouch, discuss: discuss,
    review: review, mergePR: mergePR, commentOnIssue: commentOnIssue,
  };
})();
