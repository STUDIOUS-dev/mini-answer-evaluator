(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const HISTORY_KEY = "mae.history.v1";
  const THEME_KEY = "mae.theme";
  const HISTORY_LIMIT = 15;

  const SAMPLES = [
    {
      label: "Physics — Ohm's law",
      question: "State Ohm's law and write its formula. Give the SI unit of resistance.",
      answer: "Ohm's law says that current through a conductor is directly proportional to the voltage across it, provided temperature stays constant. V = IR where V is voltage, I is current and R is resistance. Resistance is measured in ohms.",
    },
    {
      label: "Maths — integration",
      question: "Integrate x^2 * e^x with respect to x.",
      answer: "Using integration by parts twice: ∫x²eˣ dx = x²eˣ − ∫2x eˣ dx = x²eˣ − 2(x eˣ − eˣ) + C = eˣ(x² − 2x + 2) + C",
    },
    {
      label: "English — theme of a poem",
      question: "Explain the central theme of the poem 'The Road Not Taken' and how the poet conveys it.",
      answer: "The poem is about choices. The poet is in a wood and sees two roads and picks one. He says it made all the difference. The tone is kind of thoughtful.",
    },
  ];

  const els = {
    form: $("#eval-form"),
    question: $("#question"),
    answer: $("#answer"),
    rubricSelect: $("#rubric-select"),
    matchInfo: $("#match-info"),
    rubricCriteria: $("#rubric-criteria"),
    rubricInstructions: $("#rubric-instructions"),
    includeBlind: $("#include-blind"),
    formError: $("#form-error"),
    submit: $("#submit-btn"),
    clear: $("#clear-btn"),
    sample: $("#sample-select"),
    empty: $("#empty-state"),
    loading: $("#loading"),
    resultView: $("#result-view"),
    apiStatus: $("#api-status"),
  };

  let rubrics = [];
  let autoRubricId = null;
  let lastResult = null;
  let inFlight = null;

  // ── Helpers ──────────────────────────────────────────────
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null) continue;
      if (k === "class") node.className = v;
      else if (k === "style") node.style.cssText = v;
      else node.setAttribute(k, v);
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  function scoreColor(pct) {
    if (pct == null) return "var(--muted)";
    if (pct >= 70) return "var(--good)";
    if (pct >= 40) return "var(--warn)";
    return "var(--bad)";
  }

  function readStore(key, fallback) {
    try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; }
    catch { return fallback; }
  }
  function writeStore(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
  }

  // ── Theme ────────────────────────────────────────────────
  function initTheme() {
    const saved = readStore(THEME_KEY, null);
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = saved || (prefersDark ? "dark" : "light");
    $("#theme-toggle").addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      writeStore(THEME_KEY, next);
    });
  }

  // ── Counters ─────────────────────────────────────────────
  function updateCounter(textarea) {
    const counter = document.querySelector(`.counter[data-for="${textarea.id}"]`);
    const max = Number(textarea.getAttribute("maxlength"));
    counter.textContent = `${textarea.value.length.toLocaleString()} / ${max.toLocaleString()}`;
    counter.classList.toggle("near", textarea.value.length > max * 0.9);
  }

  // ── Rubrics ──────────────────────────────────────────────
  async function loadRubrics() {
    const res = await fetch("/api/rubrics");
    rubrics = await res.json();
    for (const r of rubrics) {
      els.rubricSelect.append(el("option", { value: r.id }, `${r.subject} · ${r.max_marks} marks`));
    }
    renderRubricPreview();
  }

  function currentRubricId() {
    return els.rubricSelect.value || autoRubricId || "fallback_general";
  }

  function renderRubricPreview() {
    const rubric = rubrics.find((r) => r.id === currentRubricId());
    els.rubricCriteria.replaceChildren();
    els.rubricInstructions.textContent = "";
    if (!rubric) return;
    for (const c of rubric.criteria) {
      els.rubricCriteria.append(el("li", {}, c.point, " ", el("span", { class: "w" }, `(${c.weight})`)));
    }
    els.rubricInstructions.textContent = rubric.instructions;
  }

  const matchRubric = debounce(async () => {
    const question = els.question.value.trim();
    if (!question) {
      autoRubricId = null;
      els.matchInfo.textContent = "";
      renderRubricPreview();
      return;
    }
    try {
      const res = await fetch("/api/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const m = await res.json();
      autoRubricId = m.rubric_id;
      if (!els.rubricSelect.value) {
        els.matchInfo.textContent = m.fallback
          ? "No subject keywords found · using General"
          : `Detected: ${m.subject} (${m.matched.join(", ")})`;
      }
      renderRubricPreview();
    } catch { /* non-critical */ }
  }, 300);

  // ── Rendering results ────────────────────────────────────
  function ring(result, label, sub) {
    const pct = result.ok ? result.percentage : 0;
    const r = 32, circ = 2 * Math.PI * r;
    const color = scoreColor(result.ok ? pct : null);
    const value = result.ok
      ? [String(result.marks_awarded), el("small", {}, `/${result.max_marks}`)]
      : ["—"];
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("width", "76"); svg.setAttribute("height", "76"); svg.setAttribute("viewBox", "0 0 76 76");
    const mk = (cls, offset) => {
      const c = document.createElementNS(svgNS, "circle");
      c.setAttribute("class", cls); c.setAttribute("cx", "38"); c.setAttribute("cy", "38"); c.setAttribute("r", String(r));
      c.setAttribute("fill", "none"); c.setAttribute("stroke-width", "7"); c.setAttribute("stroke-linecap", "round");
      c.setAttribute("stroke-dasharray", String(circ)); c.setAttribute("stroke-dashoffset", String(offset));
      return c;
    };
    const bar = mk("bar", circ);
    svg.append(mk("track", 0), bar);
    requestAnimationFrame(() => requestAnimationFrame(() => bar.setAttribute("stroke-dashoffset", String(circ * (1 - pct / 100)))));

    return [
      el("div", { class: "ring", style: `--c:${color}`, role: "img",
        "aria-label": result.ok ? `${result.marks_awarded} out of ${result.max_marks}` : "Evaluation failed" },
        svg, el("div", { class: "val" }, el("span", {}, ...value))),
      el("div", {},
        el("div", { class: "score-label" }, label),
        el("div", { class: "score-sub" }, result.ok ? `${pct}%${sub ? " · " + sub : ""}` : "Failed")),
    ];
  }

  function confidenceText(c) {
    if (c == null) return null;
    return `confidence ${Math.round(c * 100)}%`;
  }

  function renderEvaluation(container, result) {
    container.replaceChildren();
    if (!result.ok) {
      container.append(el("div", { class: "alert alert-error" }, result.error || "Evaluation failed."));
      if (result.justification) container.append(el("p", { class: "hint" }, result.justification));
      return;
    }
    if (result.criteria && result.criteria.length) {
      const list = el("ul", { class: "criteria" });
      for (const c of result.criteria) {
        const pct = c.max_marks ? (100 * c.marks_awarded) / c.max_marks : 0;
        const fill = el("span", { style: `--c:${scoreColor(pct)}` });
        list.append(el("li", {},
          el("div", { class: "criterion-top" }, el("span", {}, c.point), el("strong", {}, `${c.marks_awarded} / ${c.max_marks}`)),
          el("div", { class: "meter", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": String(c.max_marks), "aria-valuenow": String(c.marks_awarded) }, fill),
          c.comment ? el("p", { class: "criterion-comment" }, c.comment) : null));
        requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.width = `${pct}%`; }));
      }
      container.append(list);
    }
    container.append(
      el("div", { class: "block" }, el("div", { class: "block-title" }, "Feedback"), el("p", {}, result.feedback)),
      el("div", { class: "block" }, el("div", { class: "block-title" }, "Justification"), el("p", {}, result.justification)),
    );
  }

  function renderResult(data) {
    lastResult = data;
    const { rubric, selection, guided, blind, comparison } = data;

    $("#res-rubric").textContent = rubric.subject;
    let selText;
    if (selection.manual) {
      selText = "Rubric chosen manually";
    } else if (selection.fallback) {
      selText = "No subject keywords matched — general rubric used";
    } else {
      selText = `Auto-selected · matched: ${selection.matched.join(", ")}`;
    }
    $("#res-selection").textContent = selText;

    $("#score-guided").replaceChildren(...ring(guided, "With rubric", confidenceText(guided.confidence)));
    const blindScore = $("#score-blind");
    blindScore.hidden = !blind;
    if (blind) blindScore.replaceChildren(...ring(blind, "Blind", confidenceText(blind.confidence)));

    const cmp = $("#comparison");
    cmp.replaceChildren();
    if (comparison) {
      if (comparison.available) {
        const d = comparison.difference;
        const cls = d === 0 ? "pill-good" : "pill-warn";
        const agreeCls = { high: "pill-good", moderate: "pill-warn", low: "pill-bad" }[comparison.agreement];
        cmp.append(
          el("span", { class: `pill ${cls} delta` }, `${d > 0 ? "+" : d < 0 ? "−" : "±"}${Math.abs(d)}`),
          el("span", {}, comparison.observation),
          el("span", { class: `pill ${agreeCls}` }, `${comparison.agreement} agreement`),
        );
      } else {
        cmp.append(el("span", { class: "hint" }, comparison.observation));
      }
    }

    renderEvaluation($("#guided-body"), guided);
    $("#blind-card").hidden = !blind;
    if (blind) renderEvaluation($("#blind-body"), blind);

    setView("result");
  }

  function setView(view) {
    els.empty.hidden = view !== "empty";
    els.loading.hidden = view !== "loading";
    els.resultView.hidden = view !== "result";
  }

  // ── Submit ───────────────────────────────────────────────
  function showError(msg) {
    els.formError.textContent = msg;
    els.formError.hidden = !msg;
  }

  function validate() {
    let ok = true;
    for (const t of [els.question, els.answer]) {
      const bad = !t.value.trim();
      t.setAttribute("aria-invalid", bad ? "true" : "false");
      if (bad) ok = false;
    }
    if (!ok) {
      showError("Please fill in both the question and the student's answer.");
      (els.question.value.trim() ? els.answer : els.question).focus();
    }
    return ok;
  }

  async function submit(e) {
    e?.preventDefault();
    if (inFlight) return;
    showError("");
    if (!validate()) return;

    const payload = {
      question: els.question.value,
      answer: els.answer.value,
      rubric_id: els.rubricSelect.value || null,
      include_blind: els.includeBlind.checked,
    };

    const previousView = lastResult ? "result" : "empty";
    setView("loading");
    els.submit.disabled = true;
    els.submit.querySelector(".btn-label").textContent = "Evaluating…";
    inFlight = new AbortController();

    try {
      const res = await fetch("/api/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: inFlight.signal,
      });
      const data = await res.json().catch(() => ({ error: `Server returned ${res.status}` }));
      if (!res.ok) throw new Error(data.error || `Server returned ${res.status}`);
      renderResult(data);
      saveHistory(payload, data);
      if (window.matchMedia("(max-width: 900px)").matches) {
        $("#result-view").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (err) {
      setView(previousView);
      showError(err.message || "Something went wrong. Please try again.");
    } finally {
      inFlight = null;
      els.submit.disabled = false;
      els.submit.querySelector(".btn-label").textContent = "Evaluate";
    }
  }

  // ── Export ───────────────────────────────────────────────
  function reportText(d) {
    const line = (r, name) => r && (r.ok
      ? `${name}: ${r.marks_awarded}/${r.max_marks} (${r.percentage}%)`
      : `${name}: failed — ${r.error}`);
    const parts = [
      `Rubric: ${d.rubric.subject}`,
      line(d.guided, "With rubric"),
      line(d.blind, "Blind"),
      d.comparison?.available ? `Comparison: ${d.comparison.observation}` : null,
      "",
    ];
    if (d.guided.ok) {
      for (const c of d.guided.criteria) parts.push(`- ${c.point}: ${c.marks_awarded}/${c.max_marks}${c.comment ? " — " + c.comment : ""}`);
      parts.push("", `Feedback: ${d.guided.feedback}`, `Justification: ${d.guided.justification}`);
    }
    return parts.filter((p) => p != null).join("\n");
  }

  async function copyReport() {
    if (!lastResult) return;
    const btn = $("#copy-btn");
    try {
      await navigator.clipboard.writeText(reportText(lastResult));
      btn.textContent = "Copied ✓";
    } catch {
      btn.textContent = "Copy failed";
    }
    setTimeout(() => { btn.textContent = "Copy report"; }, 1500);
  }

  function downloadJson() {
    if (!lastResult) return;
    const blob = new Blob([JSON.stringify(lastResult, null, 2)], { type: "application/json" });
    const a = el("a", { href: URL.createObjectURL(blob), download: `evaluation-${Date.now()}.json` });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // ── History ──────────────────────────────────────────────
  function saveHistory(payload, data) {
    const history = readStore(HISTORY_KEY, []);
    history.unshift({ at: Date.now(), payload, data });
    writeStore(HISTORY_KEY, history.slice(0, HISTORY_LIMIT));
    renderHistory();
  }

  function renderHistory() {
    const history = readStore(HISTORY_KEY, []);
    const list = $("#history-list");
    list.replaceChildren();
    $("#history-empty").hidden = history.length > 0;
    $("#history-clear").hidden = history.length === 0;
    history.forEach((h) => {
      const g = h.data.guided;
      const score = g.ok ? `${g.marks_awarded}/${g.max_marks}` : "failed";
      const btn = el("button", { type: "button", title: h.payload.question },
        el("span", { class: "history-q" }, h.payload.question),
        el("span", { class: "history-score", style: `color:${scoreColor(g.ok ? g.percentage : null)}` }, score));
      btn.addEventListener("click", () => {
        els.question.value = h.payload.question;
        els.answer.value = h.payload.answer;
        els.rubricSelect.value = h.payload.rubric_id || "";
        els.includeBlind.checked = h.payload.include_blind !== false;
        updateCounter(els.question); updateCounter(els.answer);
        matchRubric();
        renderResult(h.data);
      });
      list.append(el("li", {}, btn));
    });
  }

  // ── API status ───────────────────────────────────────────
  async function checkHealth() {
    try {
      const res = await fetch("/api/health");
      const h = await res.json();
      els.apiStatus.className = `pill ${h.api_key_configured ? "pill-good" : "pill-bad"}`;
      els.apiStatus.textContent = h.api_key_configured ? "● API ready" : "● API key missing";
      els.apiStatus.title = h.api_key_configured
        ? "An API key is configured on the server."
        : "Set GOOGLE_API_KEY on the server and restart it.";
    } catch {
      els.apiStatus.className = "pill pill-bad";
      els.apiStatus.textContent = "● Server offline";
    }
  }

  // ── Wire up ──────────────────────────────────────────────
  function init() {
    initTheme();

    SAMPLES.forEach((s, i) => els.sample.append(el("option", { value: String(i) }, s.label)));
    els.sample.addEventListener("change", () => {
      const s = SAMPLES[Number(els.sample.value)];
      if (!s) return;
      els.question.value = s.question;
      els.answer.value = s.answer;
      els.sample.value = "";
      updateCounter(els.question); updateCounter(els.answer);
      showError("");
      matchRubric();
    });

    for (const t of [els.question, els.answer]) {
      t.addEventListener("input", () => {
        updateCounter(t);
        if (t.value.trim()) t.setAttribute("aria-invalid", "false");
      });
      updateCounter(t);
    }
    els.question.addEventListener("input", matchRubric);
    els.rubricSelect.addEventListener("change", () => {
      els.matchInfo.textContent = els.rubricSelect.value ? "Manual override" : "";
      if (!els.rubricSelect.value) matchRubric();
      renderRubricPreview();
    });

    els.form.addEventListener("submit", submit);
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submit(e);
    });

    els.clear.addEventListener("click", () => {
      els.question.value = ""; els.answer.value = ""; els.rubricSelect.value = "";
      updateCounter(els.question); updateCounter(els.answer);
      showError(""); matchRubric(); els.question.focus();
    });

    $("#copy-btn").addEventListener("click", copyReport);
    $("#download-btn").addEventListener("click", downloadJson);
    $("#history-clear").addEventListener("click", () => { writeStore(HISTORY_KEY, []); renderHistory(); });

    loadRubrics().catch(() => showError("Could not load rubrics from the server."));
    checkHealth();
    renderHistory();
  }

  init();
})();
