/* Train app UI — talks only to the local harness API. */
const state = { nodes: [], current: null, config: null, pollTimer: null };

const $ = (id) => document.getElementById(id);
const els = {
  platform: $("platform"), list: $("node-list"), title: $("node-title"),
  lang: $("node-lang"), code: $("code"), goal: $("goal"),
  save: $("save"), run: $("run"), fix: $("fix"),
  status: $("editor-status"), console: $("console"), runMeta: $("run-meta"),
  toolchains: $("toolchains"), dataset: $("dataset"),
  exportBtn: $("export"), trainState: $("train-state"),
  backend: $("train-backend"), trainMode: $("train-mode"),
  model: $("train-model"), steps: $("train-steps"),
  trainStart: $("train-start"), trainStop: $("train-stop"), trainLog: $("train-log"),
  newNode: $("new-node"), newNodeForm: $("new-node-form"), newNodeName: $("new-node-name"),
  libCount: $("lib-count"), libStats: $("lib-stats"), libBuild: $("lib-build"),
  libValidate: $("lib-validate"), valBar: $("val-bar"), valStatus: $("val-status"),
  judgeStatus: $("judge-status"), tourState: $("tour-state"), tourTasks: $("tour-tasks"),
  tourStart: $("tour-start"), tourLog: $("tour-log"),
  growSeeds: $("grow-seeds"), growStart: $("grow-start"), growStatus: $("grow-status"),
};

async function api(path, method = "GET", body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
  return data;
}

function setStatus(text, bad = false) {
  els.status.textContent = text || "";
  els.status.style.color = bad ? "var(--bad)" : "var(--muted)";
}

function renderConsole(text) {
  els.console.textContent = text;
}

function stamp(ms) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

/* ── nodes ─────────────────────────────────────────────────────────────── */

async function loadNodes(select) {
  const data = await api("/api/nodes");
  state.nodes = data.nodes;
  els.list.innerHTML = "";
  for (const node of state.nodes) {
    const li = document.createElement("li");
    li.className = node.name === state.current ? "active" : "";
    li.innerHTML = `<span class="name"></span><span class="lang"></span>`;
    li.querySelector(".name").textContent = node.name;
    li.querySelector(".lang").textContent = node.language || "?";
    li.onclick = () => selectNode(node.name);
    els.list.appendChild(li);
  }
  if (select) await selectNode(select);
  else if (!state.current && state.nodes.length) await selectNode(state.nodes[0].name);
  else if (!state.nodes.length) {
    els.title.textContent = "No node selected";
    els.lang.textContent = "";
    els.code.value = "";
  }
}

async function selectNode(name) {
  const node = await api(`/api/nodes/${encodeURIComponent(name)}`);
  state.current = name;
  els.title.textContent = name;
  els.lang.textContent = node.language;
  els.code.value = node.code;
  els.runMeta.textContent = "";
  setStatus("");
  [...els.list.children].forEach((li) =>
    li.classList.toggle("active", li.querySelector(".name").textContent === name));
}

async function saveNode(quiet = false) {
  if (!state.current) return false;
  await api(`/api/nodes/${encodeURIComponent(state.current)}`, "PUT", { code: els.code.value });
  if (!quiet) setStatus("saved");
  return true;
}

els.newNode.onclick = () => els.newNodeForm.classList.toggle("hidden");
els.newNodeForm.onsubmit = async (event) => {
  event.preventDefault();
  const name = els.newNodeName.value.trim();
  if (!name) return;
  try {
    await api("/api/nodes", "POST", { name, code: "" });
    els.newNodeName.value = "";
    els.newNodeForm.classList.add("hidden");
    await loadNodes(name);
  } catch (err) {
    setStatus(err.message, true);
  }
};

els.save.onclick = () => saveNode().catch((err) => setStatus(err.message, true));

/* ── run + fix ─────────────────────────────────────────────────────────── */

function renderRun(run, prefix = "") {
  const lines = [
    `${prefix}$ ${run.command || "(no command — toolchain missing)"}`,
    `exit ${run.exit_code === null ? "—" : run.exit_code}   ${stamp(run.duration_ms)}   ${run.platform}`,
    run.error ? `error: ${run.error}` : "",
    run.output || (run.ok ? "(no output)" : "(no output, but it failed)"),
  ].filter(Boolean);
  return lines.join("\n");
}

function setBusy(busy) {
  [els.run, els.fix, els.save, els.newNode].forEach((b) => (b.disabled = busy));
}

els.run.onclick = async () => {
  if (!state.current) return;
  setBusy(true);
  setStatus("running…");
  try {
    await saveNode(true);
    const { run } = await api(`/api/nodes/${encodeURIComponent(state.current)}/run`, "POST", {});
    renderConsole(renderRun(run));
    els.runMeta.textContent = run.ok ? "passed" : "failed";
    els.runMeta.className = `pill ${run.ok ? "ok" : "bad"}`;
    setStatus(run.ok ? "passed" : "failed — Fix with LLM");
  } catch (err) {
    renderConsole(`harness error: ${err.message}`);
    setStatus(err.message, true);
  } finally {
    setBusy(false);
  }
};

els.fix.onclick = async () => {
  if (!state.current) return;
  setBusy(true);
  setStatus("LLM fixing… (a 14B on CPU/GPU can take a minute)");
  els.console.textContent = "Running the node, then asking the model for a fix…";
  try {
    await saveNode(true);
    const result = await api(`/api/nodes/${encodeURIComponent(state.current)}/fix`, "POST", {
      goal: els.goal.value,
      max_attempts: 3,
    });
    if (result.status === "error") {
      renderConsole(`error: ${result.error}`);
      setStatus(result.error, true);
      return;
    }
    if (result.status === "already_passing") {
      renderConsole(renderRun(result.run) + "\n\nNothing to fix — it already passes.");
      setStatus("already passing");
      return;
    }
    const parts = [renderRun(result.first_run, "before: ")];
    for (const attempt of result.attempts) {
      parts.push(
        `attempt ${attempt.attempt}: ${attempt.ok ? "passed" : "failed"}` +
        `${attempt.changed ? "" : " (no change returned)"}` +
        `${attempt.error ? ` — ${attempt.error}` : ""}`
      );
    }
    parts.push(renderRun(result.final_run, "after:  "));
    parts.push(result.captured
      ? `✓ captured as a verified training row (${result.captured_reason})`
      : `not captured: ${result.captured_reason}`);
    renderConsole(parts.join("\n\n"));
    els.runMeta.textContent = result.status === "fixed" ? "fixed" : "failed";
    els.runMeta.className = `pill ${result.status === "fixed" ? "ok" : "bad"}`;
    setStatus(result.status === "fixed" ? "fixed" : "could not fix — see output", result.status !== "fixed");
    if (result.status === "fixed") {
      const node = await api(`/api/nodes/${encodeURIComponent(state.current)}`);
      els.code.value = node.code;
    }
    await loadDataset();
  } catch (err) {
    renderConsole(`harness error: ${err.message}`);
    setStatus(err.message, true);
  } finally {
    setBusy(false);
  }
};

/* ── side panels ───────────────────────────────────────────────────────── */

async function loadToolchains() {
  const { toolchains } = await api("/api/toolchains");
  els.toolchains.innerHTML = "";
  for (const tool of toolchains) {
    const li = document.createElement("li");
    const dot = tool.available ? "yes" : "no";
    li.innerHTML = `<span class="${dot}">${tool.available ? "●" : "○"} ${tool.language}</span>`;
    li.title = tool.available ? tool.version : `${tool.error}\n${tool.install}`;
    els.toolchains.appendChild(li);
  }
}

async function loadDataset() {
  const stats = await api("/api/dataset");
  const langs = Object.entries(stats.by_language || {})
    .map(([lang, count]) => `${lang} ${count}`).join(" · ");
  const pairs = stats.pairs || {};
  els.dataset.innerHTML =
    `<b>${stats.rows}</b> verified row${stats.rows === 1 ? "" : "s"} · ${(stats.bytes / 1024).toFixed(1)} KB` +
    `<br><b>${pairs.pairs || 0}</b> preference pair${pairs.pairs === 1 ? "" : "s"}` +
    (langs ? `<br>${langs}` : "");
}

els.exportBtn.onclick = async () => {
  try {
    const meta = await api("/api/dataset/export", "POST", {});
    setStatus(`exported ${meta.train_examples} train / ${meta.val_examples} val`);
    await loadDataset();
  } catch (err) {
    setStatus(err.message, true);
  }
};

/* ── library + validation ──────────────────────────────────────────────── */

async function loadLibrary() {
  const data = await api("/api/library");
  const lib = data.library, judge = data.judge;
  els.libCount.textContent = `${lib.confirmed}/${lib.tasks} confirmed`;
  const statuses = Object.entries(lib.by_status || {})
    .map(([k, v]) => `${v} ${k}`).join(" · ") || "not ingested yet";
  els.libStats.innerHTML =
    `tasks <b>${lib.tasks}</b> · confirmed <b>${lib.confirmed}</b><br>${statuses}`;
  const judgeUp = judge.up ? (judge.served ? "served" : "model not pulled") : "unreachable";
  els.judgeStatus.textContent = `judge: ${judge.model} — ${judgeUp}`;
  els.judgeStatus.style.color = judge.up && judge.served ? "var(--ok)" : "var(--warn)";
}

function renderValidation(st) {
  if (!st || !st.state) return;
  const total = st.total || 0, done = st.done || 0;
  els.valBar.style.width = total ? `${Math.min(100, (done / total) * 100)}%` : "0%";
  if (st.state === "running") {
    els.valStatus.textContent =
      `${done}/${total} · ok ${st.verified || 0} · fail ${st.failed || 0} · ` +
      `missing ${st.missing || 0} · ${st.current || ""}`;
  } else if (st.state === "done") {
    els.valStatus.textContent =
      `done: ${st.verified} verified / ${st.failed} failed / ${st.missing} missing ` +
      `of ${st.total} in ${st.elapsed_s}s`;
  }
  return st.state;
}

let validationPoll = null;

async function pollValidation() {
  const st = await api("/api/library/validate/status");
  const state = renderValidation(st);
  if (state !== "running") {
    clearInterval(validationPoll);
    validationPoll = null;
    els.libValidate.disabled = false;
    loadLibrary();
    loadDataset();
  }
}

els.libBuild.onclick = async () => {
  els.libBuild.disabled = true;
  try {
    const { index } = await api("/api/library/build", "POST", {});
    els.libStats.textContent = `ingested ${index.total} tasks`;
    await loadLibrary();
  } catch (err) {
    els.valStatus.textContent = err.message;
  } finally {
    els.libBuild.disabled = false;
  }
};

els.libValidate.onclick = async () => {
  els.libValidate.disabled = true;
  try {
    await api("/api/library/validate", "POST", {});
    if (!validationPoll) validationPoll = setInterval(pollValidation, 2000);
  } catch (err) {
    els.valStatus.textContent = err.message;
    els.libValidate.disabled = false;
  }
};

/* ── growth ─────────────────────────────────────────── */

function renderGrow(st) {
  if (!st || !st.state) return st && st.state;
  const s = st.summary || {};
  const rejected = Object.entries(s.rejected || {})
    .filter(([, n]) => n).map(([k, n]) => `${k} ${n}`).join(" · ");
  if (st.state === "running") {
    els.growStatus.textContent = `growing: ${st.done || 0}/${st.seeds || 0} seeds · accepted ${st.accepted || 0}`;
  } else if (st.state === "failed") {
    els.growStatus.textContent = `growth failed: ${st.error || "unknown"}`;
  } else if (st.state === "done") {
    els.growStatus.textContent =
      `growth: accepted ${s.accepted || 0}/${s.candidates || 0} candidates` +
      (s.avg_bytes ? ` · ${s.avg_reference_bytes} -> ${s.avg_bytes} B` : "") +
      (rejected ? ` · rejected ${rejected}` : "");
  }
  return st.state;
}

let growPoll = null;

async function pollGrow() {
  const st = await api("/api/library/grow/status");
  const state = renderGrow(st);
  if (state !== "running") {
    clearInterval(growPoll);
    growPoll = null;
    els.growStart.disabled = false;
    loadLibrary();
    loadDataset();
  }
}

els.growStart.onclick = async () => {
  els.growStart.disabled = true;
  try {
    await api("/api/library/grow", "POST", { seeds: Number(els.growSeeds.value) || 3 });
    if (!growPoll) growPoll = setInterval(pollGrow, 3000);
  } catch (err) {
    els.growStatus.textContent = err.message;
    els.growStart.disabled = false;
  }
};

/* ── tournament ────────────────────────────────────────────────────────── */

function renderTournament(st) {
  if (!st || !st.state) return st && st.state;
  els.tourState.textContent = st.state;
  els.tourState.className = "pill " + (st.state === "running" ? "ok" : st.state === "failed" ? "bad" : "");
  const lines = [];
  if (st.error) lines.push(`error: ${st.error}`);
  if (st.tasks) lines.push(`${st.done || 0}/${st.tasks} tasks`);
  if (st.current) lines.push(`now: ${st.current}`);
  const s = st.summary || {};
  if (s.tasks) {
    lines.push(`variants verified: ${s.verified_variants}/${s.variants} (${Math.round((s.verified_rate || 0) * 100)}%)`);
    lines.push(`avg bytes: reference ${s.avg_reference_bytes} -> winner ${s.avg_winner_bytes}`);
    lines.push(`styles: ${Object.entries(s.style_wins || {}).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}`);
    lines.push(`preference pairs: ${s.pairs}`);
  }
  els.tourLog.textContent = lines.join("\n") || "No tournament yet.";
  return st.state;
}

let tournamentPoll = null;

async function pollTournament() {
  const st = await api("/api/tournament/status");
  const state = renderTournament(st);
  if (state !== "running") {
    clearInterval(tournamentPoll);
    tournamentPoll = null;
    els.tourStart.disabled = false;
  }
}

els.tourStart.onclick = async () => {
  els.tourStart.disabled = true;
  try {
    await api("/api/tournament/start", "POST", {
      max_tasks: Number(els.tourTasks.value) || 5,
    });
    if (!tournamentPoll) tournamentPoll = setInterval(pollTournament, 4000);
  } catch (err) {
    els.tourLog.textContent = err.message;
    els.tourStart.disabled = false;
  }
};

/* ── training ──────────────────────────────────────────────────────────── */

function renderTrainStatus(job) {
  els.trainState.textContent = job.state;
  els.trainState.className = "pill " + (job.state === "running" ? "ok" : job.state === "failed" ? "bad" : "");
  if (job.log) {
    els.trainLog.textContent =
      `${job.backend || ""} ${job.model || ""}\n${job.command || ""}\n\n${job.tail || ""}`;
  }
  const running = job.state === "running";
  els.trainStart.disabled = running;
  els.trainStop.disabled = !running;
  if (running && !state.pollTimer) {
    state.pollTimer = setInterval(() => api("/api/train/status")
      .then(renderTrainStatus).catch(stopPolling), 4000);
  }
  if (!running && state.pollTimer) stopPolling();
}

function stopPolling() {
  clearInterval(state.pollTimer);
  state.pollTimer = null;
}

els.trainStart.onclick = async () => {
  try {
    const job = await api("/api/train/start", "POST", {
      backend: els.backend.value,
      mode: els.trainMode.value,
      model: els.model.value.trim() || undefined,
      max_steps: Number(els.steps.value) || undefined,
    });
    renderTrainStatus(job);
    loadDataset();
  } catch (err) {
    els.trainState.textContent = "error";
    els.trainState.className = "pill bad";
    els.trainLog.textContent = err.message;
  }
};

els.trainStop.onclick = async () => {
  try {
    renderTrainStatus(await api("/api/train/stop", "POST", {}));
  } catch (err) {
    els.trainLog.textContent = err.message;
  }
};

/* ── boot ──────────────────────────────────────────────────────────────── */

(async function boot() {
  try {
    const health = await api("/api/health");
    els.platform.textContent = health.platform;
    const { config } = await api("/api/config");
    state.config = config;
    els.backend.value = config.training.backend;
    els.trainMode.value = config.training.mode || "sft";
    els.model.value = config.training.model;
    els.steps.value = config.training.max_steps;
    await Promise.all([loadToolchains(), loadNodes(), loadDataset(), loadLibrary()]);
    renderTrainStatus(await api("/api/train/status"));
    const validationState = renderValidation(await api("/api/library/validate/status"));
    if (validationState === "running") validationPoll = setInterval(pollValidation, 2000);
    const tournamentState = renderTournament(await api("/api/tournament/status"));
    if (tournamentState === "running") tournamentPoll = setInterval(pollTournament, 4000);
    const growState = renderGrow(await api("/api/library/grow/status"));
    if (growState === "running") growPoll = setInterval(pollGrow, 3000);
  } catch (err) {
    setStatus(`boot failed: ${err.message}`, true);
  }
})();
