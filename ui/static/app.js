(() => {
  const urlsEl = document.getElementById("urls");
  const runBtn = document.getElementById("run");
  const browseBtn = document.getElementById("browse");
  const outputDirEl = document.getElementById("output-dir");
  const logEl = document.getElementById("log");
  const summaryEl = document.getElementById("summary");
  const progressLabel = document.getElementById("progress-label");

  const glyphs = {
    banner: "·",
    url: "▸",
    track: "○",
    step: "·",
    success: "✓",
    skip: "○",
    error: "✗",
    progress: "↓",
  };

  function setBusy(busy) {
    runBtn.disabled = busy || runBtn.dataset.ffmpegBlocked === "1";
    runBtn.classList.toggle("is-busy", busy);
    urlsEl.readOnly = busy;
    outputDirEl.readOnly = busy;
    browseBtn.disabled = busy;
  }

  function clearOutput() {
    logEl.replaceChildren();
    summaryEl.hidden = true;
    summaryEl.textContent = "";
    summaryEl.classList.remove("is-ok", "is-bad");
    progressLabel.textContent = "";
  }

  function appendLine(type, message) {
    const row = document.createElement("div");
    row.className = `log__line log__line--${type}`;

    const glyph = document.createElement("span");
    glyph.className = "log__glyph";
    glyph.textContent = glyphs[type] || "·";

    const text = document.createElement("span");
    text.textContent = message;

    row.append(glyph, text);
    logEl.append(row);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function handleEvent(event) {
    const type = event.type;
    if (type === "progress") {
      if (event.phase === "done") {
        progressLabel.textContent = "";
        return;
      }
      const total = event.total;
      const completed = event.completed || 0;
      if (total && total > 0) {
        const pct = Math.min(100, Math.round((completed / total) * 100));
        progressLabel.textContent = `${event.message} · ${pct}%`;
      } else {
        progressLabel.textContent = event.message || "";
      }
      return;
    }

    if (type === "summary") {
      summaryEl.hidden = false;
      const failed = event.failed || 0;
      summaryEl.classList.add(failed ? "is-bad" : "is-ok");
      summaryEl.innerHTML = `<strong>Done</strong> — ${event.message || "nothing to do"}`;
      progressLabel.textContent = "";
      return;
    }

    if (type === "track") {
      appendLine("track", `[${event.index}/${event.total}] ${event.message}`);
      return;
    }

    if (type === "banner") {
      appendLine("banner", event.message);
      return;
    }

    appendLine(type, event.message || "");
  }

  async function readSSE(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let splitAt;
      while ((splitAt = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, splitAt);
        buffer = buffer.slice(splitAt + 2);

        const lines = chunk.split("\n");
        let eventName = "message";
        const dataLines = [];
        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trim());
          }
        }

        if (eventName === "done") return;

        if (dataLines.length) {
          try {
            handleEvent(JSON.parse(dataLines.join("\n")));
          } catch {
            appendLine("error", "Could not parse a progress event.");
          }
        }
      }
    }
  }

  async function browseFolder() {
    browseBtn.disabled = true;
    try {
      const response = await fetch("/api/browse-folder", { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.ok) {
        clearOutput();
        appendLine("error", payload.error || "Could not open folder picker.");
        return;
      }
      if (payload.output_dir) {
        outputDirEl.value = payload.output_dir;
      }
    } catch (err) {
      clearOutput();
      appendLine("error", err?.message || "Could not open folder picker.");
    } finally {
      browseBtn.disabled = runBtn.classList.contains("is-busy");
    }
  }

  async function persistFolder() {
    const outputDir = outputDirEl.value.trim();
    if (!outputDir) return;
    try {
      const response = await fetch("/api/output-dir", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output_dir: outputDir }),
      });
      const payload = await response.json().catch(() => ({}));
      if (response.ok && payload.output_dir) {
        outputDirEl.value = payload.output_dir;
      }
    } catch {
      // Best-effort; download will re-validate the path.
    }
  }

  async function startRun() {
    const text = urlsEl.value.trim();
    const outputDir = outputDirEl.value.trim();
    if (!text) {
      clearOutput();
      appendLine("error", "Paste at least one YouTube video or playlist URL.");
      return;
    }
    if (!outputDir) {
      clearOutput();
      appendLine("error", "Choose a save folder.");
      return;
    }

    clearOutput();
    setBusy(true);

    try {
      const response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ urls: text, output_dir: outputDir }),
      });

      const contentType = response.headers.get("content-type") || "";
      if (!response.ok || contentType.includes("application/json")) {
        const payload = await response.json().catch(() => ({}));
        appendLine("error", payload.error || `Request failed (${response.status})`);
        return;
      }

      await readSSE(response);
    } catch (err) {
      appendLine("error", err?.message || "Could not reach the local server.");
    } finally {
      setBusy(false);
    }
  }

  if (!runBtn.disabled) {
    runBtn.dataset.ffmpegBlocked = "0";
  } else {
    runBtn.dataset.ffmpegBlocked = "1";
  }

  runBtn.addEventListener("click", startRun);
  browseBtn.addEventListener("click", browseFolder);
  outputDirEl.addEventListener("change", persistFolder);
  outputDirEl.addEventListener("blur", persistFolder);

  urlsEl.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      if (!runBtn.disabled) startRun();
    }
  });
})();
