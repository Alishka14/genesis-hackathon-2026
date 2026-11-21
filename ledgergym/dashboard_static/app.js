"use strict";

// Only aggregate metrics and public episode files are requested. No truth.
const $ = (id) => document.getElementById(id);
const state = {
  episodes: { train: [], dev: [] }, page: 0, loading: false, requestId: 0,
  replaySteps: [], replayStep: 0, replayRequestId: 0, replayFormat: null,
  findingsRequestId: 0, highlightId: null,
};
const labels = {
  reconciliation: "Reconciliation",
  oracle: "Oracle (upper bound)",
  seeded_random: "Seeded Random",
  mark_all: "Mark All",
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

async function getJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error("HTTP " + response.status);
  return response.json();
}

function setText(id, value) {
  const target = $(id);
  if (target) target.textContent = String(value);
}

function fmt(value, decimals = 2) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-US", {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  });
}

function renderSummary(summary) {
  const reconciliation = summary.policies?.reconciliation ?? {};
  const replay = summary.replay ?? {};
  setText("metric-episodes", reconciliation.episodes ?? "—");
  setText("metric-tp", reconciliation.tp ?? "—");
  setText("metric-fp", reconciliation.fp ?? "—");
  setText("metric-replays",
    String(replay.score_matches ?? "—") + "/" + String(replay.trajectories ?? "—"));
  setText("dataset-kind",
    summary.kind === "synthetic_company_development_with_settlements"
      ? "V1 + V2 · SETTLEMENT CONTROLS"
      : "SYNTHETIC DEVELOPMENT DATASET");

  const container = $("policy-bars");
  container.replaceChildren();
  for (const name of ["reconciliation", "oracle", "seeded_random", "mark_all"]) {
    const data = summary.policies?.[name] ?? {};
    const value = Number(data.mean_reward);
    const valid = Number.isFinite(value);
    const capped = valid ? Math.min(1, Math.max(-1, value)) : 0;
    const row = el("div", "policy-row");
    const title = el("span", "policy-name", labels[name]);
    const track = el("div", "policy-track");
    track.setAttribute("role", "img");
    track.setAttribute("aria-label", labels[name] + ": " + (valid ? fmt(value, 4) : "нет данных"));
    const fill = el("div", "policy-fill");
    if (capped < 0) fill.classList.add("negative");
    fill.style.left = String(capped < 0 ? 50 + capped * 50 : 50) + "%";
    fill.style.width = String(Math.abs(capped) * 50) + "%";
    track.append(fill);
    const stat = el("span", "policy-value", valid ? fmt(value, 4) : "—");
    row.append(title, track, stat);
    container.append(row);
  }
}

function updateEpisodes() {
  const split = $("split-select").value;
  const select = $("episode-select");
  select.replaceChildren();
  for (const item of state.episodes[split] ?? []) {
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = item.name.toUpperCase().replace("-", " #");
    select.append(option);
  }
  state.page = 0;
  state.highlightId = null;
  void loadRecords();
  void loadReplay();
  void loadFindings();
}

function cellValue(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function renderRecords(report) {
  const rows = Array.isArray(report.records) ? report.records : [];
  const head = $("record-head");
  const body = $("record-body");
  head.replaceChildren();
  body.replaceChildren();
  // Never hide amounts behind Object.keys(...).slice(0, 7): judges need
  // invoice totals, payment amounts and ledger debit/credit at a glance.
  const preferred = {
    invoices: ["invoice_id", "doc_id", "entity_id", "currency", "total_minor",
               "issued_at", "due_at", "line_items"],
    payments: ["payment_id", "doc_id", "kind", "currency", "amount_minor",
               "timestamp", "remittance_invoice_id", "invoice_refs"],
    ledger: ["row_id", "timestamp", "account", "debit_minor", "credit_minor",
             "currency", "invoice_id", "payment_id", "reporting_period"],
    fx: ["rate_id", "date", "source_currency", "target_currency", "rate"],
  };
  const keys = rows.length > 0 ? Object.keys(rows[0]) : [];
  const fields = [...new Set([...(preferred[report.table] ?? []), ...keys])]
    .filter((key) => keys.includes(key)).slice(0, 10);
  if (!fields.length) {
    const tr = el("tr");
    tr.append(el("td", "", "На этой странице нет записей"));
    body.append(tr);
  } else {
    const header = el("tr");
    for (const field of fields) header.append(el("th", "", field.replaceAll("_", " ")));
    head.append(header);
    for (const record of rows) {
      const tr = el("tr");
      if (state.highlightId && ["invoice_id", "payment_id", "row_id", "rate_id", "doc_id"]
        .some((key) => record[key] === state.highlightId)) tr.classList.add("evidence-highlight");
      for (const field of fields) {
        const full = cellValue(record[field]);
        const td = el("td", "", full);
        td.title = full.slice(0, 500);
        tr.append(td);
      }
      body.append(tr);
    }
  }
  const pages = Math.max(1, Math.ceil((report.total ?? 0) / 50));
  setText("page-status", String(state.page + 1) + " / " + String(pages));
  setText("record-status",
    String(rows.length) + " из " + String(report.total ?? 0) +
    " публичных записей · " + String(report.table));
  setText("explorer-meta",
    String(report.accounting_model ?? "DEV") + " · " +
    String(report.manifest?.schema_version ?? "SCHEMA"));
  $("prev-page").disabled = state.page === 0;
  $("next-page").disabled = state.page + 1 >= pages;
}

async function loadRecords() {
  const split = $("split-select").value;
  const episode = $("episode-select").value;
  const table = $("table-select").value;
  if (!episode) return;
  const requestId = ++state.requestId;
  state.loading = true;
  $("prev-page").disabled = true;
  $("next-page").disabled = true;
  setText("record-status", "Загрузка публичных записей…");
  try {
    const query = new URLSearchParams({ split, episode, table, page: String(state.page) });
    const report = await getJson("/api/records?" + query.toString());
    if (requestId !== state.requestId) return;
    renderRecords(report);
  } catch (error) {
    if (requestId !== state.requestId) return;
    setText("record-status", "Ошибка локальной загрузки: " + String(error.message));
    const tr = el("tr");
    tr.append(el("td", "", "Не удалось прочитать публичные данные"));
    $("record-body").replaceChildren(tr);
  } finally {
    if (requestId === state.requestId) state.loading = false;
  }
}

// Search the existing allowlisted public-data API only. Never fetch private
// source files or use arbitrary paths supplied by evidence IDs.
async function inspectPublicEvidence(id, preview) {
  const split = $("split-select").value;
  const episode = $("episode-select").value;
  preview.textContent = "Поиск публичного документа…";
  try {
    for (const table of ["invoices", "payments", "ledger", "fx"]) {
      for (let page = 0; page < 40; page += 1) {
        if (split !== $("split-select").value || episode !== $("episode-select").value) return;
        const query = new URLSearchParams({split, episode, table, page: String(page)});
        const result = await getJson("/api/records?" + query.toString());
        const rows = Array.isArray(result.records) ? result.records : [];
        const matched = rows.find((record) =>
          ["invoice_id", "payment_id", "row_id", "rate_id", "doc_id"]
            .some((key) => record[key] === id));
        if (matched) {
          preview.replaceChildren();
          preview.append(el("strong", "", "Публичный источник: " + table));
          const list = el("dl", "evidence-fields");
          for (const key of ["doc_id", "invoice_id", "payment_id", "row_id",
                             "rate_id", "total_minor", "amount_minor",
                             "debit_minor", "credit_minor", "currency",
                             "timestamp", "issued_at", "date", "rate"]) {
            if (matched[key] === undefined || matched[key] === null) continue;
            list.append(el("dt", "", key.replaceAll("_", " ")),
                        el("dd", "", cellValue(matched[key])));
          }
          preview.append(list);
          const link = el("button", "evidence-open", "Показать запись в Company Explorer");
          link.type = "button";
          link.addEventListener("click", () => {
            if (split !== $("split-select").value ||
                episode !== $("episode-select").value) return;
            state.page = page;
            state.highlightId = id;
            $("table-select").value = table;
            void loadRecords();
            $("explorer").scrollIntoView({behavior: "smooth", block: "start"});
          });
          preview.append(link);
          return;
        }
        if (rows.length === 0 || (page + 1) * 50 >= Number(result.total)) break;
      }
    }
    preview.textContent = "Доказательство не найдено среди доступных публичных записей.";
  } catch (error) {
    preview.textContent = "Не удалось открыть публичный источник: " + String(error.message);
  }
}

function renderFindings(report) {
  setText("findings-count", report.count ?? "—");
  setText("findings-scope", String(report.accounting_model ?? "development") +
    " · public-rule checker · not hidden truth");
  const root = $("findings-list");
  root.replaceChildren();
  const items = Array.isArray(report.findings) ? report.findings : [];
  if (items.length === 0) {
    root.append(el("div", "findings-clean",
      "Расхождений по поддерживаемым финансовым правилам не найдено. Это не означает независимую аудиторскую сертификацию."));
    return;
  }
  for (const [index, finding] of items.entries()) {
    const card = el("article", "finding-card");
    const header = el("div", "finding-head");
    header.append(
      el("span", "finding-index", String(index + 1).padStart(2, "0")),
      el("strong", "finding-type", String(finding.type ?? "unknown_issue")),
    );
    const amount = el("div", "finding-amount",
      String(finding.claimed_amount_minor ?? "—") + " minor · " +
      String(finding.currency ?? "—"));
    const meaning = {
      duplicate_invoice: "Возможное повторное обязательство за ту же услугу",
      payment_allocation: "Несоответствие распределения платежа документам",
      fx_rate_or_date: "Неверная дата курса или валютный пересчёт",
      reporting_period: "Неверный отчётный месяц для операции",
    };
    const description = el("p", "finding-explanation",
      meaning[finding.type] ?? "Отклонение от поддерживаемой учётной политики");
    const note = el("p", "finding-explanation",
      "Сумма minor — сумма претензии или разницы в минимальных денежных единицах. " +
      "Это не всегда полная сумма счёта; первичные документы доступны ниже.");
    const affectedLabel = el("div", "finding-label", "AFFECTED RECORDS");
    const affected = el("div", "finding-tags");
    for (const id of Array.isArray(finding.affected_ids) ? finding.affected_ids : []) {
      affected.append(el("span", "finding-tag", String(id)));
    }
    const evidenceLabel = el("div", "finding-label", "PUBLIC EVIDENCE IDS");
    const evidence = el("div", "finding-tags evidence");
    const evidencePreview = el("div", "evidence-preview", "Нажми на evidence ID, чтобы открыть публичную запись.");
    for (const id of Array.isArray(finding.evidence_ids) ? finding.evidence_ids : []) {
      const button = el("button", "finding-tag evidence-link", String(id));
      button.type = "button";
      button.title = "Найти публичное доказательство " + String(id);
      button.addEventListener("click", () => void inspectPublicEvidence(id, evidencePreview));
      evidence.append(button);
    }
    card.append(header, amount, description, note,
      affectedLabel, affected, evidenceLabel, evidence, evidencePreview);
    if (finding.explanation) {
      card.append(el("p", "finding-explanation", String(finding.explanation)));
    }
    root.append(card);
  }
}

async function loadFindings() {
  const split = $("split-select").value;
  const episode = $("episode-select").value;
  const request = ++state.findingsRequestId;
  setText("findings-count", "—");
  setText("findings-scope", "Загрузка результатов проверки…");
  $("findings-list").replaceChildren(el("div", "loading", "Проверка публичных правил…"));
  if (!episode) return;
  try {
    const params = new URLSearchParams({ split, episode });
    const report = await getJson("/api/findings?" + params.toString());
    if (request !== state.findingsRequestId) return;
    renderFindings(report);
  } catch (error) {
    if (request !== state.findingsRequestId) return;
    setText("findings-scope", "Проверка недоступна");
    $("findings-list").replaceChildren(
      el("div", "loading", "Ошибка публичной сверки: " + String(error.message)));
  }
}

function displayReplayStep() {
  const steps = state.replaySteps;
  const current = steps[state.replayStep];
  const buttons = $("replay-steps").querySelectorAll("button");
  buttons.forEach((button, index) => {
    button.classList.toggle("is-selected", index === state.replayStep);
    button.setAttribute("aria-current", index === state.replayStep ? "step" : "false");
  });
  if (!current) {
    setText("replay-action", "—");
    setText("replay-description", "Нет записанных действий.");
    setText("replay-position", "—");
    $("replay-prev").disabled = true;
    $("replay-next").disabled = true;
    return;
  }
  const action = String(current.action ?? "unknown_action");
  setText("replay-position", String(state.replayStep + 1) + " / " + String(steps.length));
  setText("replay-action", action);
  let description = "Шаг проверки финансовых доказательств.";
  if (action === "list_records") {
    description = "Чтение публичных записей таблицы: " + String(current.table ?? "—");
  } else if (action === "get_document") {
    description = "Чтение документа, доступного агенту.";
  } else if (action === "get_record") {
    description = "Чтение одной публичной записи.";
  } else if (action === "calculator") {
    description = "Проверка арифметического выражения.";
  } else if (action === "submit") {
    description = "Отправка находок на оценивание. В закрытом режиме результат скрыт от агента.";
  }
  setText("replay-description", description);
  setText("replay-records", current.records_seen ?? "—");
  setText("replay-findings", current.findings_submitted ?? "—");
  setText("replay-reward",
    typeof current.reward === "number" && Number.isFinite(current.reward)
      ? fmt(current.reward, 4) : "—");
  setText("replay-status",
    current.terminated === true ? "Завершено" :
      current.truncated === true ? "Остановлено" :
        current.terminated === null ? "Actions only" : "Продолжение");
  $("replay-prev").disabled = state.replayStep === 0;
  $("replay-next").disabled = state.replayStep === steps.length - 1;
}

function showReplay(report) {
  const parent = $("replay-steps");
  parent.replaceChildren();
  state.replaySteps = Array.isArray(report.steps) ? report.steps : [];
  state.replayStep = 0;
  state.replayFormat = report.format;
  for (const [index, step] of state.replaySteps.entries()) {
    const button = el("button", "replay-event");
    button.type = "button";
    const count = el("span", "replay-event-count", String(index + 1).padStart(2, "0"));
    const action = el("strong", "", String(step.action ?? "unknown"));
    const hint = el("small", "", String(step.table ?? (step.terminated ? "TERMINATED" : "ACTION")));
    button.append(count, action, hint);
    button.addEventListener("click", () => {
      state.replayStep = index;
      displayReplayStep();
    });
    parent.append(button);
  }
  setText("replay-mode", report.format === "full_transitions"
    ? "Полные переходы · development"
    : "Только actions · legacy");
  displayReplayStep();
}

async function loadReplay() {
  const split = $("split-select").value;
  const episode = $("episode-select").value;
  const policy = $("replay-policy").value;
  const request = ++state.replayRequestId;
  state.replaySteps = [];
  setText("replay-mode", "Загрузка траектории…");
  $("replay-steps").replaceChildren(el("div", "loading", "Чтение записанных шагов…"));
  $("replay-prev").disabled = true;
  $("replay-next").disabled = true;
  if (!episode) return;
  try {
    const query = new URLSearchParams({ split, episode, policy });
    const report = await getJson("/api/replay?" + query.toString());
    if (request !== state.replayRequestId) return;
    showReplay(report);
  } catch (error) {
    if (request !== state.replayRequestId) return;
    setText("replay-mode", "Траектория недоступна");
    setText("replay-description", "Ошибка загрузки: " + String(error.message));
    $("replay-steps").replaceChildren(el("div", "loading", "Траектория не найдена."));
    displayReplayStep();
  }
}

function renderResearch(response) {
  const root = $("research-cards");
  root.replaceChildren();
  if (!response || response.status !== "available") {
    setText("research-state", "NOT RUN · Запусти research_report для исходного 10+10 датасета.");
    return;
  }
  const report = response.report ?? {};
  setText("research-state",
    "AGGREGATE DEVELOPMENT REPORT · " + String(report.episodes ?? "—") +
    " эпизодов · независимая проверка не заявлена");
  for (const name of ["reconciliation", "seeded_random", "mark_all", "oracle"]) {
    const metrics = report.policies?.[name];
    if (!metrics) continue;
    const panel = el("article", "research-card");
    panel.append(el("div", "research-name", labels[name] ?? name));
    const fp = el("div", "research-number", String(metrics.fp ?? "—") + " FP");
    panel.append(fp);
    const faa = metrics.faa ?? {};
    const list = el("div", "research-tags");
    const keys = [
      ["FP_standard_valid", "STANDARD"],
      ["FP_hard_negative", "HARD NEGATIVE"],
      ["FP_duplicate", "DUPLICATE"],
      ["FP_unattributed", "UNATTRIBUTED"],
    ];
    for (const [key, label] of keys) {
      list.append(el("span", "research-tag", label + " · " + String(faa[key] ?? "—")));
    }
    panel.append(list);
    const fpr = el("p", "research-footnote");
    function formatRate(value) {
      return typeof value === "number" && Number.isFinite(value)
        ? fmt(value * 100, 0) + "%" : "N/A";
    }
    fpr.textContent =
      "Clean standard: " + formatRate(metrics.standard_valid_case_fpr) +
      " · Hard negative: " + formatRate(metrics.hard_negative_case_fpr) +
      " · Invariance: " + String(metrics.invariance_trials_passed ?? "—");
    panel.append(fpr);
    root.append(panel);
  }
}

async function loadResearch() {
  try {
    const report = await getJson("/api/research");
    renderResearch(report);
  } catch (error) {
    setText("research-state", "Результаты диагностики недоступны: " +
      String(error.message));
  }
}

function bindControls() {
  $("split-select").addEventListener("change", updateEpisodes);
  $("episode-select").addEventListener("change", () => {
    state.page = 0;
    void loadRecords();
    void loadReplay();
    void loadFindings();
  });
  $("table-select").addEventListener("change", () => {
    state.page = 0;
    void loadRecords();
  });
  $("prev-page").addEventListener("click", () => {
    if (state.page > 0 && !state.loading) {
      state.page -= 1;
      void loadRecords();
    }
  });
  $("next-page").addEventListener("click", () => {
    if (!state.loading) {
      state.page += 1;
      void loadRecords();
    }
  });
  $("replay-policy").addEventListener("change", () => void loadReplay());
  $("replay-prev").addEventListener("click", () => {
    if (state.replayStep > 0) {
      state.replayStep -= 1;
      displayReplayStep();
    }
  });
  $("replay-next").addEventListener("click", () => {
    if (state.replayStep + 1 < state.replaySteps.length) {
      state.replayStep += 1;
      displayReplayStep();
    }
  });
  const nav = document.querySelectorAll(".nav-link");
  for (const link of nav) {
    link.addEventListener("click", () => {
      for (const other of nav) other.classList.remove("is-active");
      link.classList.add("is-active");
    });
  }
}

async function init() {
  bindControls();
  try {
    const results = await Promise.all([
      getJson("/api/summary"),
      getJson("/api/episodes"),
    ]);
    state.episodes = results[1];
    renderSummary(results[0]);
    updateEpisodes();
    void loadResearch();
  } catch (error) {
    setText("dataset-kind", "Ошибка: " + String(error.message));
    setText("record-status", "Проверь запуск с --dataset или --demo.");
    $("policy-bars").replaceChildren(el("div", "loading", "Нет локального отчёта."));
  }
}

document.addEventListener("DOMContentLoaded", init);
