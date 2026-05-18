(function () {
  function baseUrl(settings) {
    return String(settings?.apiUrl || "").trim().replace(/\/+$/, "");
  }

  function isConfigured(settings) {
    return Boolean(baseUrl(settings));
  }

  async function request(settings, path, options = {}) {
    const base = baseUrl(settings);
    if (!base) {
      throw new Error("URL API бота не задан.");
    }

    const headers = {
      Accept: "application/json",
      ...(options.headers || {})
    };
    const token = String(settings?.dashboardToken || "").trim();
    if (token) {
      headers["X-Dashboard-Token"] = token;
    }

    let body = options.body;
    if (body !== undefined && typeof body !== "string") {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }

    const response = await fetch(`${base}${path}`, {
      ...options,
      headers,
      body,
      credentials: "include"
    });

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : { ok: response.ok };
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || `API вернул HTTP ${response.status}`);
    }
    return payload;
  }

  function action(settings, type, guildId, payload = {}) {
    return request(settings, "/api/actions", {
      method: "POST",
      body: { type, guildId, payload }
    });
  }

  function authUrl(settings) {
    const base = baseUrl(settings);
    if (!base) {
      return "";
    }
    const returnTo = `${location.origin}${location.pathname}${location.hash || "#/settings"}`;
    return `${base}/api/auth/login?return_to=${encodeURIComponent(returnTo)}`;
  }

  window.BotDashboardApi = {
    action,
    authUrl,
    baseUrl,
    isConfigured,
    request
  };
})();
