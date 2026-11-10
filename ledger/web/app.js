const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
let sharedLedger = false;
let run = null,
  range = 40,
  tab = "debate",
  token = sessionStorage.getItem("ledger-token") || "";
const fmt = (n, d = 2) =>
  Number(n).toLocaleString("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
const status = (text, error = false) => {
  $("status").textContent = text;
  $("status").classList.toggle("error", error);
};
async function apiResponse(path, options = {}) {
  const r = await fetch("/api" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...options.headers,
    },
  });
  if (r.status === 401) openAuth();
  return r;
}
async function api(path, options) {
  const r = await apiResponse(path, options);
  const data = await r.json();
  if (!r.ok)
    throw Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
const localDate = new Date().toLocaleDateString("en-CA");
$("asof").value = localDate;
$("asof").max = localDate;
const config = {
  mcpServers: {
    "thesis-ledger": {
      command: "/absolute/path/to/uv",
      args: [
        "--directory",
        "/absolute/path/to/thesis-ledger",
        "run",
        "thesis-ledger-mcp",
      ],
    },
  },
};
function showMcpConfig(target, button, value, label) {
  const json = JSON.stringify(value, null, 2);
  $(target).textContent = json;
  $(button).onclick = async () => {
    try {
      await navigator.clipboard.writeText(json);
      $(button).textContent = "Copied";
      setTimeout(() => { $(button).textContent = label; }, 1500);
    } catch {
      $(button).textContent = "Select and copy the configuration above";
    }
  };
}
showMcpConfig("mcp-config", "copy-config", config, "Copy local configuration");
$("mcp-url").textContent = location.origin + "/mcp/";
function openAuth() {
  const dialog = $("auth-dialog");
  if (dialog.open) return;
  $("access-token-input").value = "";
  dialog.showModal();
}
$("close-auth").onclick = () => $("auth-dialog").close();
$("auth-form").onsubmit = (event) => {
  event.preventDefault();
  const value = $("access-token-input").value.trim();
  if (!value) return;
  sessionStorage.setItem("ledger-token", value);
  location.reload();
};
async function page(name) {
  if (!$(name).classList.contains("active")) window.scrollTo(0, 0);
  document
    .querySelectorAll(".page")
    .forEach((el) => el.classList.toggle("active", el.id === name));
  document
    .querySelectorAll("[data-page]")
    .forEach((el) => el.classList.toggle("active", el.dataset.page === name));
  $("breadcrumb").textContent = {
    chat: "Research chat",
    forecast: "Forecast",
    research: "Research desk",
    deep: "Deep Research",
    memory: "Thesis ledger",
    runs: "Research history",
    connect: "Connect via MCP",
    method: "How it works",
  }[name];
  try {
    clearTimeout(quoteTimer);
    clearTimeout(marketTimer);
    if (name === "chat") await openChat();
    if (name === "research") {
      refreshMarket();
      refreshQuote("desk-quote", "ticker", "research");
      refreshIntraday(selectedTicker);
      if (!$("company-news").childElementCount) loadCompanyNews(selectedTicker, selectionVersion);
    }
    if (name !== "research") clearTimeout(intradayTimer);
    if (name === "forecast" && !$("forecast-chart").childElementCount
        && !$("forecast-submit").disabled) $("forecast-form").requestSubmit();
    if (name === "memory") await loadMemory();
    if (name === "runs") await loadRuns();
  } catch (e) {
    const target = { chat: "chat-status", memory: "memory-list", runs: "run-list" }[name];
    if (!target) return;
    $(target).textContent = e.message;
  }
}
document
  .querySelectorAll("[data-page]")
  .forEach((b) => (b.onclick = () => page(b.dataset.page)));
$("desk-deep").onclick = () => page("deep");
$("research-form").onsubmit = async (e) => {
  e.preventDefault();
  const selection = ++selectionVersion;
  $("run-button").disabled = true;
  $("run-button").classList.add("loading");
  $("run-button").textContent = "Researching…";
  status(
    "Gathering evidence → independent analysts → bull / bear debate → risk review. Completed stages are saved.",
  );
  try {
    const request = {
      ticker: $("ticker").value.toUpperCase(),
      as_of: $("asof").value,
      horizon: +$("horizon").value,
      mode: "live",
      forecast: "bootstrap",
      use_memory: $("use-memory").checked,
    };
    if ($("question").value.trim())
      request.question = $("question").value.trim();
    const result = await api("/research", {
      method: "POST",
      body: JSON.stringify(request),
    });
    if (selection !== selectionVersion) return;
    $("research-heading").textContent = "Research · " + request.ticker;
    if (result.status === "failed") {
      status(result.error + " Open Research history to resume.", true);
    } else {
      run = result;
      if (run.request.ticker === selectedTicker) renderXHighlights(run);
      render();
      status(run.snapshot.warnings.join(" "));
    }
  } catch (err) {
    status(err.message, true);
  } finally {
    $("run-button").disabled = false;
    $("run-button").classList.remove("loading");
    $("run-button").textContent = "Run research ↗";
  }
};
function sourceTitle(evidence, className = "") {
  const title = esc(evidence.title);
  try {
    const url = new URL(evidence.url);
    if (["https:", "http:"].includes(url.protocol))
      return `<a class="${className}" href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">${title} ↗</a>`;
  } catch {}
  return `<span class="${className}">${title}</span>`;
}

function cites(ids, evidence) {
  const sources = [...new Set(ids)]
    .map((id) => evidence.find((item) => item.id === id))
    .filter(Boolean);
  return sources.length
    ? '<div class="citations">' + sources.map((item) => sourceTitle(item, "citation")).join("") + '</div>'
    : "";
}
function render() {
  $("empty").hidden = true;
  $("results").hidden = false;
  $("export").disabled = false;
  $("export-status").textContent = "";
  $("asset-name").textContent = run.request.ticker;
  $("data-badge").textContent = run.snapshot.provider;
  $("run-date").textContent =
    "As of " +
    run.request.as_of +
    " · " +
    run.request.horizon +
    " session horizon";
  const m = run.metrics;
  const stats = [
    [
      "LAST OBSERVED CLOSE",
      "$" + fmt(m.last),
      fmt(m.change) + "% vs prior close",
    ],
    [
      "20-SESSION MOMENTUM",
      (m.momentum >= 0 ? "+" : "") + fmt(m.momentum) + "%",
      m.regime + " · observed series",
    ],
    [
      "ANNUALIZED VOLATILITY",
      fmt(m.volatility, 1) + "%",
      "Historical log returns · 252 sessions",
    ],
    [
      "SCENARIO MEDIAN",
      (run.forecast.expected_return >= 0 ? "+" : "") +
        fmt(run.forecast.expected_return) +
        "%",
      "Uncalibrated · " + run.request.horizon + " sessions",
    ],
  ];
  $("stats").innerHTML = stats
    .map(
      ([a, b, c]) =>
        `<div class="stat"><small>${esc(a)}</small><strong>${esc(b)}</strong><span>${esc(c)}</span></div>`,
    )
    .join("");
  $("forecast-label").textContent = run.forecast.label;
  $("forecast-note").textContent = run.forecast.disclaimer;
  $("decision").innerHTML =
    `<span class="verdict">${run.decision.stance === "abstain" ? "ABSTAIN / KEEP RESEARCHING" : esc(run.decision.stance.toUpperCase())}</span><p>${esc(run.decision.summary)}</p>${run.disagreement ? '<div class="info">Forecast and research direction disagree.</div>' : ""}<div class="invalidation"><strong>WHAT WOULD CHANGE THE THESIS</strong>${esc(run.decision.invalidation)}</div><div class="invalidation"><strong>RISK REVIEW</strong>${esc(run.reports.risk.summary)}</div>`;
  const names = {
    technical: "Technical analyst",
    fundamentals: "Fundamentals analyst",
    news: "News & catalysts",
    sentiment: "Sentiment analyst",
  };
  $("analysts").innerHTML = Object.entries(names)
    .map(([key, name], i) => {
      const r = run.reports[key];
      const reason = r.stance_reason?.trim()
        ? `<p class="stance-reason"><strong>Why ${esc(r.stance)}</strong>${esc(r.stance_reason)}</p>`
        : '<p class="stance-reason">This report predates saved stance explanations.</p>';
      return `<article class="analyst"><div class="analyst-top"><span class="agent-icon">0${i + 1}</span><span class="stance ${esc(r.stance)}">${esc(r.stance)}</span></div><h3>${name}</h3>${reason}<p>${esc(r.summary)}</p>${cites(r.evidence_ids, run.snapshot.evidence)}</article>`;
    })
    .join("");
  $("call-count").textContent =
    run.calls +
    " MODEL ATTEMPTS · " +
    run.memories.length +
    " MEMORIES";
  chart();
  details();
}
function chart(result = run, target = "chart", window = range) {
  const bars = result.snapshot.bars.slice(-window),
    f = result.forecast.points,
    all = [...bars.map((b) => b.close), ...f.flatMap((p) => [p.low, p.high])];
  let lo = Math.min(...all) * 0.98,
    hi = Math.max(...all) * 1.02;
  const W = 800,
    H = 270,
    left = 12,
    right = 65,
    top = 15,
    bottom = 32,
    n = bars.length + f.length;
  const x = (i) => left + (i / (n - 1)) * (W - left - right),
    y = (v) => top + ((hi - v) / (hi - lo)) * (H - top - bottom),
    path = (pts) =>
      pts
        .map((p, i) => (i ? "L" : "M") + p.map((v) => v.toFixed(2)).join(","))
        .join(" ");
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Observed closing prices and forecast scenario range"><defs><linearGradient id="${target}-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#83e0bd" stop-opacity=".12"/><stop offset="1" stop-color="#83e0bd" stop-opacity="0"/></linearGradient></defs>`;
  for (let i = 0; i < 5; i++) {
    const v = lo + ((hi - lo) * i) / 4;
    svg += `<line x1="${left}" y1="${y(v)}" x2="${W - right}" y2="${y(v)}" stroke="#263037" stroke-dasharray="3 5"/><text x="${W - right + 12}" y="${y(v) + 4}" fill="#7e8e98" font-size="10" font-family="monospace">${fmt(v)}</text>`;
  }
  const history = bars.map((b, i) => [x(i), y(b.close)]),
    last = history.at(-1),
    med = [last, ...f.map((p, i) => [x(bars.length + i), y(p.median)])];
  const band = [
    last,
    ...f.map((p, i) => [x(bars.length + i), y(p.high)]),
    ...f.map((p, i) => [x(bars.length + i), y(p.low)]).reverse(),
  ];
  svg += `<path d="${path(history)} L${last[0]},${H - bottom} L${left},${H - bottom} Z" fill="url(#${target}-fill)"/><path d="${path(band)} Z" fill="#b7a0f4" opacity=".13"/><line x1="${last[0]}" x2="${last[0]}" y1="${top}" y2="${H - bottom}" stroke="#73877e" stroke-dasharray="3 4"/><path d="${path(history)}" fill="none" stroke="#83e0bd" stroke-width="2"/><path d="${path(med)}" fill="none" stroke="#b7a0f4" stroke-width="2" stroke-dasharray="5 4"/>`;
  [0, Math.floor(bars.length / 2), bars.length - 1, n - 1].forEach((i) => {
    const d = i < bars.length ? bars[i].date : f.at(-1).date;
    svg += `<text x="${x(i)}" y="${H - 7}" text-anchor="${i === 0 ? "start" : i === n - 1 ? "end" : "middle"}" fill="#7e8e98" font-size="10" font-family="monospace">${esc(d.slice(5))}</text>`;
  });
  bars.forEach((b, i) => {
    svg += `<circle cx="${x(i)}" cy="${y(b.close)}" r="6" fill="transparent"><title>${esc(b.date)} · Close $${fmt(b.close)} · Volume ${fmt(b.volume, 0)}</title></circle>`;
  });
  f.forEach((p, i) => {
    svg += `<circle cx="${x(bars.length + i)}" cy="${y(p.median)}" r="6" fill="transparent"><title>${esc(p.date)} · Median $${fmt(p.median)} · Range $${fmt(p.low)}–$${fmt(p.high)}</title></circle>`;
  });
  $(target).innerHTML = svg + "</svg>";
}
document.querySelectorAll("[data-range]").forEach(
  (b) =>
    (b.onclick = () => {
      range = +b.dataset.range;
      document
        .querySelectorAll("[data-range]")
        .forEach((v) => v.classList.toggle("active", v === b));
      if (run) chart();
    }),
);
document.querySelectorAll("[data-tab]").forEach(
  (b) =>
    (b.onclick = () => {
      tab = b.dataset.tab;
      document.querySelectorAll("[data-tab]").forEach((v) => {
        v.classList.toggle("active", v === b);
        v.setAttribute("aria-selected", String(v === b));
      });
      details();
    }),
);
function details() {
  if (!run) return;
  let html = "";
  if (tab === "debate") {
    html =
      '<div class="debate-grid">' +
      Object.entries(run.reports)
        .filter(([k]) => k.startsWith("bull-") || k.startsWith("bear-"))
        .map(
          ([k, r]) =>
            `<article class="debate-card ${k.startsWith("bear") ? "bear" : ""}"><span class="tiny">${esc(k.toUpperCase())}</span><p>${esc(r.summary)}</p>${cites(r.evidence_ids, run.snapshot.evidence)}<p><strong>Invalidation:</strong> ${esc(r.invalidation)}</p></article>`,
        )
        .join("") +
      "</div>";
  } else if (tab === "evidence") {
    html = run.snapshot.evidence
      .map((e) =>
        `<div class="evidence-item"><span class="tiny">${esc(e.source || e.kind)} · ${esc(e.published)}</span><h3>${sourceTitle(e)}</h3><p>${esc(e.text)}</p></div>`,
      )
      .join("");
  } else if (tab === "trace") {
    html = run.trace
      .map(
        (t) =>
          `<div class="trace-row"><time>${esc(t.at.slice(11, 19))}</time><strong>${esc(t.stage)}</strong><span>${esc(t.detail)}</span></div>`,
      )
      .join("");
  } else {
    const e = run.evaluation;
    html = `<h2>Rolling-origin forecast diagnostic</h2><p>${esc(e.note)} The diagnostic evaluates historical-return scenarios.</p><div class="stats">${[
      ["TEST WINDOWS", e.windows],
      ["BOOTSTRAP MAPE", fmt(e.bootstrap_mape) + "%"],
      ["NO-CHANGE MAPE", fmt(e.naive_mape) + "%"],
      ["SCENARIO COVERAGE", fmt(e.scenario_coverage, 1) + "%"],
    ]
      .map(
        ([a, b]) =>
          `<div class="stat"><small>${a}</small><strong>${b}</strong></div>`,
      )
      .join(
        "",
      )}</div><p>Each window sees only preceding bars. Overlapping outcomes and a small sample limit interpretation.</p>`;
  }
  $("detail").innerHTML = html;
}
async function loadRuns() {
  const runs = (await api("/runs")).filter((run) => run.request.mode === "live");
  $("run-list").innerHTML = runs.length
    ? runs
        .map(
          (r) =>
            `<div class="history-row panel"><strong>${esc(r.request.ticker)}</strong><span class="chip">${esc(r.status)}</span><small>${esc(r.request.as_of)} · ${esc(r.request.mode)} · ${r.request.horizon} sessions</small><button class="secondary" data-open-run="${esc(r.id)}">${r.status === "complete" ? "Open report ↗" : "Resume run ↗"}</button></div>`,
        )
        .join("")
    : '<div class="empty">No runs yet. Start in Deep Research.</div>';
  bindRunButtons($("run-list"));
}

function bindRunButtons(container) {
  container.querySelectorAll("[data-open-run]").forEach(
    (b) =>
      (b.onclick = async () => {
        b.disabled = true;
        try {
          let r = await api("/runs/" + b.dataset.openRun);
          if (r.status !== "complete")
            r = await api("/runs/" + b.dataset.openRun + "/resume", {
              method: "POST",
            });
          if (r.status !== "complete") throw Error(r.error);
          await page("deep");
          ++selectionVersion;
          $("ticker").value = r.request.ticker;
          $("research-heading").textContent = "Research · " + r.request.ticker;
          run = r;
          render();
          status("Viewing saved research from " + r.request.as_of + ".");
        } catch (e) {
          b.textContent = e.message;
        } finally {
          b.disabled = false;
        }
      }),
  );
}
async function loadMemory() {
  const memories = (await api("/memories")).filter((memory) => memory.mode === "live");
  $("memory-list").innerHTML = memories.length
    ? memories
        .map(
          (m) =>
            `<article class="panel memory-card"><div class="top"><strong>${esc(m.ticker)}</strong><span class="chip">${esc(m.mode)}</span><span class="tiny">${esc(m.as_of)}</span>${sharedLedger ? "" : `<button class="secondary" data-review="${esc(m.id)}">Review memory ↗</button>`}</div><p>${esc(m.body.thesis)}</p><p><strong>Scope:</strong> ${esc(m.body.scope)}</p><p><strong>Invalidation:</strong> ${esc(m.body.invalidation)}</p><button class="secondary" data-open-run="${esc(m.run_id)}">Open source report ↗</button>${m.revisions.map((r) => `<p class="revision">${esc(r.created.slice(0, 10))} · ${esc(r.scope)}<br>${esc(r.feedback)}</p>`).join("")}</article>`,
        )
        .join("")
    : `<div class="empty">
        <p>Complete a research run to save its thesis, evidence, and invalidation criteria here.</p>
        <button id="memory-start-research" class="secondary" type="button">Open Deep Research ↗</button>
      </div>`;
  if (!memories.length) {
    $("memory-start-research").onclick = async () => {
      await page("deep");
      $("ticker").focus();
    };
  }
  bindRunButtons($("memory-list"));
  document.querySelectorAll("[data-review]").forEach(
    (b) =>
      (b.onclick = () => {
        $("review-id").value = b.dataset.review;
        $("feedback").value = "";
        $("review-dialog").showModal();
      }),
  );
}
$("close-review").onclick = () => $("review-dialog").close();
$("review-form").onsubmit = async (e) => {
  e.preventDefault();
  try {
    await api("/memories/review", {
      method: "POST",
      body: JSON.stringify({
        memory_id: $("review-id").value,
        feedback: $("feedback").value,
        scope: $("scope").value,
      }),
    });
    $("review-dialog").close();
    await loadMemory();
  } catch (e) {
    alert(e.message);
  }
};
$("export").onclick = async () => {
  const report = run;
  if (report?.status !== "complete") return;
  const button = $("export");
  const message = $("export-status");
  button.disabled = true;
  message.textContent = "Preparing download…";
  try {
    const response = await apiResponse("/runs/" + encodeURIComponent(report.id) + "/export?format=md");
    if (!response.ok) {
      const error = await response.json();
      throw Error(error.detail || "The report could not be exported.");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `thesis-ledger-${report.request.ticker}-${report.request.as_of}.md`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    if (run === report) message.textContent = "Download started.";
  } catch (error) {
    if (run === report) message.textContent = error.message;
  } finally {
    if (run === report) button.disabled = false;
  }
};
api("/config")
  .then(async (c) => {
    liveReady = c.live_ready;
    if (c.public_mcp_path) {
      const url = new URL(c.public_mcp_path, location.origin).href;
      $("public-mcp-url").textContent = url;
      showMcpConfig("public-mcp-config", "copy-public-config", {
        mcpServers: { "thesis-ledger-market": { url } },
      }, "Copy Cursor configuration");
      $("public-mcp").hidden = false;
    }
    $("account-controls").hidden = !c.google_sign_in;
    $("google-signin").hidden = c.signed_in;
    $("signout-form").hidden = !c.signed_in;
    sharedLedger = c.shared_ledger;
    $("research-public-note").hidden = !sharedLedger;
    $("ledger-access-note").textContent = sharedLedger
      ? "This ledger is public. Completed research and its source reports are visible to every visitor."
      : c.signed_in
      ? "Your reports and revisions are saved to your account."
      : c.public_visitor ? "Guest reports are temporary. Sign in to keep future research in your private ledger." : "";
    if (new URLSearchParams(location.search).get("signin") === "failed") {
      $("signin-status").textContent = "Google sign-in did not finish. Please try again.";
      $("signin-status").hidden = false;
    }
    if (location.hash === "#memory") {
      history.replaceState(null, "", location.pathname);
      await page("memory");
    } else {
      refreshMarket();
    }
    await selectTicker(selectedTicker);
  })
  .catch((e) => {
    status(e.message, true);
  });

const savedChatSession = localStorage.getItem("ledger-chat-session") || "";
let chatSession = /^[a-f0-9]{32}$/.test(savedChatSession) ? savedChatSession : newChatId();
let quoteTimer;
let quoteRequest = 0;
let chatBusy = false;

function newChatId() {
  const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (n) =>
    n.toString(16).padStart(2, "0"),
  ).join("");
  localStorage.setItem("ledger-chat-session", id);
  return id;
}

const chatMarkdown = window.markdownit?.({ html: false });
if (chatMarkdown) {
  chatMarkdown.validateLink = (url) => /^https?:\/\//i.test(url);
  chatMarkdown.renderer.rules.image = (tokens, index) => esc(tokens[index].content);
}

function renderChatAnswer(node, text) {
  if (chatMarkdown) node.innerHTML = chatMarkdown.render(text);
  else node.textContent = text;
}

function chatBubble(role, text) {
  const node = document.createElement("div");
  node.className = "chat-message " + role;
  if (role === "assistant") renderChatAnswer(node, text);
  else node.textContent = text;
  const messages = $("chat-messages");
  messages.append(node);
  messages.scrollTop = messages.scrollHeight;
  return node;
}

async function openChat() {
  if (!chatBusy) {
    const history = await api("/chat/" + chatSession);
    if (!chatBusy) {
      $("chat-messages").replaceChildren();
      for (const item of history) chatBubble(item.role, item.content);
    }
  }
  if (!$("chat").dataset.opened) {
    $("chat-ticker").value = $("ticker").value;
    $("chat").dataset.opened = "1";
  }
  refreshQuote();
}

async function refreshQuote(card = "quote-card", input = "chat-ticker", activePage = "chat") {
  clearTimeout(quoteTimer);
  const request = ++quoteRequest;
  const ticker = $(input).value.trim().toUpperCase();
  if (!/^[A-Z][A-Z0-9.\-]{0,9}$/.test(ticker)) {
    $(card).textContent = "Enter a valid ticker.";
    return;
  }
  $(card).textContent = "Checking " + ticker + "…";
  try {
    const q = await api("/quote/" + encodeURIComponent(ticker));
    if (request !== quoteRequest) return;
    $(card).textContent =
      q.ticker + "  $" + fmt(q.price) + "  ·  " + q.source + "  ·  " +
      q.freshness + "  ·  " + q.as_of;
    if (q.refresh_seconds && $(activePage).classList.contains("active"))
      quoteTimer = setTimeout(() => refreshQuote(card, input, activePage), q.refresh_seconds * 1000);
  } catch (err) {
    if (request === quoteRequest) $(card).textContent = err.message;
  }
}

$("refresh-quote").onclick = () => refreshQuote();
$("chat-ticker").onchange = () => refreshQuote();
$("ticker").onchange = () => selectTicker($("ticker").value);
$("new-chat").onclick = () => {
  chatSession = newChatId();
  $("chat-messages").replaceChildren();
  $("chat-status").textContent = "";
};
$("chat-form").onsubmit = async (e) => {
  e.preventDefault();
  if (chatBusy) return;
  const message = $("chat-input").value.trim();
  const ticker = $("chat-ticker").value.trim().toUpperCase();
  if (!message) return;
  if (!/^[A-Z][A-Z0-9.-]{0,9}$/.test(ticker)) {
    $("chat-status").textContent = "Enter a stock ticker, such as NVDA.";
    return;
  }
  chatBusy = true;
  $("chat-send").disabled = true;
  $("new-chat").disabled = true;
  $("chat-input").value = "";
  chatBubble("user", message);
  const answer = chatBubble("assistant", "");
  $("chat-status").textContent = "Thinking…";
  let answerText = "";
  let renderFrame = null;
  const updateAnswer = () => {
    renderFrame = null;
    renderChatAnswer(answer, answerText);
    const messages = $("chat-messages");
    messages.scrollTop = messages.scrollHeight;
  };
  let done = false;
  try {
    const response = await apiResponse("/chat", {
      method: "POST",
      body: JSON.stringify({ session: chatSession, ticker, message }),
    });
    if (!response.ok) {
      const data = await response.json();
      if (typeof data.detail === "string") throw Error(data.detail);
      const field = Array.isArray(data.detail) ? data.detail[0]?.loc?.at(-1) : null;
      const validationMessages = {
        session: "This chat session is invalid. Select New chat and resend your message.",
        ticker: "Enter a stock ticker, such as NVDA.",
        message: "Enter a message of up to 4,000 characters.",
      };
      throw Error(validationMessages[field] || "Chat could not start. Try again.");
    }
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    try {
      while (true) {
        const { value, done: ended } = await reader.read();
        if (ended) break;
        buffer += value;
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          const item = JSON.parse(line);
          if (item.type === "delta") {
            answerText += item.text;
            if (renderFrame === null) renderFrame = requestAnimationFrame(updateAnswer);
          }
          if (item.type === "status") $("chat-status").textContent = item.message;
          if (item.type === "report") $("chat-status").textContent = "Report saved · " + item.id;
          if (item.type === "error") throw Error(item.message);
          if (item.type === "done") done = true;
        }
      }
    } finally {
      await reader.cancel();
    }
    if (!done) throw Error("The response was interrupted.");
    $("chat-status").textContent = "";
  } catch (err) {
    $("chat-status").textContent = err.message;
    if (!answerText) answer.remove();
    $("chat-input").value ||= message;
  } finally {
    if (renderFrame !== null) {
      cancelAnimationFrame(renderFrame);
      updateAnswer();
    }
    chatBusy = false;
    $("chat-send").disabled = false;
    $("new-chat").disabled = false;
  }
};

$("forecast-form").onsubmit = async (e) => {
  e.preventDefault();
  $("forecast-submit").disabled = true;
  $("forecast-chart").replaceChildren();
  $("forecast-caption").textContent = "";
  $("forecast-status").textContent = "Fetching daily bars and sampling price paths…";
  try {
    const result = await api("/forecast", {
      method: "POST",
      body: JSON.stringify({
        ticker: $("forecast-ticker").value.trim().toUpperCase(),
        horizon: Number($("forecast-horizon").value),
        mode: "live",
        forecast: "bootstrap",
      }),
    });
    chart(result, "forecast-chart", 40);
    $("forecast-status").textContent =
      result.request.ticker + " · " + result.forecast.label + " · " +
      result.snapshot.provider +
      " · Last bar " + result.snapshot.bars.at(-1).date;
    $("forecast-caption").textContent = [result.forecast.disclaimer, ...result.snapshot.warnings.filter(
      (warning) => warning.startsWith("STALE") || warning.startsWith("Daily bars"),
    )].join(" ");
  } catch (err) {
    $("forecast-status").textContent = err.message;
  } finally {
    $("forecast-submit").disabled = false;
  }
};

function watchRow(q) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = "watch-row";
  row.dataset.symbol = q.ticker;
  row.setAttribute("aria-pressed", String(q.ticker === selectedTicker));
  row.title = [q.source, q.as_of].filter(Boolean).join(" · ");
  const symbol = document.createElement("strong");
  symbol.textContent = q.ticker;
  const price = document.createElement("span");
  price.textContent = q.price == null ? "—" : "$" + fmt(q.price);
  const change = document.createElement("span");
  change.className = q.change_percent > 0 ? "market-up" : q.change_percent < 0 ? "market-down" : "";
  change.textContent = q.change_percent == null ? "—" :
    (q.change_percent > 0 ? "+" : "") + fmt(q.change_percent) + "%";
  row.append(symbol, price, change);
  row.onclick = () => selectTicker(q.ticker);
  return row;
}

let marketTimer;
async function refreshMarket() {
  clearTimeout(marketTimer);
  try {
    const brief = await api("/market");
    $("market-quotes").replaceChildren();
    for (const quote of brief.quotes) $("market-quotes").append(watchRow(quote));
    const activity = $("market-activity");
    activity.replaceChildren();
    for (const stock of brief.activity || []) {
      const item = document.createElement("div");
      item.className = "activity-card";
      const row = watchRow(stock);
      row.onclick = () => {
        selectTicker(stock.ticker);
        $("market-chart").scrollIntoView({ block: "start" });
      };
      item.append(row);
      if (stock.headline?.url.startsWith("https://")) {
        const link = document.createElement("a");
        link.className = "activity-headline";
        link.href = stock.headline.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = stock.headline.title;
        link.title = stock.headline.source + " · " + new Date(stock.headline.published).toLocaleString();
        item.append(link);
      }
      activity.append(item);
    }
    $("activity-section").hidden = !activity.childElementCount;
    const measured = brief.quotes.filter(q => q.change_percent != null);
    const rising = measured.filter(q => q.change_percent > 0).length;
    const falling = measured.filter(q => q.change_percent < 0).length;
    $("market-summary").textContent = measured.length
      ? `${rising} up · ${falling} down · ${measured.length - rising - falling} flat on this watchlist`
      : brief.quotes.length ? "Latest available prices" : "Watchlist prices unavailable.";
    renderHeadlines("market-news", brief.headlines, "No market headlines available.");
    $("market-warning").textContent = brief.warnings.join(" ");
    if ($("research").classList.contains("active")) {
      clearTimeout(marketTimer);
      marketTimer = setTimeout(refreshMarket, brief.refresh_seconds * 1000);
    }
  } catch (err) {
    $("market-warning").textContent = err.message;
  }
}

let selectedTicker = "NVDA";
let selectionVersion = 0;
let intradayTimer;
let chartTicker = "";
let liveReady = false;

$("symbol-form").onsubmit = (event) => {
  event.preventDefault();
  selectTicker($("symbol-search").value);
};

async function selectTicker(value) {
  const ticker = value.trim().toUpperCase();
  if (!/^[A-Z][A-Z0-9.\-]{0,9}$/.test(ticker)) {
    $("intraday-status").textContent = "Enter a valid U.S. ticker.";
    return;
  }
  const version = ++selectionVersion;
  selectedTicker = ticker;
  for (const id of ["ticker", "symbol-search", "forecast-ticker", "chat-ticker"]) $(id).value = ticker;
  $("desk-symbol").textContent = ticker;
  $("company-news-heading").textContent = ticker;
  $("company-news").setAttribute("aria-label", ticker + " headlines");
  $("research-heading").textContent = "Research · " + ticker;
  companyArticles = [];
  companyPosts = [];
  companyNewsEmpty = "Loading company headlines…";
  renderCompanyHeadlines();
  $("forecast-chart").replaceChildren();
  document.querySelectorAll(".watch-row").forEach((row) =>
    row.setAttribute("aria-pressed", String(row.dataset.symbol === ticker)),
  );
  run = null;
  $("results").hidden = true;
  $("empty").hidden = false;
  $("export").disabled = true;
  refreshQuote("desk-quote", "ticker", "research");
  refreshIntraday(ticker);
  loadCompanyNews(ticker, version);
  status("Looking for saved " + ticker + " research…");
  try {
    const path = "/dashboard?ticker=" + encodeURIComponent(ticker);
    const saved = await api(path);
    if (version !== selectionVersion || $("run-button").disabled) return;
    if (saved) {
      run = saved;
      renderXHighlights(saved);
      render();
      status("Saved live report · " + saved.request.as_of + " · " + saved.snapshot.warnings.join(" "));
    } else {
      status(liveReady ? "Select Run research to generate a report for " + ticker + "." : "Connect the research providers to run analysis.");
    }
  } catch (err) {
    if (version === selectionVersion) status(err.message, true);
  }
}

let companyArticles = [];
let companyPosts = [];
let companyNewsEmpty = "Loading company headlines…";

function showHeadlineCoverage(company) {
  $("company-news-heading").setAttribute("aria-pressed", company);
  $("market-news-button").setAttribute("aria-pressed", !company);
  $("company-news").hidden = !company;
  $("market-news").hidden = company;
}
$("company-news-heading").onclick = () => showHeadlineCoverage(true);
$("market-news-button").onclick = () => showHeadlineCoverage(false);

function renderHeadlines(target, headlines, emptyMessage) {
  const rows = headlines.map((headline) => {
    const post = headline.kind === "sentiment";
    const timestamp = new Date(headline.published);
    const published = headline.published && Number.isFinite(timestamp.getTime())
      ? timestamp.toLocaleDateString(undefined, {
          month: "short", day: "numeric", year: "numeric", ...(post ? { timeZone: "UTC" } : {}),
        })
      : "";
    const source = post ? headline.title.replace(/^X post by /, "") : headline.source;
    const title = post ? headline.text.replace(/^Grok summary of the cited post: /, "") : headline.title;
    return `<li class="headline-row"><div class="headline-meta"><span class="headline-type${post ? " headline-type-x" : ""}">${post ? "X post" : "Article"}</span><span>${esc(source)}</span>${published ? `<time datetime="${esc(headline.published)}">${esc(published)}</time>` : ""}</div>${sourceTitle({ title, url: headline.url }, "headline-link")}</li>`;
  });
  $(target).innerHTML = rows.join("") || `<li class="headline-empty">${esc(emptyMessage)}</li>`;
}

function renderCompanyHeadlines() {
  const publishedAt = (entry) => Date.parse(entry.published) || 0;
  const headlines = [...companyArticles, ...companyPosts]
    .sort((a, b) => publishedAt(b) - publishedAt(a));
  renderHeadlines("company-news", headlines, companyNewsEmpty);
}

function renderXHighlights(report) {
  companyPosts = (report?.snapshot?.evidence || [])
    .filter((item) => item.kind === "sentiment" && item.id.startsWith("x-post-"))
    .slice(0, 2);
  renderCompanyHeadlines();
}

async function loadCompanyNews(ticker, version) {
  try {
    const articles = await api("/news/" + encodeURIComponent(ticker));
    if (version !== selectionVersion) return;
    companyArticles = articles.slice(0, 5);
    companyNewsEmpty = "No company headlines available.";
  } catch (err) {
    if (version !== selectionVersion) return;
    companyNewsEmpty = err.message;
  }
  renderCompanyHeadlines();
}

async function refreshIntraday(ticker) {
  clearTimeout(intradayTimer);
  const version = selectionVersion;
  if (chartTicker !== ticker) {
    chartTicker = ticker;
    $("intraday-chart").replaceChildren();
    $("intraday-status").textContent = "Loading " + ticker + " session…";
  }
  try {
    const result = await api("/intraday/" + encodeURIComponent(ticker));
    if (version !== selectionVersion) return;
    drawCandles(result);
    $("intraday-status").textContent = result.session + " · Regular session ET · Alpaca " + result.feed;
  } catch (err) {
    if (version !== selectionVersion) return;
    $("intraday-status").textContent = err.message;
  }
  if (version === selectionVersion && $("research").classList.contains("active"))
    intradayTimer = setTimeout(() => refreshIntraday(ticker), 60_000);
}

function drawCandles({ bars, ticker, open, close }) {
  const w = 720, h = 285, left = 10, right = 66, top = 12, bottom = 30;
  const minimum = Math.min(...bars.map(bar => bar.l));
  const maximum = Math.max(...bars.map(bar => bar.h));
  const pad = Math.max((maximum - minimum) * 0.07, 0.01);
  const lo = minimum - pad, hi = maximum + pad;
  const start = Date.parse(open);
  const elapsed = Math.min(Date.parse(close), Date.parse(bars.at(-1).t) + 300_000) - start;
  const span = Math.max(300_000, elapsed);
  const x = time => left + (time - start) / span * (w - left - right);
  const y = price => top + (hi - price) / (hi - lo) * (h - top - bottom);
  const body = Math.min(14, (w - left - right) * 0.68 * 300_000 / span);
  const labelTime = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour: "numeric", minute: "2-digit",
  });
  let svg = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(ticker)} five-minute candlestick chart">`;
  for (let i = 0; i <= 4; i++) {
    const price = lo + (hi - lo) * i / 4;
    svg += `<line class="candle-grid" x1="${left}" x2="${w-right}" y1="${y(price)}" y2="${y(price)}"/><text x="${w-right+10}" y="${y(price)+4}">${fmt(price)}</text>`;
  }
  for (let i = 0; i <= 4; i++) {
    const timestamp = start + span * i / 4;
    svg += `<text x="${x(timestamp)}" y="${h-7}" text-anchor="${i === 0 ? "start" : "middle"}">${labelTime.format(timestamp)}</text>`;
  }
  for (const bar of bars) {
    const cx = x(Date.parse(bar.t) + 150_000);
    const cls = bar.c >= bar.o ? "candle-up" : "candle-down";
    svg += `<g class="${cls}"><title>${labelTime.format(Date.parse(bar.t))} ET · Open ${fmt(bar.o)} · High ${fmt(bar.h)} · Low ${fmt(bar.l)} · Close ${fmt(bar.c)}</title>
      <line x1="${cx}" x2="${cx}" y1="${y(bar.h)}" y2="${y(bar.l)}"/>
      <rect x="${cx-body/2}" y="${Math.min(y(bar.o), y(bar.c))}" width="${body}" height="${Math.max(1, Math.abs(y(bar.o)-y(bar.c)))}"/></g>`;
  }
  $("intraday-chart").innerHTML = svg + "</svg>";
}
