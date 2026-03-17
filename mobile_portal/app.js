const repoBase = "https://github.com/hanjixiang1234-rgb/solo-template-business";
const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".panel");

const ideaForm = document.querySelector("#idea-form");
const learningForm = document.querySelector("#learning-form");
const copyButtons = document.querySelectorAll("[data-copy]");

const storageKeys = {
  idea: "minder_portal_draft_idea",
  learning: "minder_portal_draft_learning",
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

tabs.forEach((tab) => {
  tab.addEventListener("click", () => setActiveTab(tab.dataset.tab));
});

ideaForm.addEventListener("input", () => saveDraft("idea", formToObject(ideaForm)));
learningForm.addEventListener("input", () => saveDraft("learning", formToObject(learningForm)));

ideaForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const data = formToObject(ideaForm);
  saveDraft("idea", data);
  window.location.assign(
    issueUrl({
      title: buildIdeaTitle(data),
      body: buildIdeaBody(data),
      labels: ["idea-inbox", "mobile-inbox"],
    })
  );
});

learningForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const data = formToObject(learningForm);
  saveDraft("learning", data);
  window.location.assign(
    issueUrl({
      title: buildLearningTitle(data),
      body: buildLearningBody(data),
      labels: ["learning-request", "mobile-inbox"],
    })
  );
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
