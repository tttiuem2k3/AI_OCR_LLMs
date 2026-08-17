const el = (id) => document.getElementById(id);

// --- Các phần tử UI chính ---
const chatWindow = el("chatWindow");
const modelSelect = el("modelSelect");
const activeModel = el("activeModel");
const btnLoadModel = el("btnLoadModel");
const btnReloadModels = el("btnReloadModels");
const btnClear = el("btnClear");
const chatForm = el("chatForm");
const promptInput = el("promptInput");
const btnSend = el("btnSend");
const healthBadge = el("healthBadge");
const maxTokensEl = el("maxTokens");
const temperatureEl = el("temperature");

// --- Kết nối server / Token ---
const tokenInput = el("tokenInput");
const btnConnect = el("btnConnect");
const tokenBadge = el("tokenBadge");
const connectStatus = el("connectStatus");
const connectStatusText = el("connectStatusText");
const modelLockedBox = el("modelLockedBox");

let currentAssistantBody = null;

// Trạng thái kết nối
let isConnected = false;
let loadedModelId = null;

// Lưu token trong localStorage để lần sau khỏi nhập lại
const TOKEN_STORAGE_KEY = "local_ai_server_token";

function getToken() {
  return (localStorage.getItem(TOKEN_STORAGE_KEY) || "").trim();
}

function setToken(token) {
  const t = (token || "").trim();
  if (t) localStorage.setItem(TOKEN_STORAGE_KEY, t);
  else localStorage.removeItem(TOKEN_STORAGE_KEY);
  if (tokenInput) tokenInput.value = t;
}

function setTokenBadge(state, text) {
  // state: "ok" | "bad" | "idle"
  if (!tokenBadge) return;
  if (state === "ok") {
    tokenBadge.textContent = text || "Đã kết nối";
    tokenBadge.className = "text-[11px] px-2 py-1 rounded-full border border-zinc-800 bg-emerald-900/30 text-emerald-200";
  } else if (state === "bad") {
    tokenBadge.textContent = text || "Kết nối thất bại";
    tokenBadge.className = "text-[11px] px-2 py-1 rounded-full border border-zinc-800 bg-red-900/30 text-red-200";
  } else {
    tokenBadge.textContent = text || "Chưa kết nối";
    tokenBadge.className = "text-[11px] px-2 py-1 rounded-full border border-zinc-800 bg-zinc-950 text-zinc-300";
  }
}

function showConnectStatus(kind, text) {
  // kind: "ok" | "bad" | "info"
  if (!connectStatus || !connectStatusText) return;
  connectStatus.classList.remove("hidden");
  connectStatusText.textContent = text;

  if (kind === "ok") {
    connectStatus.className = "mt-4 rounded-xl border border-zinc-800 bg-emerald-950/30 p-3";
    connectStatusText.className = "text-sm font-semibold mt-1 text-emerald-200";
  } else if (kind === "bad") {
    connectStatus.className = "mt-4 rounded-xl border border-zinc-800 bg-red-950/30 p-3";
    connectStatusText.className = "text-sm font-semibold mt-1 text-red-200";
  } else {
    connectStatus.className = "mt-4 rounded-xl border border-zinc-800 bg-zinc-950 p-3";
    connectStatusText.className = "text-sm font-semibold mt-1 text-zinc-200";
  }
}

function setModelControlsEnabled(enabled) {
  if (btnReloadModels) btnReloadModels.disabled = !enabled;
  if (btnLoadModel) btnLoadModel.disabled = !enabled;
  if (modelSelect) modelSelect.disabled = !enabled;

  if (modelLockedBox && modelSelect) {
    if (enabled) {
      modelLockedBox.classList.add("hidden");
      modelSelect.classList.remove("hidden");
    } else {
      modelLockedBox.classList.remove("hidden");
      modelSelect.classList.add("hidden");
    }
  }
}

function resetConnectionUI() {
  isConnected = false;
  loadedModelId = null;
  setTokenBadge("idle", "Chưa kết nối");
  setModelControlsEnabled(false);
  if (modelSelect) modelSelect.innerHTML = "";
  if (activeModel) activeModel.textContent = "Chưa có";
}

function withToken(url) {
  const t = getToken();
  if (!t) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}Token=${encodeURIComponent('"' + t + '"')}`;
}

async function apiFetch(url, options) {
  return fetch(withToken(url), options);
}

function splitAnalysisAndAnswer(text) {
  if (!text) return { analysis: "", answer: "" };
  const match = text.match(/^analysis\s*([\s\S]*?)\s*assistantfinal:?\s*([\s\S]*)$/i);
  if (!match) return { analysis: "", answer: text };
  return {
    analysis: (match[1] || "").trim(),
    answer: (match[2] || "").trim()
  };
}

function createAssistantReasoningUI(bodyEl) {
  const details = document.createElement("details");
  details.className = "group";
  details.open = false;
  // Default: ẩn cho tới khi có reasoning thật sự (analysisAdd)
  details.hidden = true;
  const summary = document.createElement("summary");
  summary.className = [
    "cursor-pointer select-none",
    "text-xs text-zinc-400",
    "hover:text-zinc-300",
    "list-none flex items-center gap-2"
  ].join(" ");
  summary.innerHTML = `
    <span class=\"px-2 py-1 rounded-lg border border-zinc-800 bg-zinc-950/60\">Show reasoning</span>
    <span class=\"text-[11px] text-zinc-500 group-open:hidden\">(click to expand)</span>
    <span class=\"text-[11px] text-zinc-500 hidden group-open:inline\">(click to collapse)</span>
  `;
  const reasoning = document.createElement("div");
  reasoning.dataset.role = "assistant-reasoning";
  reasoning.className = [
    "mt-2",
    "rounded-xl border border-zinc-800 bg-zinc-950/40",
    "px-3 py-2",
    "text-xs text-zinc-400 italic",
    "whitespace-pre-wrap leading-relaxed"
  ].join(" ");
  details.appendChild(summary);
  details.appendChild(reasoning);
  bodyEl.appendChild(details);
  const answer = document.createElement("div");
  answer.dataset.role = "assistant-answer";
  answer.className = [
    "mt-3",
    "text-sm text-zinc-100",
    "whitespace-pre-wrap leading-relaxed"
  ].join(" ");
  bodyEl.appendChild(answer);
  return { reasoningEl: reasoning, answerEl: answer, detailsEl: details };
}

function createReasoningStreamParser() {
  let mode = "analysis";
  let carry = "";
  const MARKER_RE = /assistantfinal:?\s*/i;
  return {
    push(deltaText) {
      let text = carry + (deltaText || "");
      let analysisAdd = "";
      let finalAdd = "";
      if (mode === "analysis") {
        const m = text.match(MARKER_RE);
        if (m) {
          const idx = text.search(MARKER_RE);
          analysisAdd = text.slice(0, idx);
          const after = text.slice(idx).replace(MARKER_RE, "");
          mode = "final";
          finalAdd = after;
          carry = "";
        } else {
          const keep = 30;
          if (text.length > keep) {
            analysisAdd = text.slice(0, text.length - keep);
            carry = text.slice(text.length - keep);
          } else {
            carry = text;
          }
        }
      } else {
        finalAdd = text;
        carry = "";
      }
      analysisAdd = analysisAdd.replace(/^analysis\s*/i, "");
      return { analysisAdd, finalAdd };
    },
    flush() {
      const remaining = carry.replace(/^analysis\s*/i, "");
      carry = "";
      if (!remaining) return { analysisAdd: "", finalAdd: "" };
      return mode === "analysis"
        ? { analysisAdd: remaining, finalAdd: "" }
        : { analysisAdd: "", finalAdd: remaining };
    }
  };
}

function addBubble(role, text) {
  const wrap = document.createElement("div");
  wrap.className = "flex";
  const bubble = document.createElement("div");

  const isUser = role === "user";
  wrap.classList.add(isUser ? "justify-end" : "justify-start");

  bubble.className = [
    "max-w-[85%] rounded-2xl px-4 py-3 border text-sm whitespace-pre-wrap leading-relaxed",
    isUser
      ? "bg-indigo-600/20 border-indigo-500/30"
      : "bg-zinc-950 border-zinc-800"
  ].join(" ");

  const header = document.createElement("div");
  header.className = "text-[11px] uppercase tracking-wide text-zinc-400 mb-2";
  header.textContent = isUser ? "You" : "Assistant";

  const body = document.createElement("div");

  let reasoningEl = null;
  let answerEl = null;
  const isOss20b = !isUser && loadedModelId && loadedModelId.includes("gpt_oss_20b");
  if (isOss20b) {
    const ui = createAssistantReasoningUI(body);
    reasoningEl = ui.reasoningEl;
    answerEl = ui.answerEl;
  } else {
    body.textContent = text || "";
  }

  bubble.appendChild(header);
  bubble.appendChild(body);
  wrap.appendChild(bubble);
  chatWindow.appendChild(wrap);
  chatWindow.scrollTop = chatWindow.scrollHeight;

  return { body, reasoningEl, answerEl };
}

function setHealth(ok, activeId, activeName) {
  if (ok) {
    if (activeId) {
      // Prefer readable name; only show id when name is missing.
      const label = (activeName || "").trim() || activeId;
      healthBadge.textContent = `Healthy • Active: ${label}`;
    } else {
      healthBadge.textContent = "Healthy • No active model";
    }
    healthBadge.className = "px-3 py-1 rounded-full border border-zinc-800 bg-emerald-900/30 text-emerald-200 text-xs";
  } else {
    healthBadge.textContent = "Unhealthy";
    healthBadge.className = "px-3 py-1 rounded-full border border-zinc-800 bg-red-900/30 text-red-200 text-xs";
  }
}

async function refreshHealth() {
  try {
    const r = await fetch("/api/health");
    const j = await r.json();
    setHealth(true, j.active_model_id, j.active_model_name);

    if (j.active_model_id) {
      activeModel.textContent = (j.active_model_name || "").trim() || j.active_model_id;
    }
  } catch {
    setHealth(false);
  }
}

async function connectServer() {
  const token = (tokenInput?.value || "").trim();
  if (!token) {
    setTokenBadge("bad", "Thiếu token");
    showConnectStatus("bad", "Vui lòng nhập API Token để kết nối.");
    resetConnectionUI();
    return;
  }

  const prevSelectedModelId = modelSelect?.value || null;

  setToken(token);
  btnConnect.disabled = true;
  setTokenBadge("idle", "Đang kết nối...");
  showConnectStatus("info", "Đang kiểm tra token và lấy danh sách mô hình...");

  try {
    const r = await apiFetch("/connect", { method: "GET" });
    const j = await r.json().catch(() => ({}));

    if (!r.ok) {
      const msg = j.detail || j.message || `HTTP ${r.status}`;
      throw new Error(msg);
    }

    const models = Array.isArray(j.models) ? j.models : [];

    modelSelect.innerHTML = "";
    for (const m of models) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `${m.name} (${m.id})`;
      modelSelect.appendChild(opt);
    }

    // Ưu tiên chọn model đang active (thường là SPECIAL_MODEL_ID khi khởi động)
    if (j.active_model_id && [...modelSelect.options].some((o) => o.value === j.active_model_id)) {
      modelSelect.value = j.active_model_id;
    } else if (prevSelectedModelId && [...modelSelect.options].some((o) => o.value === prevSelectedModelId)) {
      modelSelect.value = prevSelectedModelId;
    }

    isConnected = true;
    loadedModelId = j.active_model_id || null;

    setModelControlsEnabled(true);
    setTokenBadge("ok", "Đã kết nối");

    if (connectStatus) connectStatus.classList.add("hidden");

    if (j.active_model_id) {
      activeModel.textContent = (j.active_model_name || "").trim() || j.active_model_id;
    } else {
      activeModel.textContent = "Chưa có";
    }
  } catch (e) {
    resetConnectionUI();
    setTokenBadge("bad", "Kết nối thất bại");
    showConnectStatus("bad", `Kết nối thất bại: ${e.message || e}`);
  } finally {
    btnConnect.disabled = false;
  }
}

async function startModel() {
  if (!isConnected) {
    addBubble("assistant", "❌ Bạn chưa kết nối server.");
    return;
  }
  const model_id = modelSelect.value;
  if (!model_id) {
    addBubble("assistant", "❌ Vui lòng chọn mô hình.");
    return;
  }
  btnLoadModel.disabled = true;
  btnLoadModel.textContent = "Đang khởi động...";
  try {
    // Kiểm tra mô hình đã load chưa
    const hr = await fetch("/api/health");
    const hj = await hr.json().catch(() => ({}));
    const activeId = hj.active_model_id || null;
    const isOss20b = model_id.includes("gpt_oss_20b");
    if (activeId && activeId === model_id) {
      const label = (hj.active_model_name || "").trim() || activeId;
      loadedModelId = activeId;
      activeModel.textContent = label;
      if (isOss20b) {
        // Hiển thị reasoning + answer rõ ràng
        const msg = `User nhấn nút khởi động mô hình GPT 20B oss, nhưng hiện tại đã khởi động rồi.`;
        const answer = `Mô hình đã được khởi động: ${label}`;
        const ui = addBubble("assistant", "");
        if (ui.reasoningEl && ui.answerEl) {
          ui.reasoningEl.textContent = msg;
          ui.answerEl.textContent = answer;
        } else {
          addBubble("assistant", answer);
        }
      } else {
        addBubble("assistant", `✅ Mô hình đã được khởi động: ${label}`);
      }
      await refreshHealth();
      return;
    }
    // Nếu đang có model khác thì unload trước
    if (activeId && activeId !== model_id) {
      const ur = await apiFetch("/api/models/unload", { method: "POST" });
      const uj = await ur.json().catch(() => ({}));
      if (!ur.ok) {
        const msg = uj.detail || uj.message || `Unload failed (HTTP ${ur.status})`;
        if (ur.status === 401) {
          resetConnectionUI();
          setTokenBadge("bad", "Token sai");
          showConnectStatus("bad", "Token không hợp lệ. Vui lòng nhập lại token và Kết nối Server.");
        }
        throw new Error(msg);
      }
    }
    // Khởi động mô hình mới
    const r = await apiFetch("/api/models/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id })
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg = j.detail || "Load failed";
      if (r.status === 401) {
        resetConnectionUI();
        setTokenBadge("bad", "Token sai");
        showConnectStatus("bad", "Token không hợp lệ. Vui lòng nhập lại token và Kết nối Server.");
      }
      throw new Error(msg);
    }
    loadedModelId = j.active_model_id;
    activeModel.textContent = (j.active_model_name || "").trim() || j.active_model_id;
    if (isOss20b) {
      const msg = `User nhấn nút khởi động mô hình GPT 20B oss, thực hiện khời động mô hình....`;
      const answer = `Mô hình khởi động thành công: ${j.active_model_name}`;
      const ui = addBubble("assistant", "");
      if (ui.reasoningEl && ui.answerEl) {
        ui.reasoningEl.textContent = msg;
        ui.answerEl.textContent = answer;
      } else {
        addBubble("assistant", answer);
      }
    } else {
      addBubble("assistant", `✅ Khởi động mô hình thành công: ${j.active_model_name || j.active_model_id}`);
    }
    await refreshHealth();
  } catch (e) {
    addBubble("assistant", `❌ Lỗi khởi động mô hình: ${e.message || e}`);
  } finally {
    btnLoadModel.disabled = !isConnected;
    btnLoadModel.textContent = "Khởi động";
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function typewriterTo(el, fullText, opts = {}) {
  const speedMs = Math.max(0, Number(opts.speedMs ?? 12));
  const chunk = Math.max(1, Number(opts.chunk ?? 2));

  if (!el) return;
  // If the server already streamed some text, continue from current length.
  const start = (el.textContent || "").length;
  for (let i = start; i < fullText.length; i += chunk) {
    el.textContent = fullText.slice(0, i + chunk);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    if (speedMs) await sleep(speedMs);
  }
}

async function streamChat({ model_id, messages, max_new_tokens, temperature }) {
  const r = await apiFetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_id, messages, max_new_tokens, temperature })
  });

  if (!r.ok) {
    const err = await r.text();
    if (r.status === 401) {
      resetConnectionUI();
      setTokenBadge("bad", "Token sai");
      showConnectStatus("bad", "Token không hợp lệ. Vui lòng nhập lại token và Kết nối Server.");
    }
    throw new Error(err || "Request failed");
  }

  // Some proxies/IIS configurations may buffer and return a non-stream JSON response.
  const ct = (r.headers.get("content-type") || "").toLowerCase();
  if (!r.body || ct.includes("application/json")) {
    const j = await r.json().catch(() => ({}));
    const answer = j.answer || j.text || j.content || "";

    let currentReasoningEl = null;
    let currentAnswerEl = null;
    let currentDetailsEl = null;

    // If chatForm already prepared currentAssistantBody (assistant bubble), reuse it.
    if (currentAssistantBody) {
      currentReasoningEl = currentAssistantBody.querySelector('[data-role="assistant-reasoning"]') || null;
      currentAnswerEl = currentAssistantBody.querySelector('[data-role="assistant-answer"]') || null;
      currentDetailsEl = currentAssistantBody.querySelector("details") || null;
    }

    if (!currentAssistantBody) {
      const ui = addBubble("assistant", "");
      currentAssistantBody = ui.body;
      currentReasoningEl = ui.reasoningEl;
      currentAnswerEl = ui.answerEl;
      currentDetailsEl = currentAssistantBody.querySelector("details") || null;
    }

    // Auto-open while streaming/typewriter the reasoning, close when done.
    if (currentDetailsEl) {
      // Only show when we actually have reasoning; for JSON fallback we may have
      // analysis+final combined, so show now if analysis part exists.
      currentDetailsEl.hidden = false;
      currentDetailsEl.open = true;
    }

    try {
      if (currentReasoningEl && currentAnswerEl) {
        const m = answer.match(/^analysis\s*([\s\S]*?)\s*assistantfinal:?\s*([\s\S]*)$/i);
        if (m) {
          await typewriterTo(currentReasoningEl, (m[1] || "").trim(), { speedMs: 10, chunk: 2 });
          await sleep(100);
          await typewriterTo(currentAnswerEl, (m[2] || "").trim(), { speedMs: 10, chunk: 2 });
        } else {
          // No analysis => keep details hidden
          if (currentDetailsEl) {
            currentDetailsEl.hidden = true;
            currentDetailsEl.open = false;
          }
          await typewriterTo(currentAnswerEl, answer || "", { speedMs: 10, chunk: 2 });
        }
      } else {
        // Non-reasoning models: always render into the dedicated answer element when available.
        const target = currentAnswerEl || currentAssistantBody;
        await typewriterTo(target, answer || "", { speedMs: 10, chunk: 2 });
      }
    } finally {
      if (currentDetailsEl) currentDetailsEl.open = false;
    }

    currentAssistantBody = null;
    return;
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder("utf-8");

  let buffer = "";
  let fullAnswer = "";
  let sawAnyDelta = false;
  let reads = 0;

  let currentReasoningEl = null;
  let currentAnswerEl = null;
  let currentDetailsEl = null;
  let reasoningParser = null;

  const tStart = Date.now();
  let tFirstByteMs = null;
  let tFirstDeltaMs = null;

  // Ensure we have an assistant bubble ready
  if (!currentAssistantBody) {
    const ui = addBubble("assistant", "");
    currentAssistantBody = ui.body;
    currentReasoningEl = ui.reasoningEl;
    currentAnswerEl = ui.answerEl;
    currentDetailsEl = currentAssistantBody.querySelector("details") || null;

    if (currentReasoningEl && currentAnswerEl) {
      reasoningParser = createReasoningStreamParser();
    }
  } else {
    // Reuse the already-prepared container (from chatForm)
    currentReasoningEl = currentAssistantBody.querySelector('[data-role="assistant-reasoning"]') || null;
    currentAnswerEl = currentAssistantBody.querySelector('[data-role="assistant-answer"]') || null;
    currentDetailsEl = currentAssistantBody.querySelector("details") || null;

    if (currentReasoningEl && currentAnswerEl) {
      reasoningParser = createReasoningStreamParser();
    }
  }

  // Hiệu ứng typewriter khi stream từng token
  let reasoningBuffer = "";
  let answerBuffer = "";
  let openedDetailsForStream = false;

  while (true) {
    const { value, done } = await reader.read();
    reads += 1;
    if (done) break;

    if (tFirstByteMs === null) tFirstByteMs = Date.now() - tStart;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();

    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;

      const payload = JSON.parse(line.replace("data: ", ""));
      if (payload.type === "delta") {
        if (!sawAnyDelta) {
          sawAnyDelta = true;
          tFirstDeltaMs = Date.now() - tStart;
        }
        const delta = payload.text || "";
        fullAnswer += delta;

        if (reasoningParser && currentReasoningEl && currentAnswerEl) {
          const { analysisAdd, finalAdd } = reasoningParser.push(delta);
          if (analysisAdd) {
            // Chỉ hiện Show reasoning khi có reasoning thật sự
            if (currentDetailsEl && !openedDetailsForStream) {
              currentDetailsEl.hidden = false;
              currentDetailsEl.open = true;
              openedDetailsForStream = true;
            }
            reasoningBuffer += analysisAdd;
            await typewriterTo(currentReasoningEl, reasoningBuffer, { speedMs: 8, chunk: 2 });
          }
          if (finalAdd) {
            answerBuffer += finalAdd;
            await typewriterTo(currentAnswerEl, answerBuffer, { speedMs: 8, chunk: 2 });
          }
        } else {
          // Non-reasoning models: stream into answer element only (do not overwrite container).
          const target = currentAnswerEl || currentAssistantBody;
          await typewriterTo(target, fullAnswer, { speedMs: 8, chunk: 2 });
        }

        chatWindow.scrollTop = chatWindow.scrollHeight;
      } else if (payload.type === "done") {
        // We'll finalize below
      } else if (payload.type === "error") {
        addBubble("assistant", `❌ Error: ${payload.message}`);
        currentAssistantBody = null;
        return;
      }
    }
  }

  const tEnd = Date.now();
  const totalMs = tEnd - tStart;

  // Decide whether to force a typewriter animation.
  // IIS/FastCGI buffering symptom: we receive the whole answer only near the end.
  // Heuristic triggers (broad on purpose):
  // - no incremental deltas
  // - first byte arrives late
  // - response finishes too quickly *after* first byte (common when buffered, then flushed at once)
  const noRealStreaming = !sawAnyDelta;
  const firstByteLate = tFirstByteMs !== null && tFirstByteMs > 800;
  const burstyFlush = tFirstByteMs !== null && totalMs < Math.max(1200, tFirstByteMs + 150);
  const bufferedLikely = noRealStreaming || firstByteLate || burstyFlush;

  // Debug instrumentation to verify behavior in browser devtools.
  try {
    console.debug("[llms][stream] metrics", {
      reads,
      sawAnyDelta,
      tFirstByteMs,
      tFirstDeltaMs,
      totalMs,
      bufferedLikely
    });
  } catch {}

  if (reasoningParser && currentReasoningEl && currentAnswerEl) {
    const { analysisAdd, finalAdd } = reasoningParser.flush();
    if (analysisAdd) {
      // Make sure open while we flush remaining reasoning.
      if (currentDetailsEl) {
        currentDetailsEl.hidden = false;
        currentDetailsEl.open = true;
      }
      reasoningBuffer += analysisAdd;
      await typewriterTo(currentReasoningEl, reasoningBuffer, { speedMs: 8, chunk: 2 });
      openedDetailsForStream = true;
    }
    if (finalAdd) {
      answerBuffer += finalAdd;
      await typewriterTo(currentAnswerEl, answerBuffer, { speedMs: 8, chunk: 2 });
    }
  }

  // Close AFTER we've rendered everything.
  if (currentDetailsEl && openedDetailsForStream) {
    currentDetailsEl.open = false;
  }

  if (currentAssistantBody) {
    currentAssistantBody = null;
  }
}

function formatDuration(ms) {
  const total = Math.max(0, Math.round(ms));
  if (total < 1000) return `${total} ms`;
  const s = total / 1000;
  if (s < 60) return `${s.toFixed(2)} s`;
  const m = Math.floor(s / 60);
  const rs = (s - m * 60).toFixed(1);
  return `${m}m ${rs}s`;
}

function prependThinkingTime(bodyEl, ms) {
  if (!bodyEl) return;
  const line = document.createElement("div");
  line.className = "text-[11px] text-zinc-500 mb-2";
  line.textContent = `⏱️ Đã suy nghĩ trong ${formatDuration(ms)}`;
  bodyEl.prepend(line);
}

function prependThinkingTimeBefore(el, ms) {
  if (!el || !el.parentElement) return;
  const line = document.createElement("div");
  line.className = "text-[11px] text-zinc-500 mb-2";
  line.textContent = `⏱️ Đã suy nghĩ trong ${formatDuration(ms)}`;
  el.parentElement.insertBefore(line, el);
}

btnClear?.addEventListener("click", () => {
  chatWindow.innerHTML = "";
});

btnConnect?.addEventListener("click", async () => {
  await connectServer();
});

btnReloadModels?.addEventListener("click", async () => {
  if (!isConnected) return;
  btnReloadModels.disabled = true;
  try {
    await connectServer();
  } finally {
    btnReloadModels.disabled = false;
  }
});

btnLoadModel?.addEventListener("click", async () => {
  await startModel();
});

chatForm?.addEventListener("submit", async (ev) => {
  ev.preventDefault();

  const prompt = (promptInput.value || "").trim();
  if (!prompt) return;

  if (!isConnected) {
    addBubble("assistant", "❌ Bạn chưa kết nối server. Hãy nhập token và bấm 'Kết nối Server'.");
    return;
  }

  if (!loadedModelId) {
    addBubble("assistant", "❌ Bạn chưa khởi động mô hình. Hãy bấm 'Khởi động mô hình' trước.");
    return;
  }

  btnSend.disabled = true;

  // Luôn gửi đúng loadedModelId (model đã được khởi động)
  const model_id = loadedModelId;
  const max_new_tokens = parseInt(maxTokensEl.value || "1024", 10);
  const temperature = parseFloat(temperatureEl.value || "0.5");

  addBubble("user", prompt);
  promptInput.value = "";

  // Hiệu ứng assistant đang suy nghĩ
  let thinkingBubble = null;
  let thinkingInterval = null;
  const tThinkingStart = performance.now();
  let wrapper = null;
  let answerEl = null;

  // NEW: keep a reference to the assistant bubble body (container)
  let assistantBodyEl = null;

  try {
    thinkingBubble = addBubble("assistant", "");
    assistantBodyEl = thinkingBubble.body;

    const isOss20b = loadedModelId && loadedModelId.includes("gpt_oss_20b");

    // Wrapper chứa dots (chiều cao cố định)
    wrapper = document.createElement('div');
    wrapper.style.height = '28px';
    wrapper.style.minHeight = '28px';
    wrapper.style.maxHeight = '28px';
    // Tạo khoảng cách dọc giữa 3 chấm và phần Show reasoning/answer
    wrapper.style.marginBottom = '8px';
    wrapper.style.display = 'flex';
    wrapper.style.alignItems = 'center';
    wrapper.style.justifyContent = 'flex-start';
    wrapper.style.overflow = 'hidden';
    wrapper.innerHTML = `
      <div class="thinking-dots" style="display:flex;flex-direction:row;align-items:center;gap:12px;height:24px;min-height:24px;max-height:24px;padding:0;margin:0;">
        <span class="dot" style="padding:0px;margin-left:4px;width:8px;height:8px;border-radius:50%;background:#a1a1aa;opacity:0.4;transition:all 0.3s;"></span>
        <span class="dot" style="padding:0px;margin:0px;width:8px;height:8px;border-radius:50%;background:#a1a1aa;opacity:0.4;transition:all 0.3s;"></span>
        <span class="dot" style="padding:0px;margin:0px;width:8px;height:8px;border-radius:50%;background:#a1a1aa;opacity:0.4;transition:all 0.3s;"></span>
      </div>
    `;

    // Dọn nội dung bubble và dựng layout: dots + (reasoning+answer hoặc answer)
    assistantBodyEl.innerHTML = "";
    assistantBodyEl.appendChild(wrapper);

    if (isOss20b) {
      // Dựng UI reasoning như cũ để stream đúng chỗ
      const ui = createAssistantReasoningUI(assistantBodyEl);
      // Yêu cầu: chỉ hiện Show reasoning khi có chữ reasoning xuất hiện.
      // Vì vậy để hidden=true (đã set trong createAssistantReasoningUI) và KHÔNG auto-open ở đây.
      // answerEl dùng để chèn thời gian suy nghĩ trước khi trả lời
      answerEl = ui.answerEl;
    } else {
      // Chỉ có phần trả lời
      answerEl = document.createElement('div');
      // Mark for streamChat() so it can always find the correct target.
      answerEl.dataset.role = "assistant-answer";
      answerEl.className = 'text-sm text-zinc-100 whitespace-pre-wrap leading-relaxed';
      assistantBodyEl.appendChild(answerEl);
    }

    const dots = wrapper.querySelectorAll('.dot');
    let step = 0;
    thinkingInterval = setInterval(() => {
      dots.forEach((dot, i) => {
        if (i === step % 3) {
          dot.style.opacity = '1';
          dot.style.transform = 'scale(1.5)';
          dot.style.background = '#facc15';
        } else {
          dot.style.opacity = '0.4';
          dot.style.transform = 'scale(1)';
          dot.style.background = '#a1a1aa';
        }
      });
      step = (step + 1) % 3;
    }, 350);

    // IMPORTANT:
    // - For OSS model we want streamChat() to use our pre-created reasoningEls.
    // - Also avoid streamChat creating a new bubble by setting currentAssistantBody.
    currentAssistantBody = assistantBodyEl;

    const messages = [{ role: "user", content: prompt }];
    await streamChat({ model_id, messages, max_new_tokens, temperature });

    const thinkingMs = performance.now() - tThinkingStart;

    // Xong thì bỏ dots
    try { wrapper?.remove(); } catch {}

    // Kết thúc: hiển thị thời gian suy nghĩ ở đầu bubble,
    // rồi Show reasoning, rồi câu trả lời (layout đã đúng sẵn).
    prependThinkingTime(assistantBodyEl, thinkingMs);

    // Xong: auto-close Show reasoning.
    try {
      const details = assistantBodyEl?.querySelector("details");
      if (details) details.open = false;
    } catch {}
  } catch (e) {
    addBubble("assistant", `❌ Error: ${e.message || e}`);
    currentAssistantBody = null;
  } finally {
    if (thinkingInterval) clearInterval(thinkingInterval);
    currentAssistantBody = null;
    btnSend.disabled = false;
  }
});

(async function init() {
  const saved = getToken();
  if (tokenInput && saved) tokenInput.value = saved;

  resetConnectionUI();

  await refreshHealth();
  setInterval(refreshHealth, 3600000);
})();

// Thêm hàm escapeHtml để tránh lỗi XSS khi render analysis
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
