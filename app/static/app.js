"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const statuses = [
  "Saved",
  "Applied",
  "Assessment",
  "Interview",
  "Offer",
  "Rejected",
  "Withdrawn",
];
const modes = ["Remote", "Hybrid", "On-site"];
const colors = [
  "#88847a",
  "#344f66",
  "#786888",
  "#b08225",
  "#43705a",
  "#b9472c",
  "#a39b8d",
];
let user,
  registerMode = false,
  charts = [],
  routeGeneration = 0,
  toastTimer;
const modal = $("#modal");
const badge = (s) => `<span class="badge ${esc(s)}">${esc(s)}</span>`;
const initials = (name) =>
  name
    .split(/\s+/)
    .map((x) => x[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
const day = (d) =>
  d
    ? new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      }).format(new Date(d + "T12:00:00Z"))
    : "—";
const moment = (d) =>
  new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: user.timezone,
    timeZoneName: "short",
  }).format(new Date(d));
const today = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: user.timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
const empty = (title, text) =>
  `<div class="empty"><span class="empty-symbol">↗</span><strong>${title}</strong>${text}</div>`;
const options = (values, selected = "", blank = "") =>
  (blank ? `<option value="">${blank}</option>` : "") +
  values
    .map(
      (v) =>
        `<option value="${esc(v)}" ${v === selected ? "selected" : ""}>${esc(v)}</option>`,
    )
    .join("");
const company = (a) =>
  `<div class="company-cell"><span class="company-icon">${esc(initials(a.company))}</span><div><a href="#application/${a.id}"><strong>${esc(a.company)}</strong></a><small>${esc(a.role)}</small></div></div>`;
function notify(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").hidden = true), 4500);
}
async function api(path, { method = "GET", body, ...rest } = {}) {
  const headers = {};
  if (method !== "GET") headers["X-CSRF-Token"] = user?.csrf || "";
  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch("/api" + path, {
    method,
    body,
    headers,
    credentials: "same-origin",
    ...rest,
  });
  } catch {
    throw Object.assign(new Error("We could not connect to the server. Check your connection and try again."), { status: 0 });
  }
  if (res.status === 204) return null;
  if (res.status === 401 && !path.includes("/auth/login")) showAuth(Boolean(user));
  let data;
  try {
    data = await res.json();
  } catch {
    throw Object.assign(new Error(res.ok
      ? "The server returned an unexpected response. Please refresh the page and try again."
      : `The request could not be completed (HTTP ${res.status}). Please try again.`), { status: res.status });
  }
  if (!res.ok) {
    throw Object.assign(new Error(
      (Array.isArray(data?.details) ? data.details.map((e) => `${e.field}: ${e.message}`).join("\n") : "") ||
        data?.error ||
        "Something went wrong. Please try again.",
    ), { status: res.status });
  }
  return data;
}
function showAuth(expired = false) {
  $("#recovery").hidden = true;
  if (expired && registerMode) $("#auth-toggle").click();
  $("#session-notice").hidden = !expired;
  $("#session-notice").textContent = expired ? "Your session has expired. Log in again to continue. Unsaved changes may need to be entered again." : "";
  user = null;
  $("#auth").hidden = false;
  $("#shell").hidden = true;
  modal.close();
}
function showShell() {
  $("#recovery").hidden = true;
  $("#auth").hidden = true;
  $("#shell").hidden = false;
  $("#profile-name").textContent = user.name;
  $("#avatar").textContent = initials(user.name);
  void autoEmailSync();
}
$("#auth-toggle").onclick = () => {
  registerMode = !registerMode;
  $("#name-field").hidden = !registerMode;
  $("#name-field input").required = registerMode;
  $("#auth-title").textContent = registerMode
    ? "Start your next chapter."
    : "Welcome back.";
  $("#auth-subtitle").textContent = registerMode
    ? "Create an account to track your internship applications."
    : "Log in to manage your internship applications.";
  $("#auth-submit").textContent = registerMode
    ? "Create account ↗"
    : "Log in ↗";
  $("#auth-question").textContent = registerMode
    ? "Already have an account?"
    : "New here?";
  $("#auth-toggle").textContent = registerMode ? "Log in" : "Create an account";
  $("#auth-form [name=password]").minLength = registerMode ? 10 : 0;
  $("#auth-form [name=password]").autocomplete = registerMode
    ? "new-password"
    : "current-password";
  $("#auth-error").textContent = "";
};
$("#auth-form").onsubmit = async (e) => {
  e.preventDefault();
  const button = $("#auth-submit");
  button.disabled = true;
  $("#auth-error").textContent = "";
  try {
    const data = Object.fromEntries(new FormData(e.target));
    user = await api("/auth/" + (registerMode ? "register" : "login"), {
      method: "POST",
      body: data,
    });
    e.target.reset();
    showShell();
    await route();
  } catch (error) {
    $("#auth-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
};
$("#logout").onclick = async () => {
  try {
    await api("/auth/logout", { method: "POST" });
    showAuth();
    notify("You’re logged out.");
  } catch (e) {
    notify(e.message);
  }
};
$("#menu").onclick = () => {
  const open = $("#sidebar").classList.toggle("open");
  $("#menu").setAttribute("aria-expanded", open);
};
$("#close-modal").onclick = () => modal.close();
modal.addEventListener("click", (e) => {
  if (
    e.target === modal &&
    (e.clientX < modal.getBoundingClientRect().left ||
      e.clientX > modal.getBoundingClientRect().right)
  )
    modal.close();
});
function dialog(title, html, onSubmit) {
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = html;
  if (!modal.open) modal.showModal();
  const form = $("#modal-body form");
  if (form)
    form.onsubmit = async (e) => {
      e.preventDefault();
      const b = form.querySelector("[type=submit]");
      b.disabled = true;
      form.querySelector(".error").textContent = "";
      try {
        await onSubmit(new FormData(form), form);
        modal.close();
        await route();
      } catch (err) {
        form.querySelector(".error").textContent = err.message;
      } finally {
        b.disabled = false;
      }
    };
  $("#modal-body [data-cancel]")?.addEventListener("click", () =>
    modal.close(),
  );
}
const formEnd = (label = "Save changes") =>
  `<p class="error" role="alert"></p><div class="form-actions"><button type="button" data-cancel>Cancel</button><button type="submit" class="primary">${label}</button></div></form>`;
const field = (label, name, value = "", type = "text", extra = "") =>
  `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
function heading(title, subtitle, buttons = "") {
  return `<div class="page-heading"><div><div class="eyebrow">THE OPPORTUNITY REGISTER</div><h1>${title}</h1><p>${subtitle}</p></div><div class="actions">${buttons}</div></div>`;
}
const addButton =
  '<button class="primary" data-action="new-app">＋ Add application</button>';
function linkTable(items) {
  return `<div class="table-wrap"><table><thead><tr><th>Company / role</th><th>Status</th><th>Applied</th><th></th></tr></thead><tbody>${items.map((a) => `<tr><td>${company(a)}</td><td>${badge(a.status)}</td><td>${day(a.application_date)}</td><td><a href="#application/${a.id}" aria-label="View ${esc(a.company)} application">↗</a></td></tr>`).join("")}</tbody></table></div>`;
}
async function dashboard() {
  const d = await api("/dashboard");
  return {
    html: `<div class="dashboard-layout"><div class="date-label">${new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: user.timezone }).format(new Date())}</div>${heading(`Hello, ${esc(user.name.split(" ")[0])}.`, "Track your applications, interviews, and next steps.", addButton)}<section class="metrics" aria-label="Application metrics">${[
      [
        "Applications submitted",
        d.submitted,
        "Saved jobs excluded",
        "▤",
        "#applications?group=submitted",
      ],
      [
        "Active applications",
        d.active,
        "Applications still in progress",
        "↗",
        "#applications?group=active",
      ],
      [
        "Offers received",
        d.offers,
        "Offers you have received",
        "✧",
        "#applications?status=Offer",
      ],
      [
        "Upcoming interviews",
        d.upcoming_interviews,
        "Scheduled interviews",
        "◷",
        "#interviews?upcoming=1",
      ],
    ]
      .map(
        ([label, n, hint, icon, href]) =>
          `<a class="metric" href="${href}"><span class="metric-icon">${icon}</span><span class="metric-label">${label}</span><strong>${n}</strong><small>${hint}</small></a>`,
      )
      .join(
        "",
      )}</section><div class="grid-bottom"><section class="panel"><div class="panel-heading"><h2>Recent applications</h2><a href="#applications">View all ↗</a></div>${d.recent.length ? linkTable(d.recent) : empty("No applications yet", "Add your first application to see your progress.")}</section><div class="stack"><section class="panel"><div class="panel-heading"><h2>Coming up next</h2><a href="#interviews?upcoming=1">View all ↗</a></div>${d.interviews.map((i) => `<a class="mini-item" href="#application/${i.application_id}"><span class="company-icon">◷</span><div class="grow"><strong>${esc(i.company)} · ${esc(i.title)}</strong><small>${moment(i.starts_at)}</small></div><span>↗</span></a>`).join("") || empty("No upcoming interviews", "Your upcoming interviews will appear here.")}</section><section class="panel"><div class="panel-heading"><h2>Stay in touch</h2><a href="#followups">View all ↗</a></div><p class="section-intro">${d.overdue_followups} overdue · ${d.today_followups} today · ${d.upcoming_followups} upcoming</p>${d.followups.map((f) => `<a class="mini-item" href="#application/${f.application_id}"><span class="company-icon">⚑</span><div><strong>${esc(f.company)}</strong><small>Follow up · ${day(f.due_date)}</small></div></a>`).join("") || empty("You’re all caught up", "Set a follow-up from an application.")}</section></div></div><div class="grid-charts"><section class="panel"><div class="panel-heading"><h2>Application activity</h2><small>All time · by submission date</small></div><div class="chart-wrap"><canvas id="activity-chart" role="img" aria-label="Applications submitted by date"></canvas></div><details class="chart-data"><summary>View chart data</summary><ul>${
      Object.entries(d.timeline)
        .map(([k, v]) => `<li>${day(k)}: ${v}</li>`)
        .join("") || "<li>No submitted applications yet.</li>"
    }</ul></details></section><section class="panel"><div class="panel-heading"><h2>Where you stand</h2><small>All applications</small></div><div class="chart-wrap"><canvas id="status-chart" role="img" aria-label="Current application status distribution"></canvas></div><details class="chart-data"><summary>View chart data</summary><ul>${statuses.map((s) => `<li>${s}: ${d.distribution[s] || 0}</li>`).join("")}</ul></details></section></div></div>`,
    after: () => {
      if (!window.Chart) {
        notify(
          "Charts could not load. Expand “View chart data” for the values.",
        );
        return;
      }
      Chart.defaults.font.family = '"Segoe UI", sans-serif';
      Chart.defaults.color = "#6c685f";
      Chart.defaults.font.size = 13;
      charts.push(
        new Chart($("#activity-chart"), {
          type: "line",
          data: {
            labels: Object.keys(d.timeline).map(day),
            datasets: [
              {
                data: Object.values(d.timeline),
                borderColor: "#c04427",
                backgroundColor: "#c04427",
                fill: false,
                tension: 0,
                pointRadius: 3,
                pointBackgroundColor: "#fff",
                pointBorderWidth: 2,
                borderWidth: 2,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              y: {
                beginAtZero: true,
                ticks: { precision: 0 },
                grid: { color: "#ded8cb" },
                border: { display: false },
              },
              x: {
                grid: { display: false },
                border: { display: false },
                ticks: { maxTicksLimit: 6, maxRotation: 0 },
              },
            },
          },
        }),
      );
      charts.push(
        new Chart($("#status-chart"), {
          type: "bar",
          data: {
            labels: statuses,
            datasets: [
              {
                data: statuses.map((s) => d.distribution[s] || 0),
                backgroundColor: colors,
                borderWidth: 0,
                barThickness: 10,
              },
            ],
          },
          options: {
            indexAxis: "y",
            scales: { x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#ded8cb" }, border: { display: false } }, y: { grid: { display: false }, border: { display: false } } },
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                display: false,
                labels: {
                  boxWidth: 8,
                  boxHeight: 8,
                  usePointStyle: true,
                  padding: 15,
                  font: { size: 10 },
                },
              },
            },
          },
        }),
      );
    },
  };
}
async function applications(params) {
  const d = await api("/applications?" + params);
  const query = params.get("q") || "";
  return {
    html:
      heading(
        "Applications",
        "Manage your internship applications in one place.",
        `<button data-action="import">Import CSV</button><a class="text-button" href="/api/applications/export">Export ↗</a>${addButton}`,
      ) +
      `<form id="filters" class="filters"><label class="search">Search<input name="q" value="${esc(query)}" placeholder="Company or role…"></label><label>Status<select name="status">${options(statuses, params.get("status"), "All statuses")}</select></label><label>Work mode<select name="work_mode">${options(modes, params.get("work_mode"), "All work modes")}</select></label><label>Applied from<input type="date" name="date_from" value="${esc(params.get("date_from") || "")}"></label><label>Applied to<input type="date" name="date_to" value="${esc(params.get("date_to") || "")}"></label><label>Sort<select name="sort">${[
        ["newest", "Newest first"],
        ["oldest", "Oldest first"],
        ["deadline", "Nearest deadline"],
        ["company", "Company A–Z"],
      ]
        .map(
          ([k, v]) =>
            `<option value="${k}" ${params.get("sort") === k ? "selected" : ""}>${v}</option>`,
        )
        .join(
          "",
        )}</select></label><button type="submit">Filter</button><a class="text-button" href="#applications">Reset</a></form>${params.get("group") ? `<div class="notice">Showing ${esc(params.get("group"))} applications. <a href="#applications">Clear filter</a></div>` : ""}<section class="panel"><div class="panel-heading"><h2>All opportunities <small>(${d.total})</small></h2></div>${d.items.length ? `<div class="table-wrap"><table><thead><tr><th>Company / role</th><th>Status</th><th>Location</th><th>Applied</th><th>Deadline</th><th></th></tr></thead><tbody>${d.items.map((a) => `<tr><td>${company(a)}</td><td>${badge(a.status)}</td><td>${esc(a.location) || "—"}<br><small>${esc(a.work_mode)}</small></td><td>${day(a.application_date)}</td><td>${day(a.deadline)}</td><td><a href="#application/${a.id}" aria-label="View ${esc(a.company)}">Open ↗</a></td></tr>`).join("")}</tbody></table></div>` : empty("No applications here yet", "Add an opportunity or adjust your filters.")}<div class="pager"><span>${d.total} applications · Page ${d.page} of ${Math.max(1, Math.ceil(d.total / d.page_size))}</span><div class="actions"><button data-page-number="${d.page - 1}" ${d.page === 1 ? "disabled" : ""}>← Previous</button><button data-page-number="${d.page + 1}" ${d.page * d.page_size >= d.total ? "disabled" : ""}>Next →</button></div></div></section>`,
    after: () => {
      $("#filters").onsubmit = (e) => {
        e.preventDefault();
        const next = new URLSearchParams();
        for (const [k, v] of new FormData(e.target)) if (v) next.set(k, v);
        if (params.get("group")) next.set("group", params.get("group"));
        location.hash = "applications?" + next;
      };
      document.querySelectorAll("[data-page-number]").forEach(
        (b) =>
          (b.onclick = () => {
            params.set("page", b.dataset.pageNumber);
            location.hash = "applications?" + params;
          }),
      );
    },
  };
}
async function applicationForm(id) {
  const [a, resumes] = await Promise.all([
    id
      ? api("/applications/" + id)
      : Promise.resolve({ status: "Saved", work_mode: "Remote" }),
    api("/resumes"),
  ]);
  dialog(
    id ? "Edit application" : "Add an application",
    `<form><p class="form-hint">Keep the essentials together. Fields marked * are required.</p><div class="form-grid">${field("Company *", "company", a.company, "text", 'required maxlength="160"')}${field("Role title *", "role", a.role, "text", 'required maxlength="160"')}${field("Job posting URL", "job_url", a.job_url, "url", 'maxlength="2000"')}${field("Location", "location", a.location, "text", 'maxlength="160"')}<label>Work mode<select name="work_mode">${options(modes, a.work_mode)}</select></label><label>Status<select name="status">${options(statuses, a.status)}</select></label>${field("Application date (required unless the status is Saved)", "application_date", a.application_date, "date")}${field("Application deadline", "deadline", a.deadline, "date")}${field("Stipend / salary", "salary", a.salary, "text", 'maxlength="160"')}${field("Recruiter name", "recruiter_name", a.recruiter_name, "text", 'maxlength="100"')}${field("Recruiter email", "recruiter_email", a.recruiter_email, "email")}<label>Résumé version<select name="resume_id"><option value="">No résumé attached</option>${resumes.map((r) => `<option value="${r.id}" ${r.id === a.resume_id ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select></label><label class="span-two">Notes<textarea name="notes" maxlength="20000">${esc(a.notes)}</textarea></label></div>${formEnd(id ? "Save changes" : "Add application")}`,
    async (fd) => {
      const data = Object.fromEntries(fd);
      for (const k of ["application_date", "deadline"])
        data[k] = data[k] || null;
      data.resume_id = data.resume_id ? Number(data.resume_id) : null;
      const saved = await api("/applications" + (id ? "/" + id : ""), {
        method: id ? "PUT" : "POST",
        body: data,
      });
      notify(id ? "Application updated" : "Application added");
      location.hash = "application/" + saved.id;
    },
  );
}
async function attachResume(id) {
  const [application, list] = await Promise.all([
    api(`/applications/${id}`),
    api("/resumes"),
  ]);
  dialog(
    application.resume_id ? "Change attached résumé" : "Attach a résumé",
    `<form><p class="form-hint">Choose a saved résumé or upload a new PDF for ${esc(application.company)}. Your files are private to your account.</p><label>Résumé<select name="resume_id">${list.map((r) => `<option value="${r.id}" ${r.id === application.resume_id ? "selected" : ""}>${esc(r.name)}</option>`).join("")}<option value="upload">Upload a new PDF…</option></select></label><div id="resume-upload-fields">${field("Résumé name *", "name", "", "text", 'maxlength="100" placeholder="e.g. Software engineering résumé"')}<label>PDF file *<input name="file" type="file" accept="application/pdf,.pdf"></label><p class="form-hint">Choose a PDF that is not password-protected. Uploading also saves it in Your résumés.</p></div>${formEnd("Attach résumé")}`,
    async (fd, form) => {
      let resumeId = fd.get("resume_id");
      let uploaded = false;
      if (resumeId === "upload") {
        const body = new FormData();
        const name = String(fd.get("name") || "").trim();
        if (!name) throw new Error("Enter a name for your résumé.");
        body.set("name", name);
        body.set("file", fd.get("file"));
        const resume = await api("/resumes", { method: "POST", body });
        // Keep a successful upload selected if attachment fails, so retrying
        // does not upload the same file again.
        const option = new Option(resume.name, String(resume.id));
        form.elements.resume_id.add(option, 0);
        form.elements.resume_id.value = String(resume.id);
        form.elements.resume_id.dispatchEvent(new Event("change"));
        resumeId = resume.id;
        uploaded = true;
      }
      try {
        await api(`/applications/${id}/resume`, {
          method: "PATCH", body: { resume_id: Number(resumeId) },
        });
      } catch (error) {
        throw new Error(uploaded
          ? `Your résumé was uploaded, but could not be attached. It is saved in Your résumés. Try attaching it again. ${error.message}`
          : error.message);
      }
      notify("Résumé attached");
    },
  );
  const form = $("#modal-body form");
  const syncUpload = () => {
    const uploading = form.elements.resume_id.value === "upload";
    $("#resume-upload-fields").hidden = !uploading;
    for (const input of $("#resume-upload-fields").querySelectorAll("input")) {
      input.disabled = !uploading;
      input.required = uploading;
    }
  };
  form.elements.resume_id.onchange = syncUpload;
  syncUpload();
}
function detachResume(id) {
  dialog("Detach résumé?",
    `<form><p>The résumé will be removed from this application. The file will remain in Your résumés and on any other applications.</p>${formEnd("Detach résumé")}`,
    async () => {
      await api(`/applications/${id}/resume`, { method: "PATCH", body: { resume_id: null } });
      notify("Résumé detached");
    },
  );
}

async function detail(id) {
  const [a, resumes] = await Promise.all([
    api("/applications/" + id),
    api("/resumes"),
  ]);
  const r = resumes.find((r) => r.id === a.resume_id);
  return {
    html: `<a href="#applications" class="text-button">← All applications</a><div class="page-heading"><div class="detail-top"><span class="company-icon">${esc(initials(a.company))}</span><div><h1>${esc(a.company)}</h1><p>${esc(a.role)}</p></div></div><div class="actions"><button data-action="edit-app" data-id="${id}">Edit application</button><button class="danger" data-action="delete-app" data-id="${id}">Delete</button></div></div><div class="detail-grid"><div class="stack"><section class="panel"><div class="panel-heading"><h2>Application overview</h2>${badge(a.status)}</div><div class="facts">${[
      ["Location", a.location || "Not specified"],
      ["Work mode", a.work_mode],
      ["Applied", day(a.application_date)],
      ["Deadline", day(a.deadline)],
      ["Compensation", a.salary || "Not specified"],
      ["Recruiter", a.recruiter_name || "Not specified"],
      ["Recruiter email", a.recruiter_email || "Not specified"],
    ]
      .map(([k, v]) => `<div class="fact"><small>${k}</small>${esc(v)}</div>`)
      .join(
        "",
      )}<div class="fact"><small>Job posting</small>${a.job_url ? `<a href="${esc(a.job_url)}" target="_blank" rel="noopener noreferrer">View listing ↗</a>` : "Not specified"}</div><div class="fact"><small>Attached résumé</small>${r ? `<a href="/api/resumes/${r.id}/download">${esc(r.name)} ↓</a>` : "No résumé attached"}<div class="attachment-actions"><button class="text-button" data-action="attach-resume" data-id="${id}">${r ? "Change résumé" : "＋ Attach résumé"}</button>${r ? `<button class="text-button" data-action="detach-resume" data-id="${id}">Detach</button>` : ""}</div></div><div class="fact"><small>Last updated</small>${moment(a.updated_at)}</div></div></section><section class="panel"><div class="panel-heading"><h2>Your notes</h2></div><div class="notes">${esc(a.notes) || '<span class="muted">Add notes about this application.</span>'}</div></section><section class="panel"><div class="panel-heading"><h2>Interviews</h2><button class="text-button" data-action="new-interview" data-app="${id}">＋ Add round</button></div>${a.interviews.length ? a.interviews.map((i) => interviewItem(i, a.company)).join("") : empty("No interviews scheduled", "Schedule an interview when a date is confirmed.")}</section><section class="panel"><div class="panel-heading"><h2>Follow-ups</h2><button class="text-button" data-action="new-followup" data-app="${id}">＋ Schedule</button></div>${a.follow_ups.map((f) => followupItem(f, a.company)).join("") || empty("No follow-ups scheduled", "Schedule a follow-up to keep the conversation going.")}</section></div><section class="panel"><div class="panel-heading"><h2>Status history</h2></div><label>Move to<select data-status-app="${id}" data-original="${a.status}" data-date="${a.application_date || ""}">${options(statuses, a.status)}</select></label><ul class="history">${a.history.map((h) => `<li>${badge(h.status)}<small>${moment(h.changed_at)}</small></li>`).join("")}</ul></section></div>`,
  };
}
async function board() {
  const groups = await Promise.all(
    statuses.map((status) =>
      api("/applications?" + new URLSearchParams({ status, page_size: 20 })),
    ),
  );
  return {
    html:
      heading(
        "Status board",
        "Track each application by its current status.",
        addButton,
      ) +
      `<div class="notice">Use the status menu to update an application. Each change is recorded in its history.</div><div class="board">${groups.map((g, i) => `<section class="board-column"><h2>${statuses[i]} <span>${g.total}</span></h2>${g.items.map((a) => `<article class="board-card"><a href="#application/${a.id}"><h3>${esc(a.company)}</h3></a><p>${esc(a.role)}</p><small>${esc(a.work_mode)} · ${day(a.application_date)}</small><label class="board-count">Move application<select data-status-app="${a.id}" data-original="${a.status}" data-date="${a.application_date || ""}">${options(statuses, a.status)}</select></label></article>`).join("") || '<div class="empty">No applications with this status.</div>'}${g.total > 20 ? `<a class="board-more" href="#applications?status=${statuses[i]}">View all ${g.total} applications →</a>` : ""}</section>`).join("")}</div>`,
  };
}
function interviewItem(i, companyName = i.company) {
  const date = new Date(i.starts_at);
  const datePart = (options) => new Intl.DateTimeFormat(undefined, { ...options, timeZone: user.timezone }).format(date);
  return `<div class="mini-item interview-row"><div class="interview-date" aria-hidden="true"><span>${esc(datePart({ month: "short" }))}</span><strong>${esc(datePart({ day: "numeric" }))}</strong><span>${esc(datePart({ weekday: "short" }))}</span></div><div class="grow"><strong>${esc(companyName)} · ${esc(i.title)}</strong><small>${moment(i.starts_at)} · ${esc(i.type)}</small><p class="notes">${esc(i.venue)}${i.notes ? "\n" + esc(i.notes) : ""}${i.outcome ? "\nOutcome: " + esc(i.outcome) : ""}</p><div class="row-actions"><button data-action="edit-interview" data-id="${i.id}">Edit</button><button data-action="delete-interview" data-id="${i.id}">Delete</button><a href="#application/${i.application_id}">Application ↗</a></div></div></div>`;
}
async function interviews(params) {
  const list = await api(
    "/interviews" + (params.has("upcoming") ? "?upcoming=true" : ""),
  );
  return {
    html:
      heading(
        "Interviews",
        "Manage interview dates, preparation notes, and feedback.",
        `<button class="primary" data-action="new-interview">＋ Schedule interview</button>`,
      ) +
      `<div class="view-switch"><a href="#interviews?upcoming=1" ${params.has("upcoming") ? 'aria-current="page"' : ""}>Upcoming</a><a href="#interviews" ${!params.has("upcoming") ? 'aria-current="page"' : ""}>All interviews</a><span>Times shown in ${esc(user.timezone)}</span></div><section class="panel">${list.map((i) => interviewItem(i)).join("") || empty("No interviews scheduled", "Schedule an interview and prepare for your next step.")}</section>`,
  };
}
async function applicationOptions() {
  let all = [],
    page = 1;
  while (true) {
    const d = await api(`/applications?page_size=100&page=${page++}`);
    all.push(...d.items);
    if (all.length >= d.total) break;
  }
  return all;
}
async function interviewForm(id, appId) {
  const [list, apps] = await Promise.all([
    id ? api("/interviews") : Promise.resolve([]),
    applicationOptions(),
  ]);
  const i = list.find((x) => x.id === id) || {};
  if (!apps.length) {
    notify("Add an application before scheduling an interview.");
    return;
  }
  // The browser datetime-local input represents the device timezone. Convert it to UTC explicitly.
  const local = i.starts_at
    ? new Date(
        new Date(i.starts_at).getTime() -
          new Date(i.starts_at).getTimezoneOffset() * 60000,
      )
        .toISOString()
        .slice(0, 16)
    : "";
  dialog(
    id ? "Edit interview" : "Schedule an interview",
    `<form><div class="form-grid">${!id ? `<label class="span-two">Application<select name="application_id">${apps.map((a) => `<option value="${a.id}" ${a.id === appId ? "selected" : ""}>${esc(a.company)} — ${esc(a.role)}</option>`).join("")}</select></label>` : ""}${field("Round / title *", "title", i.title, "text", 'required maxlength="160"')}<label>Type<select name="type">${options(["Online", "Phone", "In-person"], i.type || "Online")}</select></label>${field("Date and time * (device time zone)", "starts_at", local, "datetime-local", "required")}${field("Interview time zone (e.g. Asia/Kolkata) *", "timezone", i.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone, "text", "required")}<p class="form-hint span-two">Enter the time in your device’s time zone (${esc(Intl.DateTimeFormat().resolvedOptions().timeZone)}). It will be displayed in the time zone selected in Settings. The interview time zone records the organizer’s time zone.</p>${field("Meeting link / venue", "venue", i.venue)}<label class="span-two">Preparation notes<textarea name="notes">${esc(i.notes)}</textarea></label><label class="span-two">Outcome / feedback<textarea name="outcome">${esc(i.outcome)}</textarea></label></div>${formEnd(id ? "Save interview" : "Schedule interview")}`,
    async (fd) => {
      const data = Object.fromEntries(fd);
      const application = data.application_id;
      delete data.application_id;
      data.starts_at = new Date(data.starts_at).toISOString();
      await api(
        id ? "/interviews/" + id : `/applications/${application}/interviews`,
        { method: id ? "PUT" : "POST", body: data },
      );
      notify("Interview saved");
    },
  );
}
function followupItem(f, companyName = f.company) {
  return `<div class="mini-item followup-row"><span class="company-icon">⚑</span><div class="grow"><strong>${esc(companyName)}</strong><small>${day(f.due_date)} · ${f.completed_at ? "Completed" : f.bucket || "Pending"}</small></div><div class="row-actions">${!f.completed_at ? `<button data-action="complete-followup" data-id="${f.id}">Complete</button><button data-action="edit-followup" data-id="${f.id}" data-date="${f.due_date}">Edit</button>` : '<span class="badge Offer">Done</span>'}<button data-action="delete-followup" data-id="${f.id}">Delete</button></div></div>`;
}
async function followups() {
  const list = await api("/follow-ups");
  return {
    html:
      heading(
        "Follow-ups",
        "Keep track of when to contact recruiters.",
        `<button class="primary" data-action="new-followup">＋ Schedule follow-up</button>`,
      ) +
      ["overdue", "today", "upcoming", "completed"]
        .map(
          (b) =>
            `<section class="followup-group" data-bucket="${b}"><h2 class="subheading">${b === "today" ? "Due today" : b} · ${list.filter((f) => f.bucket === b).length}</h2><div class="panel">${
              list
                .filter((f) => f.bucket === b)
                .map((f) => followupItem(f))
                .join("") || `<p class="muted">${b === "today" ? "No follow-ups due today." : `No ${b} follow-ups.`}</p>`
            }</div></section>`,
        )
        .join(""),
  };
}
async function followupForm(id, appId, date) {
  const apps = await applicationOptions();
  if (!apps.length) {
    notify("Add an application first.");
    return;
  }
  dialog(
    id ? "Reschedule follow-up" : "Schedule a follow-up",
    `<form>${!id ? `<label>Application<select name="application_id">${apps.map((a) => `<option value="${a.id}" ${a.id === appId ? "selected" : ""}>${esc(a.company)} — ${esc(a.role)}</option>`).join("")}</select></label>` : ""}${field("Follow-up date *", "due_date", date || "", "date", "required")}${formEnd("Save follow-up")}`,
    async (fd) => {
      const data = Object.fromEntries(fd);
      await api(
        id
          ? "/follow-ups/" + id
          : `/applications/${data.application_id}/follow-ups`,
        { method: id ? "PUT" : "POST", body: { due_date: data.due_date } },
      );
      notify("Follow-up saved");
    },
  );
}
function completeFollowup(id) {
  dialog(
    "Complete follow-up",
    `<form><p class="section-intro">Mark this follow-up as completed. You can also schedule your next reminder.</p>${field("Next follow-up date (optional)", "next_date", "", "date")}${formEnd("Mark completed")}`,
    async (fd) => {
      await api(`/follow-ups/${id}/complete`, {
        method: "POST",
        body: { next_date: fd.get("next_date") || null },
      });
      notify("Follow-up completed");
    },
  );
}
async function resumes() {
  const list = await api("/resumes");
  return {
    html:
      heading(
        "Your résumés",
        "Upload and manage your résumé versions.",
        `<button class="primary" data-action="upload">＋ Upload résumé</button>`,
      ) +
      `<p class="section-intro">Your PDFs are private. Open an application and select Attach résumé to choose a saved file or upload a new one.</p><div class="cards">${list.map((r) => `<article class="panel resume-card"><div class="pdf">PDF</div><div><h2>${esc(r.name)}</h2><p>${Math.ceil(r.size / 1024)} KB · Uploaded ${moment(r.created_at)}</p></div><div class="actions"><a href="/api/resumes/${r.id}/download" class="text-button">Download ↓</a><button class="danger" data-action="delete-resume" data-id="${r.id}">Delete</button></div></article>`).join("")}</div>${!list.length ? empty("No résumés uploaded", "Upload a PDF résumé to get started.") : ""}`,
  };
}
function upload() {
  dialog(
    "Upload a résumé",
    `<form><p class="form-hint">Choose a PDF that is not password-protected. Your file will remain private to your account.</p>${field("Résumé name *", "name", "", "text", 'required maxlength="100" placeholder="e.g. Backend Resume"')}<label>PDF file *<input name="file" type="file" accept="application/pdf,.pdf" required></label>${formEnd("Upload résumé")}`,
    async (fd) => {
      await api("/resumes", { method: "POST", body: fd });
      notify("Résumé uploaded");
    },
  );
}
function confirmDelete(kind, id) {
  const paths = {
    app: "/applications/",
    interview: "/interviews/",
    followup: "/follow-ups/",
    resume: "/resumes/",
  };
  const names = {
    app: "application",
    interview: "interview",
    followup: "follow-up",
    resume: "résumé",
  };
  dialog(
    `Delete ${names[kind]}?`,
    `<form><p>${kind === "app" ? "This removes the application, interviews, follow-ups, and status history." : kind === "resume" ? "This deletes the file and removes its associations. Your applications are retained." : "This removes the record permanently."}</p><p class="form-hint">This action cannot be undone.</p>${formEnd("Delete " + names[kind])}`,
    async () => {
      await api(paths[kind] + id, { method: "DELETE" });
      notify("Deleted");
      if (kind === "app") location.hash = "applications";
    },
  );
}
async function importDialog() {
  dialog(
    "Import applications",
    `<form><p class="form-hint">Start with the <a href="/api/applications/template">CSV template ↓</a>. Import up to 500 rows. Matching company + role (case-insensitive) + application date are skipped as duplicates. All other rows must be valid before saving.</p><label>CSV file<input type="file" name="csv" accept=".csv,text/csv" required></label><div id="csv-preview"></div><p class="error" role="alert"></p><div class="form-actions"><button type="button" data-cancel>Cancel</button><button type="submit" class="primary">Preview import</button></div></form>`,
    async () => {},
  );
  const form = $("#modal-body form");
  let text = "",
    ready = false;
  form.elements.csv.onchange = () => {
    ready = false;
    $("#csv-preview").innerHTML = "";
    form.querySelector("[type=submit]").textContent = "Preview import";
  };
  form.onsubmit = async (e) => {
    e.preventDefault();
    const b = form.querySelector("[type=submit]");
    b.disabled = true;
    form.querySelector(".error").textContent = "";
    try {
      if (ready) {
        const result = await api("/applications/import", {
          method: "POST",
          body: { text },
        });
        modal.close();
        notify(
          `${result.imported} imported · ${result.skipped} duplicates skipped`,
        );
        await route();
      } else {
        const file = form.elements.csv.files[0];
        if (file.size > 1000000) throw new Error("CSV must be under 1 MB");
        text = await file.text();
        const p = await api("/applications/import/preview", {
          method: "POST",
          body: { text },
        });
        $("#csv-preview").innerHTML =
          `<p class="notice">${p.ready} ready to import${p.has_errors ? " · Fix errors and select the corrected file." : ""}</p><div class="table-wrap"><table><thead><tr><th>Row</th><th>Company</th><th>Result</th></tr></thead><tbody>${p.rows.map((r) => `<tr><td>${r.row}</td><td>${esc(r.company)}</td><td>${esc(r.error || r.result)}</td></tr>`).join("")}</tbody></table></div>`;
        ready = !p.has_errors && p.ready > 0;
        b.textContent = ready
          ? "Import " + p.ready + " applications"
          : "Preview import";
      }
    } catch (err) {
      form.querySelector(".error").textContent = err.message;
    } finally {
      b.disabled = false;
    }
  };
}
async function settings() {
  return {
    html:
      heading("Settings", "Manage your name and time zone.") +
      `<section class="panel settings-form"><h2>Personal details</h2><form id="settings-form">${field("Your name", "name", user.name, "text", 'required maxlength="100"')}${field("Email address", "email", user.email, "email", "disabled")}${field("Display time zone", "timezone", user.timezone, "text", "required")}<p class="form-hint">Enter a full time zone, such as Asia/Kolkata, Europe/London, or America/New_York. Interviews and follow-up reminders use this time zone.</p><p class="error" role="alert"></p><button class="primary">Save preferences</button></form></section>`,
    after: () => {
      $("#settings-form").onsubmit = async (e) => {
        e.preventDefault();
        const form = e.target;
        const button = form.querySelector("button");
        form.querySelector(".error").textContent = "";
        button.disabled = true;
        try {
          user = await api("/auth/me", {
            method: "PATCH",
            body: Object.fromEntries(new FormData(e.target)),
          });
          showShell();
          form.elements.timezone.value = user.timezone;
          notify("Preferences saved");
        } catch (err) {
          form.querySelector(".error").textContent = err.message;
        } finally {
          button.disabled = false;
        }
      };
    },
  };
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-action]");
  if (!b) return;
  const id = Number(b.dataset.id),
    appId = Number(b.dataset.app);
  try {
    switch (b.dataset.action) {
      case "new-app":
        await applicationForm();
        break;
      case "edit-app":
        await applicationForm(id);
        break;
      case "delete-app":
        confirmDelete("app", id);
        break;
      case "new-interview":
        await interviewForm(null, appId);
        break;
      case "edit-interview":
        await interviewForm(id);
        break;
      case "delete-interview":
        confirmDelete("interview", id);
        break;
      case "new-followup":
        await followupForm(null, appId);
        break;
      case "edit-followup":
        await followupForm(id, null, b.dataset.date);
        break;
      case "complete-followup":
        completeFollowup(id);
        break;
      case "delete-followup":
        confirmDelete("followup", id);
        break;
      case "upload":
        upload();
        break;
      case "attach-resume":
        await attachResume(id);
        break;
      case "detach-resume":
        detachResume(id);
        break;
      case "delete-resume":
        confirmDelete("resume", id);
        break;
      case "import":
        await importDialog();
        break;
    }
  } catch (err) {
    notify(err.message);
  }
});
document.addEventListener("change", async (e) => {
  const el = e.target;
  if (!el.matches("[data-status-app]")) return;
  const status = el.value,
    id = el.dataset.statusApp;
  el.disabled = true;
  try {
    if (status !== "Saved" && !el.dataset.date) {
      el.value = el.dataset.original;
      dialog(
        "When did you apply?",
        `<form><p>Moving to ${esc(status)} requires an application date.</p>${field("Application date *", "application_date", today(), "date", "required")}${formEnd("Move application")}`,
        async (fd) => {
          await api(`/applications/${id}/status`, {
            method: "PATCH",
            body: { status, application_date: fd.get("application_date") },
          });
          notify("Status updated");
        },
      );
    } else {
      await api(`/applications/${id}/status`, {
        method: "PATCH",
        body: { status },
      });
      notify("Status updated");
      await route();
    }
  } catch (err) {
    el.value = el.dataset.original;
    notify(err.message);
  } finally {
    el.disabled = false;
  }
});
function errorPage(status, missingRecord = false) {
  const pages = {
    404: ["404", missingRecord ? "RECORD NOT FOUND" : "PAGE NOT FOUND", "A wrong turn. Not a dead end.", missingRecord ? "This application is unavailable. It may have been deleted or may not belong to your account." : "This page does not exist. Check the address or return to your workspace."],
    403: ["403", "ACCESS RESTRICTED", "This page is out of reach.", "You do not have permission to open this page. Return to your workspace to continue."],
    0: ["—", "CONNECTION INTERRUPTED", "Let’s reconnect.", "We could not reach the server. Check your internet connection and try again."],
  };
  const [code, label, title, message] = pages[status] || ["500", "TEMPORARILY UNAVAILABLE", "A pause in the process.", "We could not load this page. Please try again shortly."];
  return `<section class="error-page" aria-labelledby="error-title"><div class="error-code" aria-hidden="true">${code}</div><div class="error-copy"><div class="eyebrow">${label}</div><h1 id="error-title">${title}</h1><p>${message}</p><div class="actions">${status !== 404 && status !== 403 ? '<button class="primary" data-retry>Try again ↗</button>' : ''}<a class="${status === 404 || status === 403 ? 'primary recovery-link' : 'text-button'}" href="/#dashboard">Go to dashboard ↗</a><a class="text-button" href="/#applications">View applications</a></div><p class="error-footnote">${status === 404 ? "Your next opportunity is still ahead." : "Your saved records remain in your workspace."}</p></div></section>`;
}
function validRoute(path) {
  return /^(dashboard|applications|board|interviews|followups|resumes|settings|emails)$/.test(path) || /^application\/[1-9]\d*$/.test(path);
}
async function route() {
  if (!user) return;
  const generation = ++routeGeneration;
  const hash = location.hash.slice(1) || "dashboard";
  const [path, query = ""] = hash.split("?");
  const [page, id] = path.split("/");
  const params = new URLSearchParams(query);
  $("#sidebar").classList.remove("open");
  $("#menu").setAttribute("aria-expanded", "false");
  document
    .querySelectorAll("[data-page]")
    .forEach((el) =>
      el.classList.toggle(
        "active",
        el.dataset.page === (page === "application" ? "applications" : page),
      ),
    );
  const titles = {
    dashboard: "Dashboard",
    applications: "Applications",
    application: "Application details",
    board: "Status board",
    interviews: "Interviews",
    followups: "Follow-ups",
    resumes: "Résumés",
    settings: "Settings",
    emails: "Email sync",
  };
  $("#breadcrumb").innerHTML =
    `Workspace <span>/</span> ${validRoute(path) ? titles[page] : "Page not found"}`;
  $("#main").innerHTML =
    '<p class="loading" role="status">Loading your workspace…</p>';
  charts.forEach((c) => c.destroy());
  charts = [];
  if (!validRoute(path)) {
    $("#main").innerHTML = errorPage(404);
    document.title = "Page not found · InternTrack";
    $("#main").focus();
    return;
  }
  document.title = `${titles[page]} · InternTrack`;
  try {
    const render = {
      dashboard,
      applications,
      board,
      interviews,
      followups,
      resumes,
      settings,
      emails,
    }[page];
    const result =
      page === "application"
        ? await detail(Number(id))
        : await render(params);
    if (generation !== routeGeneration || !user) return;
    $("#main").innerHTML = result.html;
    result.after?.();
  } catch (err) {
    if (generation !== routeGeneration || !user) return;
    $("#main").innerHTML = errorPage(err.status, page === "application");
    document.title = "Unable to load page · InternTrack";
    $("#main [data-retry]")?.addEventListener("click", route);
    $("#main").focus();
  }
}
window.addEventListener("hashchange", route);
async function bootstrap() {
  try {
    user = await api("/auth/me");
    showShell();
    await route();
  } catch (err) {
    if (err.status === 401) return;
    $("#auth").hidden = true;
    $("#shell").hidden = true;
    const recovery = $("#recovery");
    recovery.hidden = false;
    recovery.innerHTML = errorPage(err.status);
    recovery.querySelector("[data-retry]")?.addEventListener("click", bootstrap);
    // With no session loaded, navigation must retry startup rather than route().
    recovery.querySelectorAll("a").forEach((link) => link.addEventListener("click", (event) => {
      event.preventDefault();
      location.hash = new URL(link.href).hash;
      bootstrap();
    }));
    recovery.focus();
  }
}
bootstrap();

/* Google login and Gmail review queue. Mail content is always escaped as text. */
let emailSyncRunning = false;
async function syncEmails(manual = false) {
  if (!user || emailSyncRunning) return;
  emailSyncRunning = true;
  try {
    const result = await api('/google/sync', { method: 'POST' });
    if (manual || result.added) notify(`${result.added} new emails ready to review.${result.has_more ? ' More messages remain; sync again to continue.' : ''}`);
    // Avoid replacing a form the user is currently reviewing.
    if (location.hash.startsWith('#emails') && !modal.open) await route();
  } catch (error) {
    if (manual) notify(error.message);
  } finally {
    emailSyncRunning = false;
  }
}
async function autoEmailSync() {
  if (!user || document.hidden || emailSyncRunning) return;
  try {
    const connection = await api('/google/status');
    if (connection.connected) await syncEmails();
  } catch { /* Manual sync displays actionable connection errors. */ }
}
setInterval(autoEmailSync, 5 * 60 * 1000);

async function emails(params = new URLSearchParams()) {
  const page = Math.max(1, Number(params.get('page')) || 1);
  const [connection, queue] = await Promise.all([api('/google/status'), api('/google/emails?page=' + page)]);
  return {
    html: heading('Email sync', 'Turn application emails into a clear next step.') + `
      <section class="panel email-connection">
        <h2>${connection.connected ? 'Gmail connected' : 'Connect your Gmail'}</h2>
        <p>${connection.connected ? esc(connection.email) : 'Connect the Google account matching your InternTrack email. This also enables Google login for an existing password account.'}</p>
        <p class="muted">Read-only access finds application confirmations and recruitment updates from Indeed, LinkedIn and other senders. Review each suggestion before saving it. No email is sent or modified.</p>
        <p class="muted">The first sync checks the past 90 days, 50 messages at a time. Sync runs every five minutes while InternTrack is open. Email formats vary; some messages may not be detected.</p>
        ${connection.last_synced_at ? `<p>Last completed sync: ${esc(moment(connection.last_synced_at))}</p>` : ''}
        ${connection.has_more ? '<p class="notice">More messages remain. Select Sync now to fetch the next batch.</p>' : ''}
        ${!connection.gmail_configured ? '<p class="notice">Google integration needs server configuration. See the Google setup section in the project README.</p>' : ''}
        <div class="actions">
          <button id="connect-gmail" ${!connection.gmail_configured ? 'disabled' : ''}>${connection.connected ? 'Reconnect Gmail' : 'Connect Google + Gmail'}</button>
          ${connection.connected ? '<button id="sync-gmail" class="primary">Sync now</button><button id="disconnect-gmail">Disconnect Gmail</button>' : ''}
        </div>
      </section>
      <section class="panel email-queue"><h2>Ready to review (${queue.total})</h2>
        ${queue.items.length ? queue.items.map(item => `<article class="email-item">
          <div>${badge(item.suggested_status)} <span class="muted">${esc(moment(item.received_at))}</span></div>
          <h3>${esc(item.subject)}</h3><p class="muted">${esc(item.sender)}</p><p>${esc(item.snippet)}</p>
          <div class="actions"><button class="primary" data-email-review="${item.id}">Review application</button><button data-email-dismiss="${item.id}">Dismiss</button></div>
        </article>`).join('') : '<p class="muted">No emails waiting for review. Connect Gmail and sync to find application updates.</p>'}
        <div class="actions">${page > 1 ? `<a href="#emails?page=${page-1}">Previous</a>` : ''}${page * 25 < queue.total ? `<a href="#emails?page=${page+1}">Next</a>` : ''}</div>
      </section>`,
    after: () => {
      $('#connect-gmail').onclick = async (event) => {
        event.target.disabled = true;
        try { const result = await api('/google/connect', { method: 'POST' }); location.assign(result.url); }
        catch (error) { notify(error.message); event.target.disabled = false; }
      };
      $('#sync-gmail')?.addEventListener('click', async (event) => {
        event.target.disabled = true;
        await syncEmails(true);
        event.target.disabled = false;
      });
      $('#disconnect-gmail')?.addEventListener('click', () => {
        dialog('Disconnect Gmail?', `<form><p>This stops email syncing and deletes the email review queue. Saved applications and Google login remain available. You can also remove access in your Google account permissions.</p>${formEnd('Disconnect Gmail')}`, async () => {
          await api('/google/disconnect', { method: 'POST' });
          notify('Gmail disconnected.');
        });
      });
      document.querySelectorAll('[data-email-review]').forEach(button => button.onclick = async () => {
        button.disabled = true;
        try { await reviewEmail(queue.items.find(item => item.id === Number(button.dataset.emailReview))); }
        catch (error) { notify(error.message); }
        finally { button.disabled = false; }
      });
      document.querySelectorAll('[data-email-dismiss]').forEach(button => button.onclick = async () => {
        button.disabled = true;
        try { await api(`/google/emails/${button.dataset.emailDismiss}/dismiss`, { method: 'POST' }); await route(); }
        catch (error) { notify(error.message); button.disabled = false; }
      });
    },
  };
}
async function reviewEmail(item) {
  // Fetch all pages so existing records beyond the first hundred can be selected.
  const apps = [];
  let page = 1, result;
  do {
    result = await api(`/applications?page_size=100&page=${page++}`);
    apps.push(...result.items);
  } while (apps.length < result.total);
  dialog('Review email suggestion', `<form>
    <p>${esc(item.subject)}</p><p class="muted">Suggestions can be wrong. Check the company, role, date and status before saving.</p>
    <label>Save to<select name="application_id" id="email-target"><option value="">Create a new application</option>${apps.map(a => `<option value="${a.id}">${esc(a.company)} — ${esc(a.role)} (${esc(a.status)})</option>`).join('')}</select></label>
    <div id="email-new-fields">${field('Company *', 'company', item.company, 'text', 'required maxlength="160"')}${field('Role *', 'role', item.role, 'text', 'required maxlength="160"')}</div>
    <label>Status<select name="status">${options(statuses, item.suggested_status)}</select></label>
    ${field('Application date (check against the original application)', 'application_date', item.received_at.slice(0,10), 'date', 'required')}
    ${formEnd('Save application')}`, async (fd) => {
      const data = Object.fromEntries(fd);
      data.application_id = data.application_id ? Number(data.application_id) : null;
      await api(`/google/emails/${item.id}/import`, { method: 'POST', body: data });
      notify('Application saved.');
    });
  $('#email-target').onchange = (event) => {
    const existing = Boolean(event.target.value);
    $('#email-new-fields').hidden = existing;
    $('#email-new-fields').querySelectorAll('input').forEach(input => { input.disabled = existing; input.required = !existing; });
    const selected = apps.find(a => a.id === Number(event.target.value));
    if (selected?.application_date) $('#modal-body [name=application_date]').value = selected.application_date;
  };
}
const googleResult = new URLSearchParams(location.search).get('google');
if (googleResult) {
  const messages = {
    not_configured: 'Google sign-in is not available yet. Use email and password until setup is complete.',
    signed_in: 'Signed in with Google. Connect Gmail to sync application emails.',
    connected: 'Gmail connected. Your application emails will appear here for review.',
    cancelled: 'Google authorization was cancelled. You can try again.',
    invalid_state: 'Google sign-in expired or was opened in a different browser. Please try again.',
    link_required: 'This email already has an account. Log in with your password, then connect Google in Email sync.',
    wrong_account: 'Choose the Google account with the same email as your InternTrack account.',
    missing_permission: 'Gmail read permission was not granted. Connect again and allow email access.',
    failed: 'Google connection failed. Check server configuration or try connecting again.',
  };
  const message = messages[googleResult] || messages.failed;
  $('#auth-error').textContent = message;
  notify(message);
  history.replaceState(null, '', '/' + location.hash);
}
