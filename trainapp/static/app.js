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
  harvestRun: $("harvest-run"), harvestStatus: $("harvest-status"),
  orchState: $("orch-state"), orchRequire: $("orch-require"),
  orchLanguage: $("orch-language"), orchPlayer: $("orch-player"),
  orchAttempts: $("orch-attempts"), orchStart: $("orch-start"),
  orchLog: $("orch-log"), orchSmoke: $("orch-smoke"), orchExpect: $("orch-expect"),
  orchInputs: $("orch-inputs"),
  bState: $("builder-state"), bConnection: $("builder-connection"), bBrief: $("builder-brief"),
  bLangs: $("builder-langs"), bApps: $("builder-apps"), bStart: $("builder-start"),
  bLog: $("builder-log"),
  bandList: $("band-list"), bandCount: $("band-count"), bandLeader: $("band-leader"),
  bandAdd: $("band-add-form"), bandName: $("band-name"), bandModel: $("band-model"),
  bandUrl: $("band-url"), bandKey: $("band-key"), bandCopy: $("band-copy"),
  bandStatus: $("band-status"),
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

/* ── band ──────────────────────────────────────────────────────────────── */

const BAND_SEATS = ["coder", "builder", "judge"];

function seatLabel(member) {
  if (member.seats.length === 1) return member.seats[0];
  return member.seats.length ? `${member.seats.length} seats` : "no seat";
}

function renderBand(data) {
  const members = data.members || [];
  const playing = members.filter((m) => m.enabled);
  const lead = (data.leader && data.leader.name) || "";
  els.bandCount.textContent = `${playing.length}/${members.length} on`;
  els.bandStatus.textContent =
    `${lead ? `${lead} leads` : "no leader"} · ` +
    `${data.copy_builds ? "every build copied whole" : "build copies off"}`;
  els.bandStatus.title = data.path || "";
  els.bandStatus.style.color = lead ? "var(--muted)" : "var(--warn)";
  els.bandCopy.checked = !!data.copy_builds;

  els.bandLeader.innerHTML = "";
  els.bandList.innerHTML = "";
  for (const member of members) {
    if (member.enabled) {
      const option = document.createElement("option");
      option.value = member.name;
      option.textContent = `${member.name} — ${member.model}`;
      els.bandLeader.appendChild(option);
    }

    const li = document.createElement("li");
    li.className = member.enabled ? "band-row" : "band-row off";
    li.innerHTML =
      `<input type="checkbox" class="on" title="on / off" />` +
      `<span class="name"></span><span class="lang"></span>` +
      `<select class="seat"></select>` +
      `<button class="ghost check" title="is it answering?">?</button>` +
      `<button class="ghost hangup" title="hang up">×</button>`;
    const name = li.querySelector(".name");
    name.textContent = member.name + (member.leader ? " ★" : "");
    name.title = `${member.model}\n${member.url}`;
    li.querySelector(".lang").textContent = seatLabel(member);
    li.querySelector(".on").checked = member.enabled;

    const seat = li.querySelector(".seat");
    if (!member.seats.length) {
      const none = document.createElement("option");
      none.value = "";
      none.textContent = "no seat";
      seat.appendChild(none);
    }
    for (const role of BAND_SEATS) {
      const option = document.createElement("option");
      option.value = role;
      option.textContent = role;
      seat.appendChild(option);
    }
    seat.value = member.seats[0] || "";
    seat.onchange = () => {
      if (!seat.value) return;
      bandChange(`${member.name} now plays ${seat.value}`, "/api/band/seat",
        { role: seat.value, name: member.name });
    };
    li.querySelector(".on").onchange = (event) =>
      bandChange(`${member.name} switched ${event.target.checked ? "on" : "off"}`,
        "/api/band/toggle", { name: member.name, enabled: event.target.checked });
    li.querySelector(".hangup").onclick = () =>
      bandChange(`${member.name} left the band`, "/api/band/remove",
        { name: member.name });
    li.querySelector(".check").onclick = async () => {
      els.bandStatus.textContent = `asking ${member.name}…`;
      els.bandStatus.style.color = "var(--muted)";
      try {
        const { probe } = await api("/api/band/probe", "POST", { name: member.name });
        els.bandStatus.textContent = probe.up
          ? `${member.name}: up${probe.served ? "" : ` — ${member.model} not served`}` +
            `${probe.models.length ? ` (${probe.models.length} models)` : ""}`
          : `${member.name}: ${probe.error}`;
        els.bandStatus.style.color = probe.served ? "var(--ok)" : "var(--warn)";
      } catch (err) {
        els.bandStatus.textContent = err.message;
        els.bandStatus.style.color = "var(--bad)";
      }
    };
    els.bandList.appendChild(li);
  }
  if (lead) els.bandLeader.value = lead;

  // The builder picks a player, so it only offers players that are switched on.
  const chosen = els.bConnection.value;
  els.bConnection.innerHTML = "";
  for (const member of playing) {
    const option = document.createElement("option");
    option.value = member.name;
    option.textContent = `${member.name} — ${member.model}`;
    els.bConnection.appendChild(option);
  }
  const names = playing.map((m) => m.name);
  els.bConnection.value = names.includes(chosen) ? chosen : (lead || names[0] || "");

  // The orchestra offers the same players, the leader first by default.
  const oPlayer = els.orchPlayer.value;
  els.orchPlayer.innerHTML = "";
  for (const member of playing) {
    const option = document.createElement("option");
    option.value = member.name;
    option.textContent = `${member.name} — ${member.model}`;
    els.orchPlayer.appendChild(option);
  }
  els.orchPlayer.value = names.includes(oPlayer) ? oPlayer : (lead || names[0] || "");
}

async function loadBand() {
  renderBand(await api("/api/band"));
}

async function bandChange(note, path, body) {
  try {
    await api(path, "POST", body);
    els.bandStatus.textContent = note;
    els.bandStatus.style.color = "var(--muted)";
  } catch (err) {
    els.bandStatus.textContent = err.message;
    els.bandStatus.style.color = "var(--bad)";
  }
  // Re-read either way: a refused change has to put the toggle back.
  await loadBand().catch((err) => (els.bandStatus.textContent = err.message));
}

els.bandLeader.onchange = () =>
  bandChange(`${els.bandLeader.value} leads`, "/api/band/leader",
    { name: els.bandLeader.value });

els.bandCopy.onchange = () =>
  bandChange(
    els.bandCopy.checked ? "every build is copied" : "build copies off",
    "/api/band/copy", { enabled: els.bandCopy.checked });

els.bandAdd.onsubmit = async (event) => {
  event.preventDefault();
  const body = {
    name: els.bandName.value.trim(),
    model: els.bandModel.value.trim(),
    url: els.bandUrl.value.trim(),
    api_key: els.bandKey.value.trim(),
  };
  if (!body.name || !body.model || !body.url) {
    els.bandStatus.textContent = "a player needs a name, a model and a url";
    els.bandStatus.style.color = "var(--bad)";
    return;
  }
  await bandChange(`${body.name} joined the band`, "/api/band/add", body);
  els.bandName.value = els.bandModel.value = els.bandUrl.value = "";
  els.bandKey.value = "";
};

/* ── orchestra ────────────────────────────────────────────────────────── */

// The bug tracker, pass by pass: a failing run's history is the interesting
// part of it, and the console alone only shows the seats talking.
function passLines(job) {
  const lines = [];
  for (const entry of (job.passes || [])) {
    const failing = (entry.failing || []).join(", ");
    lines.push(`pass ${entry.pass}: ${entry.passed ? "passed" : "failed"}`
      + (entry.note ? ` — ${entry.note}` : "")
      + (failing ? ` · failing: ${failing}` : ""));
    const bugs = entry.bugs || [];
    for (const bug of bugs.slice(0, 6)) {
      lines.push(`  ${bug.resolved ? "✓" : "✗"} ${bug.path || "project"}: `
        + String(bug.error || "").slice(0, 160));
    }
    if (bugs.length > 6) lines.push(`  … ${bugs.length - 6} more`);
  }
  return lines;
}

function renderOrchestra(job) {
  if (!job || !job.state) return job && job.state;
  els.orchState.textContent = job.state;
  els.orchState.className = "pill " +
    (job.state === "running" ? "ok" : job.state === "failed" ? "bad" :
      job.state === "done" ? (job.passed ? "ok" : "bad") : "");
  const running = job.state === "running";
  els.orchStart.disabled = running;
  const lines = [];
  if (job.error) lines.push(`error: ${job.error}`);
  if (job.requirement) lines.push(`build: ${job.requirement}`);
  if (job.model) lines.push(`player: ${job.player || "leader"} — ${job.model}`);
  if (job.smoke) lines.push(`run: ${job.smoke}`);
  if (job.expect) lines.push(`expects: ${job.expect}`);
  lines.push(...(job.log || []));
  lines.push(...passLines(job));
  if (job.state === "done") {
    lines.push(job.passed
      ? `✓ built ${job.files.length} file(s)`
      : `✗ not built in ${job.attempts} pass(es)`);
    if (job.path) lines.push(`copy: ${job.path}`);
    for (const error of (job.errors || []).slice(0, 5)) lines.push(`  - ${error}`);
  }
  els.orchLog.textContent = lines.join("\n") || "No orchestra run yet.";
  return job.state;
}

let orchestraPoll = null;

async function pollOrchestra() {
  const job = await api("/api/orchestra/status");
  if (renderOrchestra(job) !== "running") {
    clearInterval(orchestraPoll);
    orchestraPoll = null;
    els.orchStart.disabled = false;
    await loadHarvest();
  }
}

els.orchStart.onclick = async () => {
  els.orchStart.disabled = true;
  try {
    const job = await api("/api/orchestra/start", "POST", {
      requirement: els.orchRequire.value.trim(),
      language: els.orchLanguage.value.trim() || "python",
      player: els.orchPlayer.value,
      attempts: Number(els.orchAttempts.value) || 3,
      smoke: els.orchSmoke.value.trim(),
      expect: els.orchExpect.value.trim(),
      inputs: els.orchInputs.value.split("\n").map((line) => line.trim())
        .filter(Boolean),
    });
    renderOrchestra(job);
    if (!orchestraPoll) orchestraPoll = setInterval(pollOrchestra, 3000);
  } catch (err) {
    els.orchLog.textContent = err.message;
    els.orchStart.disabled = false;
  }
};

/* ── harvest ──────────────────────────────────────────────────────────── */

async function loadHarvest() {
  try {
    const st = await api("/api/harvest/status");
    els.harvestStatus.textContent = st.state === "never"
      ? "never harvested"
      : `${st.state} ${st.month || ""} · ${st.added || 0} task(s) from ` +
        `${st.runs || 0} run(s)`;
    els.harvestStatus.title = st.sheet || "";
  } catch (err) {
    els.harvestStatus.textContent = err.message;
  }
}

els.harvestRun.onclick = async () => {
  els.harvestRun.disabled = true;
  els.harvestStatus.textContent = "reading the build copies…";
  try {
    const result = await api("/api/harvest/run", "POST", {});
    els.harvestStatus.textContent = result.state === "skipped"
      ? `skipped — ${result.reason}`
      : `${result.added} task(s) from ${result.new_runs} new run(s) · ` +
        `${result.sft_rows} training row(s)`;
    await loadLibrary();
  } catch (err) {
    els.harvestStatus.textContent = err.message;
  }
  els.harvestRun.disabled = false;
};

/* ── builder ───────────────────────────────────────────────────────────── */

function renderBuilder(st) {
  if (!st || !st.state) return st && st.state;
  els.bState.textContent = st.state;
  els.bState.className =
    "pill " + (st.state === "running" ? "ok" : st.state === "failed" ? "bad" : "");
  els.bStart.disabled = st.state === "running";
  const lines = [];
  if (st.error) lines.push(`error: ${st.error}`);
  if (st.model) lines.push(`model: ${st.model}`);
  if (st.apps) lines.push(`${st.done || 0}/${st.apps} apps${st.current ? ` · now: ${st.current}` : ""}`);
  for (const record of st.records || []) {
    lines.push(`${record.ok ? "✓" : "✗"} ${record.id} (${record.language}) ` +
      `${record.files.length} file${record.files.length === 1 ? "" : "s"}, ` +
      `${record.runs} run${record.runs === 1 ? "" : "s"}` +
      `${record.conventions ? ", used copied conventions" : ""}` +
      `${record.added ? "" : " (already in pool)"}`);
  }
  const lanes = Object.entries(st.scaffold || {});
  if (lanes.length) {
    lines.push("conventions on file: " + lanes
      .map(([lang, s]) => `${lang} ${s.built}/${s.models}`).join(" · "));
  }
  els.bLog.textContent = lines.join("\n") || "No build yet.";
  return st.state;
}

let builderPoll = null;

async function pollBuilder() {
  const st = await api("/api/builder/status");
  const builderState = renderBuilder(st);
  if (builderState !== "running") {
    clearInterval(builderPoll);
    builderPoll = null;
    els.bStart.disabled = false;
    loadLibrary();
  }
}

els.bStart.onclick = async () => {
  els.bStart.disabled = true;
  try {
    await api("/api/builder/start", "POST", {
      connection: els.bConnection.value,
      brief: els.bBrief.value.trim(),
      languages: els.bLangs.value.trim(),
      apps: Number(els.bApps.value) || 1,
    });
    if (!builderPoll) builderPoll = setInterval(pollBuilder, 3000);
    await pollBuilder();
  } catch (err) {
    els.bLog.textContent = err.message;
    els.bStart.disabled = false;
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
    await loadBand();
    renderTrainStatus(await api("/api/train/status"));
    const validationState = renderValidation(await api("/api/library/validate/status"));
    if (validationState === "running") validationPoll = setInterval(pollValidation, 2000);
    const tournamentState = renderTournament(await api("/api/tournament/status"));
    if (tournamentState === "running") tournamentPoll = setInterval(pollTournament, 4000);
    const growState = renderGrow(await api("/api/library/grow/status"));
    if (growState === "running") growPoll = setInterval(pollGrow, 3000);
    const builderState = renderBuilder(await api("/api/builder/status"));
    if (builderState === "running") builderPoll = setInterval(pollBuilder, 3000);
    const orchestraState = renderOrchestra(await api("/api/orchestra/status"));
    if (orchestraState === "running") orchestraPoll = setInterval(pollOrchestra, 3000);
    await loadHarvest();
  } catch (err) {
    setStatus(`boot failed: ${err.message}`, true);
  }
})();
