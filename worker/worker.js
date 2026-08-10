/* OAuth token-exchange worker for the Collective Knowledge site.
 *
 * A static site cannot complete an OAuth code flow by itself: GitHub's
 * (and ORCID's) token endpoints require the client secret and are not
 * CORS-enabled. This worker is the one tiny server-side piece: it holds
 * the secret and swaps an authorization code for a token. It stores
 * nothing and logs nothing.
 *
 * Endpoints (POST, JSON, CORS restricted to ALLOWED_ORIGINS):
 *   /exchange        {code}                -> {access_token, scope}   (GitHub)
 *   /orcid/exchange  {code, redirect_uri}  -> {orcid, name, access_token}
 *
 * Configuration (wrangler vars/secrets):
 *   ALLOWED_ORIGINS       comma-separated site origins, e.g.
 *                         "https://fhell.github.io"
 *   GITHUB_CLIENT_ID      OAuth app client id        (var)
 *   GITHUB_CLIENT_SECRET  OAuth app client secret    (secret)
 *   ORCID_CLIENT_ID       optional, for ORCID later  (var)
 *   ORCID_CLIENT_SECRET   optional                   (secret)
 */

function json(data, status, cors) {
  return new Response(JSON.stringify(data), {
    status: status,
    headers: { "Content-Type": "application/json", ...cors },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    const allowed = (env.ALLOWED_ORIGINS || "")
      .split(",").map((s) => s.trim()).filter(Boolean);
    const okOrigin = allowed.includes(origin);
    const cors = {
      "Access-Control-Allow-Origin": okOrigin ? origin : "null",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Vary": "Origin",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    if (url.pathname === "/exchange" && request.method === "POST") {
      if (!okOrigin) return json({ error: "origin not allowed" }, 403, cors);
      const { code } = await request.json().catch(() => ({}));
      if (!code) return json({ error: "missing code" }, 400, cors);
      const r = await fetch("https://github.com/login/oauth/access_token", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          client_id: env.GITHUB_CLIENT_ID,
          client_secret: env.GITHUB_CLIENT_SECRET,
          code: code,
        }),
      });
      const data = await r.json();
      if (data.error) {
        return json({ error: data.error_description || data.error }, 400, cors);
      }
      return json({
        access_token: data.access_token,
        token_type: data.token_type,
        scope: data.scope,
      }, 200, cors);
    }

    if (url.pathname === "/orcid/exchange" && request.method === "POST") {
      if (!okOrigin) return json({ error: "origin not allowed" }, 403, cors);
      if (!env.ORCID_CLIENT_ID) {
        return json({ error: "ORCID not configured on this worker" }, 501, cors);
      }
      const { code, redirect_uri } = await request.json().catch(() => ({}));
      if (!code) return json({ error: "missing code" }, 400, cors);
      const form = new URLSearchParams({
        client_id: env.ORCID_CLIENT_ID,
        client_secret: env.ORCID_CLIENT_SECRET,
        grant_type: "authorization_code",
        code: code,
        redirect_uri: redirect_uri || "",
      });
      const r = await fetch("https://orcid.org/oauth/token", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          Accept: "application/json",
        },
        body: form.toString(),
      });
      const data = await r.json();
      if (data.error) {
        return json({ error: data.error_description || data.error }, 400, cors);
      }
      return json({
        orcid: data.orcid,
        name: data.name,
        access_token: data.access_token,
      }, 200, cors);
    }

    return json({
      service: "collective-knowledge token exchange",
      endpoints: ["POST /exchange {code}", "POST /orcid/exchange {code, redirect_uri}"],
    }, 200, cors);
  },
};
