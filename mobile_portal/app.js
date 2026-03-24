const repoBase = "https://github.com/hanjixiang1234-rgb/solo-template-business";
const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".panel");

const ideaForm = document.querySelector("#idea-form");
const learningForm = document.querySelector("#learning-form");
const copyButtons = document.querySelectorAll("[data-copy]");

const cloudApiBaseInput = document.querySelector("#cloud-api-base");
const cloudWriteTokenInput = document.querySelector("#cloud-write-token");
const saveCloudSettingsButton = document.querySelector("#save-cloud-settings");
const cloudSettingsStatus = document.querySelector("#cloud-settings-status");
const submissionStatus = document.querySelector("#submission-status");

const storageKeys = {
  idea: "minder_portal_draft_idea",
  learning: "minder_portal_draft_learning",
  cloudApiBase: "minder_portal_cloud_api_base",
  cloudWriteToken: "minder_portal_cloud_write_token",
};

function setActiveTab(tabName) {
  tabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === tabName);
  });
  panels.forEach((panel) => {
    panel.classList.toggle("active", panel.id === `panel-${tabName}`);
  });
}

function formToObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function buildIdeaTitle(data) {
  return `灵感：${(data.title || "").trim()}`;
}

function buildIdeaBody(data) {
  return [
    "### 灵感一句话",
    data.idea_summary || "",
    "",
    "### 为什么值得记下来",
    data.why_it_matters || "",
    "",
    "### 灵感归类",
    data.bucket || "",
    "",
    "### 你希望后面怎么处理",
    data.next_step || "",
  ].join("\n");
}

function buildLearningTitle(data) {
  return `学习请求：${(data.title || "").trim()}`;
}

function buildLearningBody(data) {
  return [
    "### 来源类型",
    data.source_type || "article",
    "",
    "### 来源链接",
    data.source_url || "",
    "",
    "### 来源标题（可选）",
    data.source_title || "",
    "",
    "### 你觉得它哪里好",
    data.why_good || "",
    "",
    "### 你希望我重点提炼什么",
    data.wanted_outputs || "",
    "",
    "### 补充说明（可选）",
    data.extra_context || "",
  ].join("\n");
}

function issueUrl({ title, body, labels }) {
  const params = new URLSearchParams({
    title,
    body,
    labels: labels.join(","),
  });
  return `${repoBase}/issues/new?${params.toString()}`;
}

function saveDraft(key, data) {
  window.localStorage.setItem(storageKeys[key], JSON.stringify(data));
}

function loadDraft(key, form) {
  const raw = window.localStorage.getItem(storageKeys[key]);
  if (!raw) return;
  try {
    const data = JSON.parse(raw);
    Object.entries(data).forEach(([name, value]) => {
      const field = form.elements.namedItem(name);
      if (!field) return;
      if (field instanceof RadioNodeList) {
        field.value = value;
        return;
      }
      field.value = value;
    });
  } catch (error) {
    console.warn("Failed to load draft", error);
  }
}

function saveCloudSettings() {
  window.localStorage.setItem(storageKeys.cloudApiBase, cloudApiBaseInput.value.trim());
  window.localStorage.setItem(storageKeys.cloudWriteToken, cloudWriteTokenInput.value.trim());
  updateCloudSettingsStatus();
}

function loadCloudSettings() {
  cloudApiBaseInput.value = window.localStorage.getItem(storageKeys.cloudApiBase) || "";
  cloudWriteTokenInput.value = window.localStorage.getItem(storageKeys.cloudWriteToken) || "";
  updateCloudSettingsStatus();
}

function currentCloudSettings() {
  return {
    apiBase: cloudApiBaseInput.value.trim().replace(/\/+$/, ""),
    writeToken: cloudWriteTokenInput.value.trim(),
  };
}

function hasCloudSubmitMode() {
  const { apiBase, writeToken } = currentCloudSettings();
  return Boolean(apiBase && writeToken);
}

function updateCloudSettingsStatus() {
  cloudSettingsStatus.textContent = hasCloudSubmitMode()
    ? "已启用 OpenAI Cloud Hub 直连模式。提交后不再依赖 GitHub。"
    : "还没填云端地址或口令，页面会自动回退到 GitHub 提交。";
}

function setSubmissionStatus(text, isError = false) {
  submissionStatus.textContent = text;
  submissionStatus.style.color = isError ? "#8c3211" : "#6d5538";
}

function copyText(text, button) {
  navigator.clipboard
    .writeText(text)
    .then(() => {
      const previous = button.textContent;
      button.textContent = "已复制";
      window.setTimeout(() => {
        button.textContent = previous;
      }, 1200);
    })
    .catch(() => {
      window.alert("复制失败，请长按手动复制。");
    });
}

async function submitToCloud(payload) {
  const { apiBase, writeToken } = currentCloudSettings();
  const response = await window.fetch(`${apiBase}/api/v1/submissions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${writeToken}`,
      "X-Minder-Client": "mobile-portal",
    },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `云端提交失败（${response.status}）`);
  }
  return data;
}

function fallbackToGitHub(kind, data) {
  if (kind === "idea") {
    window.location.assign(
      issueUrl({
        title: buildIdeaTitle(data),
        body: buildIdeaBody(data),
        labels: ["idea-inbox", "mobile-inbox"],
      })
    );
    return;
  }
  window.location.assign(
    issueUrl({
      title: buildLearningTitle(data),
      body: buildLearningBody(data),
      labels: ["learning-request", "mobile-inbox"],
    })
  );
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => setActiveTab(tab.dataset.tab));
});

saveCloudSettingsButton.addEventListener("click", saveCloudSettings);

ideaForm.addEventListener("input", () => saveDraft("idea", formToObject(ideaForm)));
learningForm.addEventListener("input", () => saveDraft("learning", formToObject(learningForm)));

ideaForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formToObject(ideaForm);
  saveDraft("idea", data);

  if (!hasCloudSubmitMode()) {
    setSubmissionStatus("当前未配置 OpenAI Cloud Hub，正在回退到 GitHub 提交。");
    fallbackToGitHub("idea", data);
    return;
  }

  try {
    setSubmissionStatus("正在提交到 OpenAI Cloud Hub...");
    const result = await submitToCloud({
      kind: "idea",
      title: data.title,
      idea_summary: data.idea_summary,
      why_it_matters: data.why_it_matters,
      bucket: data.bucket,
      next_step: data.next_step,
    });
    setSubmissionStatus(`灵感已进云端队列，任务 #${result.id} 已受理。`);
  } catch (error) {
    setSubmissionStatus(`${error.message}，正在回退到 GitHub。`, true);
    fallbackToGitHub("idea", data);
  }
});

learningForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formToObject(learningForm);
  saveDraft("learning", data);

  if (!hasCloudSubmitMode()) {
    setSubmissionStatus("当前未配置 OpenAI Cloud Hub，正在回退到 GitHub 提交。");
    fallbackToGitHub("learning", data);
    return;
  }

  try {
    setSubmissionStatus("正在提交到 OpenAI Cloud Hub...");
    const result = await submitToCloud({
      kind: "learning",
      title: data.title,
      source_type: data.source_type,
      source_url: data.source_url,
      source_title: data.source_title,
      why_good: data.why_good,
      wanted_outputs: data.wanted_outputs,
      extra_context: data.extra_context,
    });
    setSubmissionStatus(`学习请求已进云端队列，任务 #${result.id} 已受理。`);
  } catch (error) {
    setSubmissionStatus(`${error.message}，正在回退到 GitHub。`, true);
    fallbackToGitHub("learning", data);
  }
});

copyButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const kind = button.dataset.copy;
    if (kind === "idea") {
      copyText(buildIdeaBody(formToObject(ideaForm)), button);
      return;
    }
    copyText(buildLearningBody(formToObject(learningForm)), button);
  });
});

loadDraft("idea", ideaForm);
loadDraft("learning", learningForm);
loadCloudSettings();
