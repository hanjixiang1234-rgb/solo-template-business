const state = {
  status: null,
};

const els = {
  metrics: document.getElementById("metrics"),
  generatedAt: document.getElementById("generated-at"),
  incomingRequests: document.getElementById("incoming-requests"),
  upcomingPlan: document.getElementById("upcoming-plan"),
  publishRuns: document.getElementById("publish-runs"),
  inboxRuns: document.getElementById("inbox-runs"),
  postGallery: document.getElementById("post-gallery"),
  postSelect: document.getElementById("post-select"),
  refreshStatus: document.getElementById("refresh-status"),
  previewPlan: document.getElementById("preview-plan"),
  syncInbox: document.getElementById("sync-inbox"),
  queueForm: document.getElementById("queue-form"),
  ideaForm: document.getElementById("idea-form"),
  toast: document.getElementById("toast"),
};

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    els.toast.classList.add("hidden");
  }, 2600);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function renderMetrics(summary = {}) {
  const order = [
    ["pending", "待处理"],
    ["scheduled_native", "已原生定时"],
    ["published_manual_recovery", "人工恢复"],
    ["published_via_automation", "自动发布"],
  ];
  els.metrics.innerHTML = order
    .map(([key, label]) => {
      const value = summary[key] || 0;
      return `<div class="metric"><span class="tiny">${label}</span><strong>${value}</strong></div>`;
    })
    .join("");
}

function renderList(container, items, formatter, emptyMessage) {
  if (!items || items.length === 0) {
    container.innerHTML = `<div class="list-item"><span class="meta">${emptyMessage}</span></div>`;
    return;
  }
  container.innerHTML = items.map(formatter).join("");
}

function renderIncoming(items) {
  renderList(
    els.incomingRequests,
    items,
    (item) => `
      <div class="list-item">
        <strong>${item.name}</strong>
        <div class="meta">${item.modified_at}</div>
      </div>
    `,
    "收件箱现在是空的。"
  );
}

function renderPlan(items) {
  renderList(
    els.upcomingPlan,
    items,
    (item) => `
      <div class="plan-item">
        <strong>${item.post}</strong>
        <div class="meta">${item.slot === "morning" ? "早上" : "晚上"} · ${item.schedule_at}</div>
      </div>
    `,
    "目前没有待预演的排期。"
  );
}

function renderRuns(container, items, emptyMessage) {
  renderList(
    container,
    items,
    (item) => `
      <div class="list-item">
        <strong>${item.status || "unknown"}</strong>
        <div class="meta">${item.time || item.generated_at || ""}</div>
        <div>${item.post || item.message || item.trigger_label || ""}</div>
      </div>
    `,
    emptyMessage
  );
}

function renderPostOptions(posts) {
  els.postSelect.innerHTML = posts
    .map(
      (post) =>
        `<option value="${post.filename}">${post.filename} · ${post.title}</option>`
    )
    .join("");
}

function renderPostGallery(posts) {
  renderList(
    els.postGallery,
    posts,
    (post) => {
      const queueEntry = post.queue_entry || null;
      const badges = [];
      if (queueEntry?.status) {
        badges.push(
          `<span class="badge ${queueEntry.status === "pending" ? "pending" : "live"}">${queueEntry.status}</span>`
        );
      } else {
        badges.push('<span class="badge">未进队列</span>');
      }
      return `
        <article class="post-card">
          ${post.cover_url ? `<img src="${post.cover_url}" alt="${post.title}" />` : ""}
          <div class="post-card-body">
            <h3>${post.title}</h3>
            <div class="meta">${post.filename}</div>
            <p>${post.caption ? post.caption.slice(0, 68) + (post.caption.length > 68 ? "..." : "") : ""}</p>
            <div class="badge-row">${badges.join("")}</div>
          </div>
        </article>
      `;
    },
    "还没有可展示的帖子。"
  );
}

function renderStatus(status) {
  state.status = status;
  renderMetrics(status.queue_summary);
  renderIncoming(status.incoming_requests);
  renderPlan(status.upcoming_plan);
  renderRuns(els.publishRuns, status.recent_publish_runs, "还没有发布日志。");
  renderRuns(els.inboxRuns, status.recent_mobile_inbox_runs, "还没有收件箱日志。");
  renderPostOptions(status.posts);
  renderPostGallery(status.posts);
  els.generatedAt.textContent = status.generated_at || "";
}

async function refreshStatus() {
  const payload = await api("/api/status");
  renderStatus(payload);
}

async function handleQueueForm(event) {
  event.preventDefault();
  const slot = new FormData(els.queueForm).get("queue-slot");
  const payload = await api("/api/requests/queue-post", {
    method: "POST",
    body: JSON.stringify({
      post: els.postSelect.value,
      slot,
      note: document.getElementById("queue-note").value,
      import_now: true,
    }),
  });
  renderStatus(payload.status);
  document.getElementById("queue-note").value = "";
  showToast("帖子已经从手机面板送进本地队列。");
}

async function handleIdeaForm(event) {
  event.preventDefault();
  const slot = new FormData(els.ideaForm).get("idea-slot");
  const payload = await api("/api/requests/note-idea", {
    method: "POST",
    body: JSON.stringify({
      title: document.getElementById("idea-title").value,
      slot,
      notes: document.getElementById("idea-notes").value,
      import_now: true,
    }),
  });
  renderStatus(payload.status);
  document.getElementById("idea-title").value = "";
  document.getElementById("idea-notes").value = "";
  showToast("新想法已经写进收件箱并导入。");
}

async function runAction(kind) {
  if (kind === "preview") {
    const payload = await api("/api/actions/reconcile", {
      method: "POST",
      body: JSON.stringify({ dry_run: true }),
    });
    renderStatus(payload.status);
    showToast("排期预演已经刷新。");
    return;
  }
  if (kind === "sync") {
    const payload = await api("/api/actions/sync-inbox", {
      method: "POST",
      body: JSON.stringify({ dry_run: false }),
    });
    renderStatus(payload.status);
    showToast("收件箱已经真实导入。");
    return;
  }
  if (kind === "reconcile-live") {
    const confirmed = window.confirm("这会真实尝试把内容写进小红书原生定时。确定继续吗？");
    if (!confirmed) return;
    const payload = await api("/api/actions/reconcile", {
      method: "POST",
      body: JSON.stringify({ dry_run: false }),
    });
    renderStatus(payload.status);
    showToast(payload.ok ? "真实排期已执行。" : "真实排期执行后有报错，请看日志。");
  }
}

function bindEvents() {
  els.refreshStatus.addEventListener("click", refreshStatus);
  els.previewPlan.addEventListener("click", () => runAction("preview"));
  els.syncInbox.addEventListener("click", () => runAction("sync"));
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => runAction(button.dataset.action));
  });
  els.queueForm.addEventListener("submit", (event) => {
    handleQueueForm(event).catch((error) => showToast(error.message));
  });
  els.ideaForm.addEventListener("submit", (event) => {
    handleIdeaForm(event).catch((error) => showToast(error.message));
  });
}

bindEvents();
refreshStatus().catch((error) => showToast(error.message));
