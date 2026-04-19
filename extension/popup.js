// HawkApply Popup

function sendMsg(msg) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(msg, (res) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (res?.error) return reject(new Error(res.error));
      resolve(res);
    });
  });
}

function qs(sel) { return document.querySelector(sel); }

function tierDot(tier) {
  const t = (tier || "").toLowerCase();
  if (t.includes("strong")) return "dot-strong";
  if (t.includes("good")) return "dot-good";
  if (t.includes("stretch")) return "dot-stretch";
  return "dot-none";
}

function renderMain(stats, matches) {
  const j = stats.jobs;
  const m = stats.match;

  const topMatches = (matches || []).slice(0, 5);

  const matchRows = topMatches.map((match) => `
    <div class="match-item">
      <span class="tier-dot ${tierDot(match.fit_tier)}"></span>
      <div class="match-info">
        <div class="match-title">${match.title}</div>
        <div class="match-company">${match.company}</div>
      </div>
      <span class="match-score">${match.combined_score?.toFixed(0) ?? "—"}%</span>
    </div>
  `).join("");

  const lastScraped = j.last_scraped_at
    ? new Date(j.last_scraped_at).toLocaleDateString()
    : "never";

  qs("#last-scraped").textContent = `Last: ${lastScraped}`;

  qs("#main").innerHTML = `
    <div class="body">
      <div class="kpi-row">
        <div class="kpi">
          <div class="kpi-value">${j.total_jobs}</div>
          <div class="kpi-label">Jobs</div>
        </div>
        <div class="kpi">
          <div class="kpi-value">${m.total_matched}</div>
          <div class="kpi-label">Matched</div>
        </div>
        <div class="kpi">
          <div class="kpi-value">${m.strong_matches}</div>
          <div class="kpi-label">Strong</div>
        </div>
      </div>

      <div class="pipeline-row" style="margin-bottom:14px">
        <span class="pipeline-status">H1B sponsors: <strong>${j.sponsoring_jobs}</strong></span>
        <button class="btn-sm" id="run-pipeline-btn">▶ Run Pipeline</button>
      </div>

      <hr class="divider" />

      <div class="section-title">Top Matches</div>
      ${matchRows || '<p style="color:#94a3b8;font-size:11px">No matches yet. Run matching first.</p>'}

      <hr class="divider" />

      <button class="btn btn-primary" id="open-dashboard">Open Dashboard</button>
      <button class="btn btn-secondary" id="open-options">⚙ Settings</button>
    </div>
  `;

  qs("#open-dashboard").addEventListener("click", () => {
    chrome.storage.sync.get({ dashboardUrl: "http://localhost:3000" }, ({ dashboardUrl }) => {
      chrome.tabs.create({ url: `${dashboardUrl.replace(/\/$/, "")}/jobs` });
    });
  });

  qs("#open-options").addEventListener("click", () => {
    chrome.runtime.openOptionsPage();
  });

  qs("#run-pipeline-btn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Starting…";
    try {
      await sendMsg({ type: "RUN_PIPELINE" });
      btn.textContent = "▶ Running…";
    } catch (err) {
      btn.textContent = "✗ Error";
      setTimeout(() => {
        btn.disabled = false;
        btn.textContent = "▶ Run Pipeline";
      }, 2000);
    }
  });
}

function renderNotConfigured() {
  qs("#main").innerHTML = `
    <div class="not-configured">
      <p style="margin-bottom:10px">⚙ Set your API key to get started.</p>
      <button class="btn btn-primary" id="goto-options" style="width:auto;display:inline-block;padding:7px 18px">
        Open Settings
      </button>
    </div>
  `;
  qs("#goto-options").addEventListener("click", () => chrome.runtime.openOptionsPage());
}

function renderError(msg) {
  qs("#main").innerHTML = `<div class="error">⚠ ${msg}</div>
    <div style="padding:0 16px 14px">
      <button class="btn btn-secondary" id="open-options">⚙ Settings</button>
    </div>`;
  qs("#open-options")?.addEventListener("click", () => chrome.runtime.openOptionsPage());
}

async function init() {
  try {
    const { configured } = await sendMsg({ type: "CHECK_SETTINGS" });
    if (!configured) {
      renderNotConfigured();
      return;
    }

    const [{ stats }, matches] = await Promise.all([
      sendMsg({ type: "GET_STATS" }),
      sendMsg({ type: "GET_MATCHES" }).catch(() => ({ matches: [] })),
    ]);

    renderMain(stats, matches?.matches || []);
  } catch (err) {
    renderError(err.message);
  }
}

init();
