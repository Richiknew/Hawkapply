// HawkApply Service Worker
// Handles all API calls so the API key never lives in a content script.

const DEFAULT_API_URL = "http://localhost:8000";

async function getSettings() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(
      { apiUrl: DEFAULT_API_URL, apiKey: "", dashboardUrl: "http://localhost:3000" },
      resolve
    );
  });
}

async function hawkFetch(path, options = {}) {
  const { apiUrl, apiKey } = await getSettings();
  if (!apiKey) throw new Error("API key not set. Open HawkApply options.");

  const res = await fetch(`${apiUrl}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

// ── Message handlers ──────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  handleMessage(msg).then(sendResponse).catch((err) => {
    sendResponse({ error: err.message });
  });
  return true; // keep channel open for async
});

async function handleMessage(msg) {
  switch (msg.type) {
    case "LOOKUP_JOB": {
      const url = encodeURIComponent(msg.url);
      const job = await hawkFetch(`/jobs/lookup?url=${url}`);
      if (!job) return { found: false };
      // Also fetch match result if exists
      let match = null;
      try {
        match = await hawkFetch(`/jobs/${job.job_hash}/match`);
      } catch (_) {
        // no match yet — that's fine
      }
      return { found: true, job, match };
    }

    case "SAVE_JOB": {
      const job = await hawkFetch("/jobs", {
        method: "POST",
        body: JSON.stringify(msg.data),
      });
      return { job };
    }

    case "UPDATE_STATUS": {
      const job = await hawkFetch(`/jobs/${msg.jobHash}`, {
        method: "PATCH",
        body: JSON.stringify({ status: msg.status }),
      });
      return { job };
    }

    case "GET_STATS": {
      const stats = await hawkFetch("/stats");
      return { stats };
    }

    case "GET_MATCHES": {
      const matches = await hawkFetch("/match/results?limit=20");
      return { matches };
    }

    case "RUN_PIPELINE": {
      const result = await hawkFetch("/pipeline/run", {
        method: "POST",
        body: "{}",
      });
      return { result };
    }

    case "CHECK_SETTINGS": {
      const { apiUrl, apiKey, dashboardUrl } = await getSettings();
      return { configured: !!apiKey, apiUrl, dashboardUrl };
    }

    case "GET_AUTOFILL": {
      const autofill = await hawkFetch(`/jobs/${msg.jobHash}/autofill`);
      return { autofill };
    }

    default:
      throw new Error(`Unknown message type: ${msg.type}`);
  }
}
