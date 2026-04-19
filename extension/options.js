// HawkApply Options Page

const DEFAULTS = {
  apiUrl: "http://localhost:8000",
  apiKey: "",
  dashboardUrl: "http://localhost:3000",
};

function qs(sel) { return document.querySelector(sel); }

// Load saved settings into form
chrome.storage.sync.get(DEFAULTS, (settings) => {
  qs("#api-url").value = settings.apiUrl;
  qs("#api-key").value = settings.apiKey;
  qs("#dashboard-url").value = settings.dashboardUrl;
});

// Save
qs("#save-btn").addEventListener("click", () => {
  const settings = {
    apiUrl: qs("#api-url").value.trim().replace(/\/$/, ""),
    apiKey: qs("#api-key").value.trim(),
    dashboardUrl: qs("#dashboard-url").value.trim().replace(/\/$/, ""),
  };

  chrome.storage.sync.set(settings, () => {
    const status = qs("#status");
    status.textContent = "✓ Settings saved!";
    status.className = "status status-success";
    setTimeout(() => { status.className = "status"; }, 3000);
  });
});

// Reset
qs("#reset-btn").addEventListener("click", () => {
  qs("#api-url").value = DEFAULTS.apiUrl;
  qs("#api-key").value = DEFAULTS.apiKey;
  qs("#dashboard-url").value = DEFAULTS.dashboardUrl;
});

// Test connection
qs("#test-btn").addEventListener("click", async () => {
  const btn = qs("#test-btn");
  const result = qs("#test-result");
  const apiUrl = qs("#api-url").value.trim().replace(/\/$/, "");
  const apiKey = qs("#api-key").value.trim();

  btn.disabled = true;
  btn.textContent = "Testing…";
  result.textContent = "";

  try {
    const res = await fetch(`${apiUrl}/health`, {
      headers: { "X-API-Key": apiKey },
    });
    const data = await res.json();
    if (res.ok) {
      result.style.color = "#166534";
      result.textContent = `✓ Connected (${data.status || "ok"})`;
    } else {
      result.style.color = "#dc2626";
      result.textContent = `✗ ${res.status}: ${JSON.stringify(data)}`;
    }
  } catch (e) {
    result.style.color = "#dc2626";
    result.textContent = `✗ ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Test Connection";
  }
});
