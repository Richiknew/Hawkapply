// HawkApply Content Script
// Injects a score overlay on job pages and extracts job data from the DOM.

(function () {
  "use strict";

  if (document.getElementById("hawkapply-overlay")) return;

  // ── React-compatible input setter ─────────────────────────────────────────
  // Plain `el.value = x` silently fails on React-controlled inputs.
  // We use the native HTMLInputElement setter which React cannot intercept.

  const _nativeInput = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, "value"
  )?.set;
  const _nativeTextarea = Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype, "value"
  )?.set;
  const _nativeSelect = Object.getOwnPropertyDescriptor(
    window.HTMLSelectElement.prototype, "value"
  )?.set;

  function triggerReact(el) {
    ["input", "change", "blur"].forEach((evt) =>
      el.dispatchEvent(new Event(evt, { bubbles: true }))
    );
  }

  function setElementValue(el, value) {
    if (!el || value == null || value === "") return false;
    const tag = el.tagName.toLowerCase();
    const type = (el.type || "").toLowerCase();
    const val = String(value).trim();

    if (tag === "select") {
      const opts = Array.from(el.options || []);
      const match = opts.find((o) => {
        const hay = `${o.value} ${o.textContent}`.toLowerCase();
        return hay.includes(val.toLowerCase()) || val.toLowerCase().includes(o.value.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim());
      });
      if (!match) return false;
      _nativeSelect ? _nativeSelect.call(el, match.value) : (el.value = match.value);
      triggerReact(el);
      return true;
    }

    if (type === "checkbox") {
      const truthy = ["yes", "true", "1"].includes(val.toLowerCase());
      el.checked = truthy;
      triggerReact(el);
      return true;
    }

    if (type === "radio") {
      const radios = document.querySelectorAll(`input[type="radio"][name="${CSS.escape(el.name || "")}"]`);
      const target = Array.from(radios).find((r) => {
        const label = (r.closest("label")?.textContent || r.value || "").toLowerCase();
        return label.includes(val.toLowerCase());
      });
      if (!target) return false;
      target.checked = true;
      triggerReact(target);
      return true;
    }

    // text / textarea — use native setter for React compat
    el.focus();
    if (tag === "textarea") {
      _nativeTextarea ? _nativeTextarea.call(el, val) : (el.value = val);
    } else {
      _nativeInput ? _nativeInput.call(el, val) : (el.value = val);
    }
    triggerReact(el);
    return true;
  }

  // ── Page detection ────────────────────────────────────────────────────────

  function likelyJobUrl() {
    const url = location.href.toLowerCase();
    return [
      "/jobs/", "/job/", "/careers/", "/apply", "apply-now",
      "gh_jid=", "/posting/", "/requisitions/", "/positions/",
      "/en/jobs/", "/job-details/", "jobdetail", "jobid=",
    ].some((t) => url.includes(t));
  }

  function isLikelyJobPage() {
    if (likelyJobUrl()) return true;
    return Boolean(
      document.querySelector("form input[name='first_name'], form input[name='email']") ||
      document.querySelector(".jobs-description__content, #job-description, [data-automation-id='job-posting-description']") ||
      document.querySelector("h1.job-title, h1.app-title, h1[data-test-id='job-title']") ||
      document.querySelector(".job-details-jobs-unified-top-card__job-title")
    );
  }

  // ── ATS detection ─────────────────────────────────────────────────────────

  function detectAts() {
    const host = location.hostname.toLowerCase();
    if (host.includes("linkedin.com")) return "linkedin";
    if (host.includes("greenhouse.io") || /gh_jid=/i.test(location.href)) return "greenhouse";
    if (host.includes("lever.co")) return "lever";
    if (host.includes("workday.com") || host.includes("myworkdayjobs.com")) return "workday";
    if (host.includes("ashbyhq.com")) return "ashby";
    if (host.includes("smartrecruiters.com")) return "smartrecruiters";
    if (host.includes("jobvite.com")) return "jobvite";
    if (host.includes("amazon.jobs") || host.includes("amazonjobs.com")) return "amazon";
    if (host.includes("careers.google.com") || host.includes("google.com/about/careers")) return "google";
    if (host.includes("meta.com") || host.includes("facebook.com/careers")) return "meta";
    if (host.includes("apple.com/careers")) return "apple";
    if (host.includes("microsoft.com/careers") || host.includes("careers.microsoft.com")) return "microsoft";

    // DOM-based fallback detection
    if (document.querySelector("[data-automation-id='jobPostingHeader']")) return "workday";
    if (document.querySelector(".posting-headline h2, .posting-categories")) return "lever";
    if (document.querySelector("h1.app-title, input[name='first_name']")) return "greenhouse";
    if (document.querySelector(".jv-header h2, #jv-job-description")) return "jobvite";

    return "generic";
  }

  // ── Job data extractors ───────────────────────────────────────────────────

  function text(sel, root = document) {
    return root.querySelector(sel)?.textContent?.trim() || "";
  }

  function firstText(...selectors) {
    for (const sel of selectors) {
      const t = text(sel);
      if (t) return t;
    }
    return "";
  }

  function extractJobData() {
    const ats = detectAts();
    switch (ats) {
      case "linkedin":      return extractLinkedIn();
      case "greenhouse":    return extractGreenhouse();
      case "lever":         return extractLever();
      case "workday":       return extractWorkday();
      case "ashby":         return extractAshby();
      case "smartrecruiters": return extractSmartRecruiters();
      case "jobvite":       return extractJobvite();
      case "amazon":        return extractAmazon();
      case "google":        return extractGoogle();
      case "meta":          return extractMeta();
      case "microsoft":     return extractMicrosoft();
      default:              return extractGeneric();
    }
  }

  function extractLinkedIn() {
    return {
      title: firstText(
        "h1.job-details-jobs-unified-top-card__job-title",
        "h1.topcard__title",
        "h1[data-test-id='job-title']",
        "h1"
      ),
      company: firstText(
        ".job-details-jobs-unified-top-card__company-name a",
        ".topcard__org-name-link",
        ".job-details-jobs-unified-top-card__company-name",
        "a[data-tracking-control-name='public_jobs_topcard-org-name']"
      ),
      location: firstText(
        ".job-details-jobs-unified-top-card__bullet",
        ".topcard__flavor--bullet",
        ".job-details-jobs-unified-top-card__primary-description-without-tagline"
      ),
      description: firstText(".jobs-description__content", ".show-more-less-html__markup"),
    };
  }

  function extractGreenhouse() {
    return {
      title: firstText("h1.app-title", "h1#application_header", ".posting-headline h2", "h1"),
      company: firstText(".company-name", ".nav-title a")
        || document.title.split(" at ").pop()?.trim()
        || "",
      location: firstText(".location", ".job-location", ".location-text"),
      description: firstText("#content", ".job-post-description", "#app_body"),
    };
  }

  function extractLever() {
    return {
      title: firstText(".posting-headline h2", "h2.posting-name", "h1"),
      company: firstText(".posting-header .company-name")
        || location.hostname.replace("jobs.lever.co/", "").split(".")[0],
      location: firstText(".posting-categories .location", ".location"),
      description: firstText(".posting-description", ".section.page-centered"),
    };
  }

  function extractWorkday() {
    return {
      title: firstText(
        "[data-automation-id='jobPostingHeader']",
        "h2[data-automation-id='jobPostingHeader']",
        "h1"
      ),
      company: firstText("[data-automation-id='company']")
        || document.title.split("|").pop()?.trim()
        || document.title.split("-").pop()?.trim()
        || "",
      location: firstText(
        "[data-automation-id='locations']",
        ".css-k64aca",
        "[data-automation-id='locationText']"
      ),
      description: firstText("[data-automation-id='job-posting-description']"),
    };
  }

  function extractAshby() {
    return {
      title: firstText("h1.ashby-job-posting-heading", "h1"),
      company: firstText(".ashby-job-posting-company-name", "[class*='companyName']")
        || document.title.split("at").pop()?.trim()
        || "",
      location: firstText("[class*='location']", "[class*='Location']"),
      description: firstText("[class*='jobPostingDescription']", "[class*='description']"),
    };
  }

  function extractSmartRecruiters() {
    return {
      title: firstText("h1.job-title", "h1"),
      company: firstText(".hiring-company-name", "[itemprop='hiringOrganization'] [itemprop='name']"),
      location: firstText(".job-info .location", "[itemprop='jobLocation'] [itemprop='addressLocality']"),
      description: firstText("#job-description", ".job-sections"),
    };
  }

  function extractJobvite() {
    return {
      title: firstText(".jv-header h2", "h2.jv-job-detail-meta", "h1"),
      company: firstText(".jv-company h1")
        || document.title.split(" at ").pop()?.trim()
        || "",
      location: firstText(".jv-job-detail-meta .location", ".jv-job-detail-location"),
      description: firstText("#jv-job-description", ".jv-job-detail-description"),
    };
  }

  function extractAmazon() {
    // amazon.jobs uses a React SPA; key selectors as of 2024
    return {
      title: firstText(
        "h1.job-title",
        "h1[data-test='job-title']",
        ".job-details h1",
        ".job-title",
        "h1"
      ),
      company: "Amazon",
      location: firstText(
        ".location-and-id .location",
        "[data-test='job-location']",
        ".job-details-meta .location",
        ".job-location"
      ),
      description: firstText(
        ".job-description",
        "[data-test='job-description']",
        ".job-detail-description",
        "#job-detail"
      ),
    };
  }

  function extractGoogle() {
    // careers.google.com
    return {
      title: firstText(
        "h2.p-hd__title",
        ".gc-job-detail__title h2",
        "h1",
        "[data-job-title]"
      ),
      company: "Google",
      location: firstText(
        ".gc-job-detail__location",
        ".p-hd__location",
        "[itemprop='jobLocation']",
        ".location"
      ),
      description: firstText(
        ".gc-job-detail__content",
        ".job-description",
        "[itemprop='description']"
      ),
    };
  }

  function extractMeta() {
    return {
      title: firstText("h1._8muv", "h2._65cn", "h1", "[data-testid='job-detail-title']"),
      company: "Meta",
      location: firstText("._9ata", "[data-testid='job-detail-location']", ".location"),
      description: firstText("._8o0a", "[data-testid='job-detail-description']"),
    };
  }

  function extractMicrosoft() {
    return {
      title: firstText("h1.ms-font-xxl", "[data-automation='job-title']", "h1"),
      company: "Microsoft",
      location: firstText("[data-automation='job-location']", ".ms-Icon--Location + span", ".location"),
      description: firstText("[data-automation='job-description']", ".job-description"),
    };
  }

  function extractGeneric() {
    // Score candidates by likely importance, pick first non-empty
    const title =
      firstText("h1") ||
      document.querySelector("title")?.textContent?.split(/[-|]/)[0]?.trim() ||
      document.title;

    // Try to get company from og:site_name or title "Role at Company"
    const ogSite = document.querySelector("meta[property='og:site_name']")?.content || "";
    const titleParts = document.title.split(/\s+at\s+/i);
    const company = ogSite || (titleParts.length > 1 ? titleParts[1].trim() : "");

    return {
      title,
      company,
      location: firstText(
        "[class*='location']", "[id*='location']",
        "[itemprop='jobLocation']", ".job-location"
      ),
      description: firstText(
        "#job-description", ".job-description",
        "[class*='description']", "[itemprop='description']"
      ),
    };
  }

  // ── Overlay rendering ──────────────────────────────────────────────────────

  const STATUSES = ["new", "reviewing", "applied", "interview", "rejected", "offer"];

  function buildOverlay() {
    const el = document.createElement("div");
    el.id = "hawkapply-overlay";
    el.innerHTML = `
      <div class="hawk-card" id="hawk-card">
        <div class="hawk-header" id="hawk-header">
          <span class="hawk-logo">🦅</span>
          <span class="hawk-title">HawkApply</span>
          <span class="hawk-toggle" id="hawk-toggle">▲</span>
        </div>
        <div class="hawk-body" id="hawk-body">
          <div class="hawk-loading" id="hawk-loading">
            <div class="hawk-spinner"></div>
            <span>Checking HawkApply…</span>
          </div>
          <div id="hawk-content" style="display:none"></div>
        </div>
      </div>`;
    return el;
  }

  function tierClass(tier) {
    const t = (tier || "").toLowerCase();
    if (t.includes("strong")) return "hawk-tier-strong";
    if (t.includes("good")) return "hawk-tier-good";
    if (t.includes("stretch")) return "hawk-tier-stretch";
    return "hawk-tier-none";
  }

  function capitalize(s) {
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
  }

  function renderFound(job, match) {
    const statusOptions = STATUSES.map(
      (s) => `<option value="${s}" ${job.status === s ? "selected" : ""}>${capitalize(s)}</option>`
    ).join("");

    const sponsorHtml = job.sponsors_h1b
      ? `<span class="hawk-sponsor hawk-sponsor-yes">✓ H1B Sponsor · ${job.h1b_filings ?? "?"} filings</span>`
      : `<span class="hawk-sponsor hawk-sponsor-no">✗ No H1B Sponsorship</span>`;

    let matchHtml = "";
    if (match) {
      const strengthsHtml = (match.strengths || []).slice(0, 2)
        .map((s) => `<li><span class="hawk-bullet-icon">✓</span> ${s}</li>`).join("");
      const gapsHtml = (match.gaps || []).slice(0, 1)
        .map((g) => `<li><span class="hawk-bullet-icon">✗</span> ${g}</li>`).join("");

      matchHtml = `
        <div class="hawk-scores">
          <div class="hawk-score-box">
            <div class="hawk-score-value">${match.combined_score?.toFixed(0) ?? "—"}%</div>
            <div class="hawk-score-label">Match</div>
          </div>
          <div class="hawk-score-box">
            <div class="hawk-score-value">${match.h1b_score?.toFixed(0) ?? "—"}%</div>
            <div class="hawk-score-label">H1B</div>
          </div>
          <div class="hawk-score-box">
            <div class="hawk-score-value">${match.match_score?.toFixed(0) ?? "—"}%</div>
            <div class="hawk-score-label">Resume</div>
          </div>
        </div>
        <span class="hawk-tier ${tierClass(match.fit_tier)}">${match.fit_tier || "Unscored"}</span>
        ${strengthsHtml || gapsHtml ? `
          <div class="hawk-section-title">Key points</div>
          <ul class="hawk-bullets">${strengthsHtml}${gapsHtml}</ul>` : ""}`;
    } else {
      matchHtml = `
        <div class="hawk-scores">
          <div class="hawk-score-box">
            <div class="hawk-score-value">${job.h1b_score?.toFixed(0) ?? "—"}%</div>
            <div class="hawk-score-label">H1B Score</div>
          </div>
        </div>
        <span class="hawk-tier hawk-tier-none">Not matched yet</span>`;
    }

    return `
      ${matchHtml}
      ${sponsorHtml}
      <div class="hawk-status-row">
        <span class="hawk-status-label">Status</span>
        <select class="hawk-status-select" id="hawk-status-select">${statusOptions}</select>
      </div>
      <div class="hawk-actions">
        <button class="hawk-btn hawk-btn-primary" id="hawk-autofill-btn">Autofill Form</button>
        <button class="hawk-btn hawk-btn-secondary" id="hawk-open-dashboard">Dashboard</button>
      </div>`;
  }

  function renderNotFound() {
    return `
      <p class="hawk-not-found">This job isn't in HawkApply yet.</p>
      <div class="hawk-actions">
        <button class="hawk-btn hawk-btn-primary" id="hawk-save-btn">+ Save to HawkApply</button>
        <button class="hawk-btn hawk-btn-secondary" id="hawk-quick-autofill">Save + Autofill</button>
        <button class="hawk-btn hawk-btn-secondary" id="hawk-open-dashboard">Dashboard</button>
      </div>`;
  }

  function renderError(msg) {
    return `<p class="hawk-error">⚠ ${msg}</p>`;
  }

  // ── Toast ─────────────────────────────────────────────────────────────────

  function showToast(msg, duration = 2800) {
    const t = document.createElement("div");
    t.className = "hawk-toast";
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), duration);
  }

  // ── Messaging ─────────────────────────────────────────────────────────────

  let currentJob = null;
  let currentJobHash = null;

  function sendMsg(msg) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(msg, (res) => {
        if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
        if (res?.error) return reject(new Error(res.error));
        resolve(res);
      });
    });
  }

  // ── Autofill engine ───────────────────────────────────────────────────────

  /**
   * Find form controls whose label/name/placeholder/aria contains ALL of the given patterns.
   * Falls back to OR matching if nothing found.
   */
  function fieldText(el) {
    const labelledBy = (el.getAttribute("aria-labelledby") || "")
      .split(/\s+/)
      .map((id) => document.getElementById(id)?.textContent || "")
      .join(" ");

    // Walk up to find a <label> with [for] pointing to this field
    let forLabel = "";
    if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl) forLabel = lbl.textContent;
    }

    const parts = [
      el.name,
      el.id,
      el.placeholder,
      el.getAttribute("aria-label"),
      el.getAttribute("autocomplete"),
      el.getAttribute("data-field-name"),
      labelledBy,
      forLabel,
      el.closest("label")?.textContent,
      el.closest("[class*='field'], [class*='Field'], [class*='form-group'], [class*='input-container']")
        ?.querySelector("label, span, legend")?.textContent,
    ];

    return parts.filter(Boolean).join(" ").toLowerCase();
  }

  function findField(patterns) {
    const controls = Array.from(document.querySelectorAll("input:not([type=hidden]):not([type=file]), textarea, select"));
    // try to find a field that matches any of the patterns
    return controls.find((el) => {
      const ft = fieldText(el);
      return patterns.some((p) => ft.includes(p));
    }) || null;
  }

  function fillField(patterns, value) {
    if (value == null || value === "") return false;
    const el = findField(patterns);
    if (!el) return false;
    return setElementValue(el, value);
  }

  function autofillForm(payload) {
    const ats = detectAts();
    // Merge standard fields + platform-specific overrides
    const std = payload.standard_fields || {};
    const platformData = payload[ats] || payload["greenhouse"] || {};
    const merged = { ...std, ...platformData };

    let filled = 0;

    // ── Personal Info ────────────────────────────────────────────────────────
    filled += fillField(["first name", "given name", "firstname", "first_name", "fname"], merged.first_name) ? 1 : 0;
    filled += fillField(["last name", "family name", "lastname", "last_name", "surname", "lname"], merged.last_name) ? 1 : 0;
    filled += fillField(["full name", "fullname", "candidate name", "legal name", "your name"], merged.full_name) ? 1 : 0;
    filled += fillField(["email"], merged.email) ? 1 : 0;
    filled += fillField(["phone", "mobile", "telephone", "cell"], merged.phone) ? 1 : 0;
    filled += fillField(["city", "location", "current location", "city, state", "address"], merged.city || merged.location) ? 1 : 0;

    // ── Links ────────────────────────────────────────────────────────────────
    filled += fillField(["linkedin"], merged.linkedin) ? 1 : 0;
    filled += fillField(["github"], merged.github) ? 1 : 0;
    filled += fillField(["portfolio", "website", "personal site", "personal url"], merged.portfolio || merged.github) ? 1 : 0;

    // ── Work Authorization ───────────────────────────────────────────────────
    filled += fillField(["authorized to work", "legally authorized", "work authorization", "eligible to work"], "Yes") ? 1 : 0;
    filled += fillField(["require sponsorship", "need sponsorship", "sponsorship", "visa sponsorship"], "Yes") ? 1 : 0;
    filled += fillField(["visa status", "immigration status", "work visa", "current work auth"], merged.visa_status || "OPT STEM Extension") ? 1 : 0;
    filled += fillField(["will you now or in the future require", "now or in the future"], "Yes") ? 1 : 0;

    // ── Experience ───────────────────────────────────────────────────────────
    filled += fillField(["years of experience", "years experience", "experience (years)", "total experience", "relevant experience"], merged.years_experience) ? 1 : 0;
    filled += fillField(["current title", "current job title", "job title", "position title"], merged.current_title) ? 1 : 0;
    filled += fillField(["current company", "current employer", "most recent company"], merged.current_company) ? 1 : 0;

    // ── Education ────────────────────────────────────────────────────────────
    filled += fillField(["school", "university", "college", "institution", "last school"], merged.school_1) ? 1 : 0;
    filled += fillField(["degree", "degree type", "highest degree", "level of education"], merged.degree_1) ? 1 : 0;
    filled += fillField(["graduation", "grad date", "graduated", "graduation year"], merged.graduation_1) ? 1 : 0;
    filled += fillField(["gpa", "grade point"], merged.gpa_1) ? 1 : 0;

    // ── Other ─────────────────────────────────────────────────────────────────
    filled += fillField(["salary", "compensation", "desired pay", "salary expectation", "expected salary"], merged.desired_salary) ? 1 : 0;
    filled += fillField(["start date", "available", "when can you start", "earliest start"], merged.available_start_date) ? 1 : 0;
    filled += fillField(["relocate", "willing to relocate"], merged.willing_to_relocate) ? 1 : 0;
    filled += fillField(["how did you hear", "how did you learn", "referred by", "source"], merged.how_did_you_hear) ? 1 : 0;
    filled += fillField(["preferred work arrangement", "work type", "remote", "work mode"], merged.preferred_work_arrangement) ? 1 : 0;

    // ── Custom/essay answers ─────────────────────────────────────────────────
    const custom = payload.custom_answers || {};
    const textareas = Array.from(document.querySelectorAll("textarea"));
    for (const [question, answer] of Object.entries(custom)) {
      if (!answer) continue;
      // Match the closest textarea whose surrounding label contains question keywords
      const qWords = question.toLowerCase().split(/\s+/).filter((w) => w.length > 4).slice(0, 3);
      const ta = textareas.find((el) => {
        const ft = fieldText(el);
        return qWords.some((w) => ft.includes(w));
      });
      if (ta && setElementValue(ta, answer)) filled++;
    }

    return filled;
  }

  async function runAutofill() {
    if (!currentJobHash) throw new Error("Job not saved. Click 'Save to HawkApply' first.");
    const { autofill } = await sendMsg({ type: "GET_AUTOFILL", jobHash: currentJobHash });
    const count = autofillForm(autofill);
    if (count === 0) throw new Error("No matching fields found on this page.");
    showToast(`✓ Autofilled ${count} field${count === 1 ? "" : "s"}`);
  }

  // ── Event wiring ──────────────────────────────────────────────────────────

  function renderContent(result, jobData) {
    const loading = document.getElementById("hawk-loading");
    const content = document.getElementById("hawk-content");
    if (!loading || !content) return;

    loading.style.display = "none";
    content.style.display = "block";

    if (result.found) {
      currentJob = result.job;
      currentJobHash = result.job.job_hash;
      content.innerHTML = renderFound(result.job, result.match);
    } else {
      content.innerHTML = renderNotFound();
    }

    attachEvents(jobData, result);
  }

  function attachEvents(jobData, result) {
    // Save
    document.getElementById("hawk-save-btn")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.textContent = "Saving…";
      try {
        const saved = await sendMsg({ type: "SAVE_JOB", data: { ...jobData, url: location.href } });
        currentJob = saved.job;
        currentJobHash = saved.job.job_hash;
        showToast("✓ Saved to HawkApply!");
        renderContent({ found: true, job: saved.job, match: null }, jobData);
      } catch (e) {
        btn.disabled = false;
        btn.textContent = "+ Save to HawkApply";
        showToast("✗ " + e.message);
      }
    });

    // Save + Autofill
    document.getElementById("hawk-quick-autofill")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.textContent = "Working…";
      try {
        const saved = await sendMsg({ type: "SAVE_JOB", data: { ...jobData, url: location.href } });
        currentJob = saved.job;
        currentJobHash = saved.job.job_hash;
        showToast("✓ Saved!");
        renderContent({ found: true, job: saved.job, match: null }, jobData);
        await runAutofill();
      } catch (e) {
        showToast("✗ " + e.message);
      } finally {
        btn.disabled = false;
        btn.textContent = "Save + Autofill";
      }
    });

    // Autofill
    document.getElementById("hawk-autofill-btn")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.textContent = "Filling…";
      try {
        await runAutofill();
      } catch (e) {
        showToast("✗ " + e.message);
      } finally {
        btn.disabled = false;
        btn.textContent = "Autofill Form";
      }
    });

    // Status change
    document.getElementById("hawk-status-select")?.addEventListener("change", async (e) => {
      const newStatus = e.target.value;
      try {
        await sendMsg({ type: "UPDATE_STATUS", jobHash: currentJobHash, status: newStatus });
        showToast(`Status → ${capitalize(newStatus)}`);
      } catch (e) {
        showToast("✗ " + e.message);
      }
    });

    // Dashboard
    document.getElementById("hawk-open-dashboard")?.addEventListener("click", () => {
      chrome.runtime.sendMessage({ type: "CHECK_SETTINGS" }, ({ dashboardUrl } = {}) => {
        window.open(`${(dashboardUrl || "http://localhost:3000").replace(/\/$/, "")}/jobs`, "_blank");
      });
    });

    // Collapse header
    const header = document.getElementById("hawk-header");
    const card = document.getElementById("hawk-card");
    if (header && card) {
      header.addEventListener("click", (e) => {
        // Don't collapse if the click was on a child interactive element
        if (e.target === header || e.target.id === "hawk-toggle" || e.target.classList.contains("hawk-title") || e.target.classList.contains("hawk-logo")) {
          card.classList.toggle("hawk-collapsed");
        }
      });
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  async function init() {
    if (!isLikelyJobPage()) return;

    const overlay = buildOverlay();
    document.body.appendChild(overlay);

    const jobData = extractJobData();

    // Auto-collapse if we couldn't extract a title
    if (!jobData.title) {
      document.getElementById("hawk-card")?.classList.add("hawk-collapsed");
    }

    try {
      const result = await sendMsg({ type: "LOOKUP_JOB", url: location.href });
      renderContent(result, jobData);
    } catch (e) {
      const loading = document.getElementById("hawk-loading");
      const content = document.getElementById("hawk-content");
      if (loading) loading.style.display = "none";
      if (content) {
        content.style.display = "block";
        content.innerHTML = renderError(e.message);
      }
    }
  }

  // Some SPAs render content after DOMContentLoaded; wait a beat
  function tryInit() {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => setTimeout(init, 800));
    } else {
      setTimeout(init, 500);
    }
  }

  tryInit();

  // Re-run on SPA navigation (LinkedIn, Google etc. update URL without reload)
  let _lastUrl = location.href;
  const _observer = new MutationObserver(() => {
    if (location.href !== _lastUrl) {
      _lastUrl = location.href;
      const old = document.getElementById("hawkapply-overlay");
      if (old) old.remove();
      currentJob = null;
      currentJobHash = null;
      setTimeout(init, 1000);
    }
  });
  _observer.observe(document.body, { childList: true, subtree: true });
})();
