const $ = (selector) => document.querySelector(selector);
const state = { threadId: null, temporary: false, messages: [], settings: {}, archived: false, sending: false, searchTimer: null, artifact: null, previewTab: "preview", previewWidth: "desktop", previewFile: "", uploaded: null, lastTask: null, abortController: null, recognition: null, selectedSkillIds: [] };

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}
function markdown(value) {
  if (window.marked && window.DOMPurify) return window.DOMPurify.sanitize(window.marked.parse(value || ""));
  return esc(value).replace(/\n/g, "<br>");
}
function highlightCode(source, language) {
  const commentPattern = /^(?:py|python|sh|bash)$/i.test(language) ? /#[^\n]*/g : /^(?:html|xml|svg)$/i.test(language) ? /<!--[\s\S]*?-->/g : /\/\*[\s\S]*?\*\/|\/\/[^\n]*/g;
  const tokens = new RegExp(`${commentPattern.source}|<\\/?[A-Za-z][^>]*>|"(?:\\\\.|[^"\\\\])*"|'(?:\\\\.|[^'\\\\])*'|\\b(?:async|await|const|let|var|function|return|if|else|for|while|class|new|import|export|from|def|print|true|false|null|None|try|catch|throw|public|private|static|void|int|str|flex|grid)\\b|\\b\\d+(?:\\.\\d+)?\\b`, "gi");
  let output = "", cursor = 0, match;
  while ((match = tokens.exec(source))) {
    output += esc(source.slice(cursor, match.index));
    const token = match[0];
    commentPattern.lastIndex = 0;
    const kind = commentPattern.test(token) ? "code-comment" : token.startsWith("<") ? "code-tag" : /^["'`]/.test(token) ? "code-string" : /^\d/.test(token) ? "code-number" : "code-keyword";
    commentPattern.lastIndex = 0;
    output += `<span class="${kind}">${esc(token)}</span>`;
    cursor = match.index + token.length;
  }
  return output + esc(source.slice(cursor));
}
function decorateCodeBlocks(container = $("#messages")) {
  container.querySelectorAll(".message-content pre").forEach((pre) => {
    if (pre.parentElement.classList.contains("code-block")) return;
    const code = pre.querySelector("code") || pre;
    const language = (code.className.match(/language-([\w+#.-]+)/i) || [])[1] || "text";
    const source = code.textContent || "";
    const wrapper = document.createElement("div"); wrapper.className = "code-block";
    const toolbar = document.createElement("div"); toolbar.className = "code-toolbar";
    const badge = document.createElement("span"); badge.className = "code-language"; badge.textContent = language.toUpperCase();
    const copy = document.createElement("button"); copy.type = "button"; copy.className = "code-copy"; copy.dataset.copyCode = ""; copy.textContent = "Copy";
    toolbar.append(badge, copy);
    pre.parentNode.insertBefore(wrapper, pre); wrapper.append(toolbar, pre);
    code.innerHTML = highlightCode(source, language);
    if (source.split("\n").length > 25) {
      const more = document.createElement("button"); more.type = "button"; more.className = "code-show-more"; more.textContent = "Show more";
      more.addEventListener("click", () => { const expanded = wrapper.classList.toggle("expanded"); more.textContent = expanded ? "Show less" : "Show more"; });
      wrapper.append(more);
    }
  });
}
function toast(message) {
  const element = $("#toast"); element.textContent = message; element.classList.add("show");
  window.clearTimeout(toast.timer); toast.timer = window.setTimeout(() => element.classList.remove("show"), 2600);
}
async function api(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch {}
    throw new Error(message);
  }
  const result = await response.json();
  if (path === "/api/settings" && options.method === "PUT") {
    try { localStorage.setItem("assistant.savedSettings", JSON.stringify(result)); } catch {}
  }
  return result;
}
function readCachedSettings() {
  try {
    const value = JSON.parse(localStorage.getItem("assistant.savedSettings") || "{}");
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch { return {}; }
}
function setMode(temporary) {
  state.temporary = temporary;
  $("#temporaryDot").classList.toggle("on", temporary);
  $("#temporaryChat").querySelector("span:nth-child(2)").textContent = temporary ? "Temporary chat · on" : "Temporary chat";
}
function renderWelcomeTitle() {
  const title = $("#welcomeTitle");
  const name = String(state.settings.preferred_name || "").trim();
  const fullText = name ? `Welcome Back, ${name}` : "Welcome Back";
  if (title.dataset.fullText === fullText) return;
  title.dataset.fullText = fullText;
  title.setAttribute("aria-label", fullText);
  if (state.welcomeTimer) clearInterval(state.welcomeTimer);
  title.classList.remove("is-typing");
  title.textContent = "";
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    title.textContent = fullText;
    return;
  }
  title.classList.add("is-typing");
  const characters = Array.from(fullText);
  let position = 0;
  state.welcomeTimer = window.setInterval(() => {
    title.textContent += characters[position++];
    if (position >= characters.length) {
      clearInterval(state.welcomeTimer);
      state.welcomeTimer = null;
      title.classList.remove("is-typing");
    }
  }, 42);
}
function showConversation() {
  const welcome = $("#welcome"), messages = $("#messages");
  const hasMessages = state.messages.length > 0;
  welcome.classList.toggle("hidden", hasMessages);
  if (!hasMessages) renderWelcomeTitle();
  const name = (state.settings.preferred_name || "").trim();
  $("#profileName").textContent = name || "Local workspace";
  $(".profile-avatar").textContent = (name || "L").charAt(0).toUpperCase();
  messages.classList.toggle("visible", hasMessages);
  messages.innerHTML = state.messages.map(messageMarkup).join("");
  decorateCodeBlocks(messages);
  scrollToBottom();
}
function messageMarkup(message, index = -1) {
  const user = message.role === "user";
  const author = user ? "You" : "Morrow";
  const previewCard = message.artifact ? `<div class="preview-card"><span>Preview opened: ${esc(message.artifact.entry || Object.keys(message.artifact.files || {}).find((name) => name.toLowerCase().endsWith(".html")) || "project.html")}</span><button type="button" data-open-preview="${index}">Open preview</button></div>` : "";
  return `<article class="message-row ${user ? "user" : "assistant"}" ${index >= 0 ? `data-index="${index}"` : ""}>
    <div class="message-avatar">${user ? "Z" : "M"}</div><div class="message-body"><div class="message-author">${author}${message.agent ? `<button type="button" class="agent-chip" data-agent-key="${esc(message.agentKey || "general")}" title="Use ${esc(message.agent)} for future messages">${esc(message.agent)}</button>` : ""}</div>
    <div class="message-content">${markdown(message.content || "")}</div>${previewCard}${message.pending ? '<div class="typing-indicator"><i></i><i></i><i></i></div>' : ""}</div></article>`;
}
function previewDocument(files) {
  const htmlName = Object.keys(files).find((name) => /\.html?$/i.test(name));
  if (!htmlName) return "";
  let source = files[htmlName];
  const base = htmlName.includes("/") ? htmlName.slice(0, htmlName.lastIndexOf("/") + 1) : "";
  const localFile = (url) => {
    const clean = url.split(/[?#]/)[0].replace(/^\.\//, "");
    if (/^(?:[a-z]+:|\/|\\\\)/i.test(clean)) return null;
    return files[base + clean] ?? files[clean] ?? null;
  };
  source = source.replace(/<link\b([^>]*?)href=["']([^"']+\.css(?:\?[^"']*)?)["']([^>]*)>/gi, (tag, before, url) => {
    const css = localFile(url); return css === null ? tag : `<style>${css.replace(/<\/style/gi, "<\\/style")}</style>`;
  });
  source = source.replace(/<script\b([^>]*?)src=["']([^"']+\.js(?:\?[^"']*)?)["']([^>]*)>\s*<\/script>/gi, (tag, before, url) => {
    const js = localFile(url); return js === null ? tag : `<script>${js.replace(/<\/script/gi, "<\\/script")}</script>`;
  });
  const csp = "default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'; frame-src 'none'";
  if (/<head(?:\s[^>]*)?>/i.test(source)) return source.replace(/<head(?:\s[^>]*)?>/i, (head) => `${head}<meta http-equiv="Content-Security-Policy" content="${csp}">`);
  return `<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="${csp}"></head><body>${source}</body></html>`;
}
function renderPreview() {
  const project = state.artifact; if (!project?.files) return;
  const files = project.files, names = Object.keys(files);
  if (!names.includes(state.previewFile)) state.previewFile = names.find((name) => name.toLowerCase() === "index.html") || names.find((name) => name.toLowerCase().endsWith(".html")) || names[0];
  const select = $("#previewFileSelect"); select.innerHTML = names.map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join(""); select.value = state.previewFile;
  $("#previewTitle").textContent = project.title || "Generated app";
  $("#previewFileLabel").textContent = `${names.length} file${names.length === 1 ? "" : "s"} · v${project.version || 1}`;
  $("#previewCodeFilename").textContent = state.previewFile;
  $("#previewLanguage").textContent = ({ html: "HTML", htm: "HTML", css: "CSS", js: "JavaScript", py: "Python", json: "JSON" })[state.previewFile.split(".").pop().toLowerCase()] || "Source";
  $("#previewCodeSource").textContent = files[state.previewFile] || "";
  $("#previewFrame").srcdoc = previewDocument(files);
  const versions = project.versions || [];
  $("#previewVersionWrap").hidden = versions.length < 2;
  $("#previewVersionSelect").innerHTML = versions.slice().reverse().map((item) => `<option value="${Number(item.version)}">Version ${Number(item.version)}${item.version === project.version ? " · current" : ""}</option>`).join("");
  $("#previewVersionSelect").value = String(project.version || versions.at(-1)?.version || 1);
  $("#previewStage").dataset.width = state.previewWidth;
  $("#previewFrame").hidden = state.previewTab !== "preview";
  $("#previewCodeView").hidden = state.previewTab !== "code";
  document.querySelectorAll("[data-preview-tab]").forEach((button) => { const active = button.dataset.previewTab === state.previewTab; button.classList.toggle("active", active); button.setAttribute("aria-selected", String(active)); });
  document.querySelectorAll("[data-preview-width]").forEach((button) => button.classList.toggle("active", button.dataset.previewWidth === state.previewWidth));
  $("#copyPreviewCode").hidden = state.previewTab !== "code";
  $("#downloadPreviewCode").hidden = state.previewTab !== "code";
}
function openPreview(project) {
  if (!project?.files) return;
  state.artifact = project; state.previewFile = "";
  $(".app-shell").classList.add("preview-open"); $("#previewPanel").setAttribute("aria-hidden", "false");
  renderPreview();
}
function closePreview() { $(".app-shell").classList.remove("preview-open"); $("#previewPanel").setAttribute("aria-hidden", "true"); }
function scrollToBottom() { const pane = $("#conversation"); requestAnimationFrame(() => { pane.scrollTop = pane.scrollHeight; }); }
function setTitle(title) {
  const safe = title && title !== "New chat" ? title : "New chat";
  $("#chatTitle").textContent = safe; $("#chatTitle").title = safe;
}
async function refreshChats() {
  const query = $("#searchChats").value.trim();
  try {
    const chats = await api(`/api/conversations?q=${encodeURIComponent(query)}&archived=${state.archived}`);
    const list = $("#chatList");
    if (!chats.length) { list.innerHTML = `<div class="list-empty">${query ? "No matching chats." : state.archived ? "No archived chats." : "Your saved chats will appear here."}</div>`; return; }
    const pinned = chats.filter((chat) => chat.pinned && !state.archived);
    const recent = chats.filter((chat) => !chat.pinned || state.archived);
    const renderGroup = (label, rows) => rows.length ? `<div class="chat-group-label">${label}</div>${rows.map((chat) => `<div class="chat-item ${chat.id === state.threadId ? "active" : ""}" data-chat-id="${esc(chat.id)}" title="${esc(chat.title)}"><span class="chat-item-title">${esc(chat.title || "New chat")}</span>${chat.pinned ? '<span class="chat-item-pin">✦</span>' : ""}<button class="chat-item-menu" data-menu-id="${esc(chat.id)}" aria-label="Chat options">•••</button></div>`).join("")}` : "";
    list.innerHTML = renderGroup("Pinned", pinned) + renderGroup(state.archived ? "Archived" : "Recent", recent);
  } catch (error) { $("#chatList").innerHTML = `<div class="list-empty">${esc(error.message)}</div>`; }
}
function selectedSkillsByChat() {
  try { const value = JSON.parse(localStorage.getItem("assistant.skillsByChat") || "{}"); return value && typeof value === "object" && !Array.isArray(value) ? value : {}; }
  catch { return {}; }
}
function loadSelectedSkills(threadId) { const value = selectedSkillsByChat()[threadId]; return Array.isArray(value) ? value.filter((id) => typeof id === "string") : []; }
function saveSelectedSkills() {
  if (!state.threadId) return;
  try { const all = selectedSkillsByChat(); all[state.threadId] = state.selectedSkillIds; localStorage.setItem("assistant.skillsByChat", JSON.stringify(all)); } catch {}
}
async function startChat(temporary = false) {
  try {
    const chat = await api("/api/conversations", { method: "POST", body: JSON.stringify({ temporary }) });
    state.threadId = chat.id; state.messages = []; state.artifact = null; state.selectedSkillIds = []; saveSelectedSkills(); closePreview(); setMode(temporary); setTitle(temporary ? "Temporary chat" : "New chat"); showConversation();
    if (temporary) sessionStorage.setItem("assistant.temporaryChat", chat.id); else sessionStorage.removeItem("assistant.temporaryChat");
    if (!temporary) localStorage.setItem("assistant.lastChat", chat.id);
    if (!temporary) await refreshChats();
    if (window.innerWidth <= 800) closeMobileSidebar();
    $("#messageInput").focus();
  } catch (error) { toast(error.message); }
}
async function openChat(threadId) {
  try {
    const chat = await api(`/api/conversations/${encodeURIComponent(threadId)}`);
    state.threadId = chat.id; state.messages = chat.messages || []; state.selectedSkillIds = loadSelectedSkills(chat.id); setMode(Boolean(chat.temporary)); setTitle(chat.title || "New chat");
    if (chat.temporary) sessionStorage.setItem("assistant.temporaryChat", chat.id); else { localStorage.setItem("assistant.lastChat", chat.id); sessionStorage.removeItem("assistant.temporaryChat"); }
    showConversation(); await refreshChats(); if (window.innerWidth <= 800) closeMobileSidebar();
    try { const project = await api(`/api/projects/${encodeURIComponent(threadId)}`); openPreview(project); } catch { state.artifact = null; closePreview(); }
  } catch (error) { toast(error.message); }
}
function openSettings() {
  $("#settingsBackdrop").classList.add("open"); $("#settingsBackdrop").setAttribute("aria-hidden", "false");
  $("#settingAgent").value = state.settings.agent || "Auto";
  $("#settingName").value = state.settings.preferred_name || "";
  $("#settingProvider").value = state.settings.provider || "Auto";
  $("#settingModel").value = state.settings.model || "Auto (provider default)";
  $("#settingTier").value = state.settings.model_tier || "Fast";
  $("#settingStyle").value = state.settings.response_style || "Normal";
  $("#settingLanguage").value = state.settings.language || "English";
  $("#settingInstructions").value = state.settings.custom_instructions || "";
  $("#settingTemperature").value = state.settings.temperature ?? 0.4;
  $("#settingStreaming").checked = state.settings.streaming !== false;
  $("#settingVoice").checked = state.settings.voice_responses === true;
  $("#settingMcpTools").checked = state.settings.mcp_tools_enabled === true;
  $("#settingMemory").checked = state.settings.memory_enabled !== false;
  $("#settingWebSearch").value = state.settings.web_search_mode || "Auto";
  $("#settingSearchProvider").value = state.settings.web_search_provider || "Auto";
}
function closeSettings() { $("#settingsBackdrop").classList.remove("open"); $("#settingsBackdrop").setAttribute("aria-hidden", "true"); }
async function saveSettings() {
  const values = { ...state.settings, preferred_name: $("#settingName").value.trim().slice(0, 60), custom_instructions: $("#settingInstructions").value.trim().slice(0, 4000), mcp_tools_enabled: $("#settingMcpTools").checked, agent: $("#settingAgent").value, provider: $("#settingProvider").value, model: $("#settingModel").value, model_tier: $("#settingTier").value, response_style: $("#settingStyle").value, language: $("#settingLanguage").value, temperature: Number($("#settingTemperature").value), streaming: $("#settingStreaming").checked, voice_responses: $("#settingVoice").checked, memory_enabled: $("#settingMemory").checked, web_search_mode: $("#settingWebSearch").value, web_search_provider: $("#settingSearchProvider").value };
  const button = $("#saveSettings");
  button.disabled = true; $("#settingsSaved").textContent = "Saving settings...";
  try { state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify({ settings: values }), keepalive: true }); updateAgentLabel(); showConversation(); $("#settingsSaved").textContent = "Saved just now"; toast("Settings saved"); }
  catch (error) { $("#settingsSaved").textContent = "Could not save settings"; toast(error.message); }
  finally { button.disabled = false; }
}
function updateAgentLabel() { const label = state.settings.agent || "Auto"; $("#agentLabel").textContent = label; }
function localReply(prompt, answer) { state.messages.push({ role: "user", content: prompt }, { role: "assistant", content: answer }); $("#messageInput").value = ""; showConversation(); }
function exportConversation() {
  const text = [`# ${state.title || "Conversation"}`, "", ...state.messages.map((item) => `${item.role === "user" ? "## You" : "## Assistant"}\n\n${item.content || ""}\n`)].join("\n");
  const link = document.createElement("a"), url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" })); link.href = url; link.download = "conversation.md"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function runSlashAction(command, argument, original) {
  const prompt = original.trim();
  const agents = { write: "Writing", research: "Research", code: "Code", analyze: "Math", summarize: "Writing" };
  if (agents[command]) { if (!argument.trim()) { $("#messageInput").value = `/${command} `; $("#messageInput").focus(); return true; } state.settings = { ...state.settings, agent: agents[command] }; await sendMessage(argument.trim()); return true; }
  if (command === "upload") { $("#fileInput").click(); return true; }
  if (command === "features" || command === "tools") { localReply(prompt, "**Tools and commands**\n\n`/write <prompt>` draft text · `/research <topic>` research · `/code <idea>` build software · `/analyze <data>` calculate · `/summarize <text>` summarize.\n\n`/upload` attach TXT, Markdown, or PDF. `/library`, `/library-add`, `/library-delete <id>` manage your private files. `/knowledge`, `/reload-knowledge` inspect or refresh local Markdown knowledge.\n\n`/new`, `/temporary`, `/history`, `/pinned`, `/find <words>`, `/resume <id>` manage chats. `/rename <title>`, `/pin`, `/unpin`, `/archive`, `/unarchive`, `/delete-chat`, `/clear-context`, `/export`, `/tasks` manage this chat.\n\n`/settings`, `/providers`, `/memory list|add|edit|delete|clear` manage preferences. Web search mode and provider are in Settings. Type `/` to browse."); return true; }
  if (command === "features" || command === "help") { localReply(prompt, "**Tools and commands**\n\n`/write <prompt>` draft text · `/research <topic>` research · `/code <idea>` build software · `/analyze <data>` calculate · `/summarize <text>` summarize.\n\n`/upload` attach TXT, Markdown, or PDF. `/library`, `/library-add`, `/library-delete <id>` manage your private files. `/knowledge`, `/reload-knowledge` inspect or refresh local Markdown knowledge.\n\n`/new`, `/temporary`, `/history`, `/find <words>` manage chats. `/rename <title>`, `/pin`, `/archive`, `/unarchive`, `/delete-chat`, `/clear-context`, `/export` manage this chat.\n\n`/settings`, `/providers`, `/memory list|add|edit|delete|clear` manage preferences. Web search mode and provider are in Settings. Type `/` to browse."); return true; }
  if (command === "new" || command === "temporary") { await startChat(command === "temporary"); return true; }
  if (command === "settings") { openSettings(); return true; }
  if (command === "tools" || command === "features") { localReply(prompt, "Type `/` to browse commands. Use `/help` to see what each command does."); return true; }
  if (command === "history" || command === "recent") { state.archived = argument.trim().toLowerCase() === "archived"; $("#toggleArchived").title = state.archived ? "Show recent chats" : "Show archived chats"; await refreshChats(); $("#chatList").scrollIntoView({ behavior: "smooth", block: "nearest" }); return true; }
  if (command === "find" || command === "search") { $("#searchChats").value = argument.trim(); await refreshChats(); $("#searchChats").focus(); return true; }
  if (command === "resume") { if (!argument.trim()) { localReply(prompt, "Use `/resume <chat-id>`. Find chat IDs with `/pinned` or `/find <words>`."); return true; } await openChat(argument.trim().replace(/[<>`]/g, "").split(/\s+/)[0]); return true; }
  if (command === "pinned") { const rows = await api("/api/conversations?q="); const pinned = rows.filter((item) => item.pinned && !item.archived); localReply(prompt, pinned.length ? `**Pinned chats**\n\n${pinned.map((item) => `- ${esc(item.title)} · ID ${item.id}`).join("\n")}\n\nOpen one with /resume <id>.` : "No pinned chats yet."); return true; }
  if (command === "tasks") { localReply(prompt, state.lastTask ? `**Latest task:** ${state.lastTask.status} · ${state.lastTask.summary}` : "No agent tasks have run in this chat yet."); return true; }
  if (command === "providers") { try { const status = await api("/api/providers/status"); localReply(prompt, `**Provider status**\n\nEligible: ${status.eligible?.join(", ") || "none configured"}.\nFree-only mode: ${status.free_only ? "on" : "off"}.\nLast served: ${status.last_served_provider || "not reported yet"}.`); } catch (error) { toast(error.message); } return true; }
  if (command === "knowledge" || command === "reload-knowledge") { try { const status = await api(command === "knowledge" ? "/api/knowledge/status" : "/api/knowledge/reload", command === "reload-knowledge" ? { method: "POST" } : {}); localReply(prompt, `**Local knowledge**\n\n${status.document_count ?? 0} Markdown files · ${status.chunk_count ?? 0} searchable sections${status.errors?.length ? `\n\nSome files could not be read: ${status.errors.join(", ")}` : ""}.`); } catch (error) { toast(error.message); } return true; }
  if (command === "library") { try { const docs = await api("/api/library"); localReply(prompt, docs.length ? `**Your Library**\n\n${docs.map((item) => `- **${esc(item.name)}** · ID ${item.id}`).join("\n")}\n\nUse /library-delete <id> to remove one.` : "Your private Library is empty. Attach a file and use `/library-add` to save it."); } catch (error) { toast(error.message); } return true; }
  if (command === "library-add") { if (!state.uploaded) { localReply(prompt, "Attach a document first, then run `/library-add`."); return true; } try { const result = await api("/api/library", { method: "POST", body: JSON.stringify({ name: state.uploaded.name, content: state.uploaded.text }) }); localReply(prompt, `Saved **${esc(state.uploaded.name)}** to your private Library (ID ${result.id}).`); state.uploaded = null; $("#uploadStatus").hidden = true; } catch (error) { toast(error.message); } return true; }
  if (command === "library-delete") { if (!/^\d+$/.test(argument.trim())) { localReply(prompt, "Use `/library-delete <id>`. Run `/library` to see IDs."); return true; } try { await api(`/api/library/${argument.trim()}`, { method: "DELETE" }); localReply(prompt, "Library document removed."); } catch (error) { toast(error.message); } return true; }
  if (command === "memory") {
    const [action = "list", ...parts] = argument.trim().split(/\s+/), value = parts.join(" ");
    try {
      if (action === "list") { const rows = await api("/api/memories"); localReply(prompt, rows.length ? `**Saved preferences**\n\n${rows.map((row) => `- ID ${row.id}: ${esc(row.content)}`).join("\n")}\n\nUse /memory add <preference>, /memory edit <id> <text>, or /memory delete <id>.` : "No saved preferences. Try `/memory add <preference>`."); }
      else if (action === "add") { if (!value) throw new Error("Use `/memory add <preference>`."); const row = await api("/api/memories", { method: "POST", body: JSON.stringify({ content: value }) }); localReply(prompt, `Saved preference ${row.id}.`); }
      else if (action === "edit") { const match = value.match(/^(\d+)\s+([\s\S]+)$/); if (!match) throw new Error("Use `/memory edit <id> <new text>`."); await api(`/api/memories/${match[1]}`, { method: "PATCH", body: JSON.stringify({ content: match[2] }) }); localReply(prompt, "Preference updated."); }
      else if (action === "delete") { if (!/^\d+$/.test(value)) throw new Error("Use `/memory delete <id>`."); await api(`/api/memories/${value}`, { method: "DELETE" }); localReply(prompt, "Preference deleted."); }
      else if (action === "clear" && confirm("Delete all saved preferences?")) { const result = await api("/api/memories", { method: "DELETE" }); localReply(prompt, `Deleted ${result.deleted} preferences.`); }
      else if (!['clear'].includes(action)) localReply(prompt, "Use `/memory list`, `add <preference>`, `edit <id> <text>`, `delete <id>`, or `clear`.");
    } catch (error) { localReply(prompt, `Couldn't update preferences: ${error.message}`); } return true;
  }
  if (["rename", "pin", "unpin", "archive", "unarchive", "delete-chat", "clear-context"].includes(command)) {
    if (!state.threadId || state.temporary) { localReply(prompt, "This action is available in a saved chat."); return true; }
    try {
      if (command === "rename") { const title = argument.trim() || window.prompt("New chat title:"); if (!title) return true; await api(`/api/conversations/${state.threadId}`, { method: "PATCH", body: JSON.stringify({ operation: "rename", title }) }); setTitle(title); await refreshChats(); }
      else if (["pin", "unpin", "archive", "unarchive"].includes(command)) { const chats = await api("/api/conversations?q="); const current = chats.find((chat) => chat.id === state.threadId); const operation = ["pin", "unpin"].includes(command) ? "pin" : "archive"; const enabled = command === "unarchive" ? false : command === "unpin" ? false : command === "pin" ? !current?.pinned : true; await api(`/api/conversations/${state.threadId}`, { method: "PATCH", body: JSON.stringify({ operation, enabled }) }); await refreshChats(); }
      else if (command === "delete-chat" && confirm("Delete this chat permanently?")) { await api(`/api/conversations/${state.threadId}`, { method: "DELETE" }); await startChat(false); }
      else if (command === "clear-context" && confirm("Clear this chat's saved messages?")) { await api(`/api/conversations/${state.threadId}/messages`, { method: "DELETE" }); state.messages = []; showConversation(); }
    } catch (error) { toast(error.message); } return true;
  }
  if (command === "export") { exportConversation(); return true; }
  return false;
}
async function sendMessage(text) {
  const slash = text.trim().match(/^\/([\w-]+)(?:\s+([\s\S]*))?$/);
  if (slash) {
    const [, command, argument = ""] = slash;
    if (await runSlashAction(command, argument, text)) return;
    if (command === "upload") { $("#fileInput").click(); return; }
    if (command === "features" || command === "help") {
      const content = command === "features" ? "**Features and commands**\n\n`/write` draft or polish text · `/research` research a topic · `/code` build software · `/analyze` work through numbers · `/summarize` summarize content.\n\nUse **Upload** or `/upload` for TXT, Markdown, or PDF files. Choose Web search mode and provider in Settings. Type `/` to browse these commands." : "Type `/` to browse commands. Use **Upload** or `/upload` to attach a TXT, Markdown, or PDF file. Open Settings to change your agent, provider, and web search.";
      state.messages.push({ role: "user", content: text.trim() }, { role: "assistant", content }); showConversation(); $("#messageInput").value = ""; return;
    }
    const agents = { write: "Writing", research: "Research", code: "Code", analyze: "Math", summarize: "Writing" };
    if (agents[command] && argument.trim()) { state.settings = { ...state.settings, agent: agents[command] }; text = argument.trim(); }
  }
  if (!text.trim() || state.sending) return;
  if (!state.threadId) await startChat(false);
  const content = text.trim(); state.messages.push({ role: "user", content }); state.messages.push({ role: "assistant", content: "", pending: true });
  state.lastTask = { status: "running", summary: content.slice(0, 120) };
  state.sending = true; $("#sendButton").disabled = true; $("#stopGeneration").hidden = false; $("#messageInput").value = ""; resizeComposer(); showConversation();
  const assistantIndex = state.messages.length - 1;
  try {
    const attachment = state.uploaded;
    state.abortController = new AbortController();
    const response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, signal: state.abortController.signal, body: JSON.stringify({ thread_id: state.threadId, message: content, uploaded_text: attachment?.text || "", uploaded_name: attachment?.name || "", settings: { ...state.settings, selected_skill_ids: state.selectedSkillIds } }) });
    if (!response.ok) { const detail = (await response.json()).detail || "The request failed."; throw new Error(detail); }
    const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = "";
    while (true) {
      const { value, done } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n"); buffer = blocks.pop() || "";
      for (const block of blocks) {
        const line = block.split("\n").find((part) => part.startsWith("data: ")); if (!line) continue;
        const event = JSON.parse(line.slice(6));
        if (event.type === "token") { state.messages[assistantIndex].content += event.value; state.messages[assistantIndex].pending = false; updateAssistant(assistantIndex); }
        else if (event.type === "status") { state.messages[assistantIndex].content = `_${event.value}_`; updateAssistant(assistantIndex); }
        else if (event.type === "done") { state.lastTask.status = "completed"; state.messages[assistantIndex].agent = event.value.agent; state.messages[assistantIndex].agentKey = event.value.agent_key; state.messages[assistantIndex].pending = false; state.messages[assistantIndex].content = state.messages[assistantIndex].content.replace(/^_[^\n]*_\n?/, ""); setTitle(event.value.title); if (attachment && state.uploaded === attachment) { state.uploaded = null; $("#uploadStatus").hidden = true; } if (event.value.artifact) { try { const project = await api(`/api/projects/${encodeURIComponent(state.threadId)}`); state.messages[assistantIndex].artifact = project; openPreview(project); } catch { toast("The project was saved, but the preview could not load"); } } updateAssistant(assistantIndex); await refreshChats(); if (state.settings.voice_responses && window.speechSynthesis && state.messages[assistantIndex].content) { window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance(state.messages[assistantIndex].content)); } }
        else if (event.type === "error") { state.lastTask.status = "failed"; state.messages[assistantIndex].content = `**I couldn't complete that request.**\n\n${event.value}`; state.messages[assistantIndex].pending = false; updateAssistant(assistantIndex); }
      }
    }
    if (!state.messages[assistantIndex].content) { state.messages[assistantIndex].content = "The assistant returned an empty response. Please try again."; state.messages[assistantIndex].pending = false; updateAssistant(assistantIndex); }
  } catch (error) { state.lastTask.status = "stopped"; state.messages[assistantIndex].content = error.name === "AbortError" ? (state.messages[assistantIndex].content || "Generation stopped.") : `**Something went wrong.**\n\n${error.message}`; state.messages[assistantIndex].pending = false; updateAssistant(assistantIndex); }
  finally { state.abortController = null; state.sending = false; $("#stopGeneration").hidden = true; $("#sendButton").disabled = false; $("#messageInput").focus(); }
}

function startVoiceInput() {
  const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
  const status = $("#recordingStatus");
  if (!Speech) { toast("Voice input is not supported in this browser. Try Chrome or Edge."); return; }
  if (state.recognition) { state.recognition.stop(); return; }
  const input = $("#messageInput"), originalText = input.value.trim();
  const recognition = new Speech(); state.recognition = recognition;
  recognition.lang = state.settings.language === "Urdu" ? "ur-PK" : state.settings.language === "Roman Urdu" ? "en-PK" : (navigator.language || "en-US");
  recognition.continuous = true; recognition.interimResults = true;
  status.hidden = false; status.textContent = "Listening...";
  $("#voiceInput").classList.add("recording"); $("#voiceInput").setAttribute("aria-label", "Stop voice input"); $("#voiceInput").setAttribute("aria-pressed", "true");
  recognition.onresult = (event) => {
    const transcript = Array.from(event.results).map((result) => result[0].transcript).join("").trim();
    input.value = [originalText, transcript].filter(Boolean).join(" "); resizeComposer();
  };
  recognition.onerror = (event) => {
    const messages = {
      "not-allowed": "Microphone permission was denied. Allow microphone access in your browser settings.",
      "service-not-allowed": "Your browser blocked its speech recognition service.",
      "audio-capture": "No microphone was found. Check that one is connected.",
      "no-speech": "No speech was detected. Tap the mic and try again.",
      network: "Speech recognition could not connect. Check your internet connection.",
    };
    if (event.error !== "aborted") toast(messages[event.error] || "Voice input could not start.");
  };
  recognition.onend = () => {
    state.recognition = null; status.hidden = true; $("#voiceInput").classList.remove("recording");
    $("#voiceInput").setAttribute("aria-label", "Start voice input"); $("#voiceInput").setAttribute("aria-pressed", "false"); input.focus();
  };
  try { recognition.start(); }
  catch { state.recognition = null; status.hidden = true; $("#voiceInput").classList.remove("recording"); $("#voiceInput").setAttribute("aria-label", "Start voice input"); $("#voiceInput").setAttribute("aria-pressed", "false"); toast("Voice input could not start."); }
}
function updateAssistant(index) {
  const row = $("#messages").querySelector(`[data-index="${index}"]`);
  const fresh = document.createElement("div"); fresh.innerHTML = messageMarkup(state.messages[index], index);
  if (row) { row.replaceWith(fresh.firstElementChild); decorateCodeBlocks($("#messages")); } else showConversation(); scrollToBottom();
}
function resizeComposer() { const input = $("#messageInput"); input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 180)}px`; }
const slashCommands = [
  ["Agents", "/write", "Draft and polish writing"], ["Agents", "/research", "Research a topic with web sources"], ["Agents", "/code", "Build or edit code and web apps"], ["Agents", "/analyze", "Analyze numbers or data"], ["Agents", "/summarize", "Summarize text or files"],
  ["Files & knowledge", "/upload", "Attach TXT, Markdown, or PDF"], ["Files & knowledge", "/library", "Browse your private document library"], ["Files & knowledge", "/library-add", "Save the attached file to your Library"], ["Files & knowledge", "/library-delete", "Remove a Library file by ID"], ["Files & knowledge", "/knowledge", "Check local Markdown knowledge"], ["Files & knowledge", "/reload-knowledge", "Reload local Markdown knowledge"],
  ["Chats", "/new", "Start a saved chat"], ["Chats", "/temporary", "Start a private temporary chat"], ["Chats", "/history", "Show recent or archived chats"], ["Chats", "/pinned", "List pinned chats and their IDs"], ["Chats", "/find", "Search saved chats"], ["Chats", "/resume", "Open a saved chat by ID"], ["Chats", "/rename", "Rename this chat"], ["Chats", "/pin", "Pin or unpin this chat"], ["Chats", "/unpin", "Unpin this chat"], ["Chats", "/archive", "Archive this chat"], ["Chats", "/unarchive", "Restore an archived chat"], ["Chats", "/delete-chat", "Delete this chat"], ["Chats", "/clear-context", "Clear this chat's saved messages"], ["Chats", "/export", "Download this conversation as Markdown"], ["Chats", "/tasks", "Show the latest task status"],
  ["Settings & help", "/settings", "Choose agent, model, web search, and preferences"], ["Settings & help", "/providers", "Show configured provider status"], ["Settings & help", "/memory", "View or manage saved preferences"], ["Settings & help", "/features", "Show all commands and features"], ["Settings & help", "/tools", "Show the command guide"], ["Settings & help", "/help", "Show quick help"],
];
let slashIndex = 0;
let lastSlashQuery = "";
function renderSlashMenu() {
  const input = $("#messageInput"), menu = $("#slashMenu"), beforeCursor = input.value.slice(0, input.selectionStart);
  const match = beforeCursor.match(/(?:^|\s)(\/[^\s]*)$/);
  if (!match) { menu.hidden = true; return; }
  const query = match[1].toLowerCase();
  if (query !== lastSlashQuery) { slashIndex = 0; lastSlashQuery = query; }
  const options = slashCommands.filter(([, command]) => command.startsWith(query));
  if (!options.length) { menu.hidden = true; return; }
  slashIndex = Math.min(slashIndex, options.length - 1);
  let previousGroup = "";
  menu.innerHTML = options.map(([group, command, description], index) => `${group !== previousGroup ? `<div class="slash-group">${(previousGroup = group)}</div>` : ""}<button type="button" class="slash-option ${index === slashIndex ? "selected" : ""}" role="option" aria-selected="${index === slashIndex}" data-slash="${command}"><span class="slash-command">${command}</span><span class="slash-description">${description}</span></button>`).join("");
  menu.hidden = false;
}
function selectSlashCommand(command) { const menu = $("#slashMenu"); menu.hidden = true; if (command === "/upload") { $("#fileInput").click(); return; } const input = $("#messageInput"); input.value = `${command} `; input.focus(); resizeComposer(); }
async function uploadSelectedFile(file) {
  if (!file) return;
  const status = $("#uploadStatus"); status.hidden = false; status.classList.add("is-loading");
  if (file.size > 10 * 1024 * 1024) { status.textContent = "This file is over the 10 MB limit. Choose a smaller file."; status.classList.remove("is-loading"); return; }
  status.innerHTML = `<div class="upload-card"><span class="upload-file-icon">${esc(file.name.split(".").pop() || "FILE")}</span><span class="upload-file-meta"><strong>${esc(file.name)}</strong><small>Reading file · ${(file.size / 1024).toFixed(0)} KB</small></span></div><span class="upload-spinner" aria-label="Uploading"></span>`;
  try {
    const data = new FormData(); data.append("file", file);
    const response = await fetch("/api/upload", { method: "POST", body: data });
    const result = await response.json(); if (!response.ok) throw new Error(result.detail || "Upload failed.");
    state.uploaded = result; status.classList.remove("is-loading"); status.innerHTML = `<div class="upload-card"><span class="upload-file-icon">${esc(result.name.split(".").pop() || "FILE")}</span><span class="upload-file-meta"><strong>${esc(result.name)}</strong><small>${(result.size_bytes / 1024).toFixed(0)} KB · Ready to use${result.truncated ? " · text shortened to fit" : ""}</small></span></div><button type="button" class="upload-remove" id="removeUpload" aria-label="Remove attachment" title="Remove file">×</button>`;
    $("#messageInput").focus();
  } catch (error) { status.classList.remove("is-loading"); status.textContent = error.message; }
}
function openContextMenu(button, chatId) {
  document.querySelector(".context-menu")?.remove();
  const menu = document.createElement("div"); menu.className = "context-menu";
  menu.addEventListener("click", (event) => event.stopPropagation());
  const actions = state.archived ? [["Restore", "unarchive"], ["Delete", "delete"]] : [["Rename", "rename"], ["Pin / unpin", "pin"], ["Archive", "archive"], ["Delete", "delete"]];
  menu.innerHTML = actions.map(([label, operation]) => `<button class="${operation === "delete" ? "danger" : ""}" data-operation="${operation}">${label}</button>`).join("");
  button.closest(".chat-item").append(menu);
  menu.addEventListener("click", async (event) => {
    const operation = event.target.dataset.operation; if (!operation) return;
    try {
      if (operation === "delete") { if (!confirm("Delete this chat permanently?")) return; await api(`/api/conversations/${chatId}`, { method: "DELETE" }); if (state.threadId === chatId) await startChat(); }
      else if (operation === "rename") { const title = prompt("Rename chat"); if (title?.trim()) await api(`/api/conversations/${chatId}`, { method: "PATCH", body: JSON.stringify({ operation, title }) }); }
      else if (operation === "unarchive") await api(`/api/conversations/${chatId}`, { method: "PATCH", body: JSON.stringify({ operation: "archive", enabled: false }) });
      else if (operation === "pin") { const selected = (await api(`/api/conversations?q=`)).find((chat) => chat.id === chatId); await api(`/api/conversations/${chatId}`, { method: "PATCH", body: JSON.stringify({ operation: "pin", enabled: !selected?.pinned }) }); }
      else await api(`/api/conversations/${chatId}`, { method: "PATCH", body: JSON.stringify({ operation, enabled: true }) });
      await refreshChats();
    } catch (error) { toast(error.message); }
  });
  eventStop(button);
}
function eventStop(element) { element.addEventListener("click", (event) => event.stopPropagation(), { once: true }); }
function closeMobileSidebar() { $("#sidebar").classList.remove("mobile-open"); $("#sidebarBackdrop").classList.remove("open"); }

async function deleteAllChats() {
  if (!confirm("Permanently delete all saved chats? This cannot be undone.")) return;
  try { await api("/api/conversations", { method: "DELETE" }); state.threadId = null; localStorage.removeItem("assistant.lastChat"); await refreshChats(); closeSettings(); await startChat(true); toast("All chats deleted"); }
  catch (error) { toast(error.message); }
}
async function deleteAllMemory() {
  if (!confirm("Permanently delete all saved memory? This cannot be undone.")) return;
  try { await api("/api/memories", { method: "DELETE" }); toast("Saved memory deleted"); }
  catch (error) { toast(error.message); }
}

function trainingStatus(message) { $("#trainingStatus").textContent = message; }
async function refreshTraining() {
  try {
    const [documents, skills, examples, servers] = await Promise.all([api("/api/library"), api("/api/skills"), api("/api/training/examples"), api("/api/mcp")]);
    $("#knowledgeSources").innerHTML = documents.length ? documents.map((item) => `<div class="platform-item"><span><strong>${esc(item.name)}</strong><small>${new Date(item.updated_at).toLocaleDateString()}</small></span><button type="button" class="platform-danger" data-delete-library="${Number(item.id)}">Remove</button></div>`).join("") : '<p class="platform-empty">No saved knowledge sources yet.</p>';
    $("#skillList").innerHTML = skills.length ? skills.map((item) => `<div class="platform-item"><span><strong>${esc(item.name)}</strong><small>${esc(item.description)} · ${item.enabled ? "Enabled" : "Disabled"}</small></span><div class="platform-item-actions"><label class="platform-toggle"><input type="checkbox" data-skill-selected="${esc(item.id)}" ${state.selectedSkillIds.includes(item.id) ? "checked" : ""}/> Select for this chat</label><label class="platform-toggle"><input type="checkbox" data-skill-enabled="${esc(item.id)}" ${item.enabled ? "checked" : ""}/> Enabled</label><button type="button" class="platform-button" data-edit-skill="${esc(item.id)}">Edit</button><button type="button" class="platform-danger" data-delete-skill="${esc(item.id)}">Remove</button></div></div>`).join("") : '<p class="platform-empty">No installed skills.</p>';
    $("#exampleList").innerHTML = examples.length ? examples.map((item) => `<div class="platform-item"><span><strong>${esc(item.question)}</strong><small>${esc(item.category || "General")} · ${item.enabled ? "Enabled" : "Disabled"}</small></span><div class="platform-item-actions"><button type="button" class="platform-button" data-edit-example="${esc(item.id)}">Edit</button><label class="platform-toggle"><input type="checkbox" data-example-enabled="${esc(item.id)}" ${item.enabled ? "checked" : ""}/> Use</label><button type="button" class="platform-danger" data-delete-example="${esc(item.id)}">Remove</button></div></div>`).join("") : '<p class="platform-empty">No training examples yet.</p>';
    $("#mcpList").innerHTML = servers.length ? servers.map((item) => `<div class="platform-item platform-item-column"><div class="platform-item"><span><strong>${esc(item.name)}</strong><small>${esc(item.url)} · ${esc(item.last_status || "Not tested")}</small>${item.last_error ? `<small class="platform-error">${esc(item.last_error)}</small>` : ""}</span><div class="platform-item-actions"><button type="button" class="platform-button" data-test-mcp="${esc(item.id)}">Test</button><label class="platform-toggle"><input type="checkbox" data-mcp-enabled="${esc(item.id)}" ${item.enabled ? "checked" : ""}/> Allow tools</label><button type="button" class="platform-danger" data-delete-mcp="${esc(item.id)}">Remove</button></div></div>${item.tools?.length ? `<ul class="mcp-tool-list">${item.tools.map((tool) => `<li><strong>${esc(tool.name)}</strong> — ${esc(tool.description)}</li>`).join("")}</ul>` : ""}</div>`).join("") : '<p class="platform-empty">No MCP servers configured.</p>';
  } catch (error) { trainingStatus(error.message); }
}
async function openTraining() {
  $("#trainingBackdrop").classList.add("open"); $("#trainingBackdrop").setAttribute("aria-hidden", "false");
  trainingStatus(""); await refreshTraining();
}
function closeTraining() { $("#trainingBackdrop").classList.remove("open"); $("#trainingBackdrop").setAttribute("aria-hidden", "true"); }
async function platformAction(action, success) {
  try { await action(); await refreshTraining(); trainingStatus(success); return true; }
  catch (error) { trainingStatus(error.message); return false; }
}
async function addKnowledgeFile(file) {
  const data = new FormData(); data.append("file", file);
  const response = await fetch("/api/upload", { method: "POST", body: data, cache: "no-store" });
  const result = await response.json(); if (!response.ok) throw new Error(result.detail || "Could not read that file.");
  await api("/api/library", { method: "POST", body: JSON.stringify({ name: result.name, content: result.text }) });
}
async function handleTrainingClick(event) {
  const button = event.target.closest("button"); if (!button) return;
  if (button.dataset.deleteLibrary) return platformAction(() => api(`/api/library/${button.dataset.deleteLibrary}`, { method: "DELETE" }), "Knowledge source removed.");
  if (button.dataset.deleteSkill) return platformAction(() => api(`/api/skills/${encodeURIComponent(button.dataset.deleteSkill)}`, { method: "DELETE" }), "Skill removed.");
  if (button.dataset.editSkill) {
    const item = await api(`/api/skills/${encodeURIComponent(button.dataset.editSkill)}/detail`);
    $("#skillEditId").value = item.id; $("#skillEditName").value = item.name; $("#skillEditDescription").value = item.description || ""; $("#skillEditInstructions").value = item.instructions || "";
    $("#skillEditForm").hidden = false; $("#skillEditForm").scrollIntoView({ behavior: "smooth", block: "center" }); return;
  }
  if (button.dataset.deleteExample) return platformAction(() => api(`/api/training/examples/${encodeURIComponent(button.dataset.deleteExample)}`, { method: "DELETE" }), "Training example removed.");
  if (button.dataset.deleteMcp) return platformAction(() => api(`/api/mcp/${encodeURIComponent(button.dataset.deleteMcp)}`, { method: "DELETE" }), "MCP server removed.");
  if (button.dataset.testMcp) return platformAction(() => api(`/api/mcp/${encodeURIComponent(button.dataset.testMcp)}/test`, { method: "POST" }), "MCP server connected; review its tools, then allow them if appropriate.");
  if (button.dataset.editExample) {
    const examples = await api("/api/training/examples"), item = examples.find((row) => row.id === button.dataset.editExample); if (!item) return;
    const question = prompt("Edit user question", item.question); if (question === null) return;
    const answer = prompt("Edit preferred answer", item.expected_answer); if (answer === null) return;
    return platformAction(() => api(`/api/training/examples/${encodeURIComponent(item.id)}`, { method: "PUT", body: JSON.stringify({ question, expected_answer: answer, category: item.category || "General", explanation: item.explanation || "" }) }), "Training example updated.");
  }
}
async function handleTrainingChange(event) {
  const input = event.target;
  if (input.matches("[data-skill-selected]")) {
    const id = input.dataset.skillSelected;
    state.selectedSkillIds = input.checked ? [...new Set([...state.selectedSkillIds, id])] : state.selectedSkillIds.filter((item) => item !== id);
    saveSelectedSkills(); trainingStatus(input.checked ? "Skill selected for this conversation." : "Skill removed from this conversation."); return;
  }
  if (input.matches("[data-skill-enabled]")) return platformAction(() => api(`/api/skills/${encodeURIComponent(input.dataset.skillEnabled)}`, { method: "PATCH", body: JSON.stringify({ enabled: input.checked }) }), "Skill setting updated.");
  if (input.matches("[data-example-enabled]")) return platformAction(() => api(`/api/training/examples/${encodeURIComponent(input.dataset.exampleEnabled)}`, { method: "PATCH", body: JSON.stringify({ enabled: input.checked }) }), "Training example setting updated.");
  if (input.matches("[data-mcp-enabled]")) return platformAction(() => api(`/api/mcp/${encodeURIComponent(input.dataset.mcpEnabled)}`, { method: "PATCH", body: JSON.stringify({ enabled: input.checked }) }), input.checked ? "MCP tools enabled for chats." : "MCP tools disabled.");
}

async function init() {
  try {
    const [brand, savedSettings] = await Promise.all([api("/api/brand"), api("/api/settings")]);
    const storedKeys = savedSettings.__saved_keys || [];
    delete savedSettings.__saved_keys;
    state.settings = { ...savedSettings, ...readCachedSettings() };
    for (const key of storedKeys) state.settings[key] = savedSettings[key];
    $("#brandName").textContent = brand.name; document.title = brand.name; $("#welcomeDescription").textContent = brand.tagline; updateAgentLabel();
    for (const model of brand.models.slice(1)) { const option = document.createElement("option"); option.value = model; option.textContent = model; $("#settingModel").append(option); }
    for (const [provider, configured] of Object.entries(brand.providers)) { const option = $("#settingProvider").querySelector(`option[value="${provider}"]`); if (option && !configured) { option.disabled = true; option.textContent += " · not configured"; } }
    await refreshChats();
    const temporaryId = sessionStorage.getItem("assistant.temporaryChat");
    if (temporaryId) {
      try { await openChat(temporaryId); }
      catch { sessionStorage.removeItem("assistant.temporaryChat"); }
    }
    if (!state.threadId) {
      const lastChatId = localStorage.getItem("assistant.lastChat");
      if (lastChatId) {
        try { await openChat(lastChatId); }
        catch { localStorage.removeItem("assistant.lastChat"); showConversation(); }
      } else showConversation();
    }
  } catch (error) { toast(`Couldn't connect to the assistant: ${error.message}`); }

  $("#newChat").addEventListener("click", () => startChat(false));
  $("#temporaryChat").addEventListener("click", () => startChat(true));
  $("#openTraining").addEventListener("click", openTraining); $("#closeTraining").addEventListener("click", closeTraining);
  $("#trainingBackdrop").addEventListener("click", (event) => { if (event.target.id === "trainingBackdrop") closeTraining(); });
  $("#knowledgeSources").addEventListener("click", handleTrainingClick);
  $("#skillList").addEventListener("click", handleTrainingClick); $("#skillList").addEventListener("change", handleTrainingChange);
  $("#exampleList").addEventListener("click", handleTrainingClick); $("#exampleList").addEventListener("change", handleTrainingChange);
  $("#mcpList").addEventListener("click", handleTrainingClick); $("#mcpList").addEventListener("change", handleTrainingChange);
  $("#knowledgeUploadForm").addEventListener("submit", async (event) => { event.preventDefault(); const formNode = event.currentTarget, file = $("#knowledgeFile").files[0]; if (!file) return; if (await platformAction(() => addKnowledgeFile(file), "Knowledge source added to your searchable Library.")) formNode.reset(); });
  $("#knowledgeUrlForm").addEventListener("submit", async (event) => { event.preventDefault(); const formNode = event.currentTarget, url = $("#knowledgeUrl").value.trim(); if (await platformAction(() => api("/api/library/url", { method: "POST", body: JSON.stringify({ url }) }), "Website text added to your searchable Library.")) formNode.reset(); });
  $("#skillTextForm").addEventListener("submit", async (event) => { event.preventDefault(); const formNode = event.currentTarget, payload = { name: $("#skillName").value.trim(), description: $("#skillDescription").value.trim(), instructions: $("#skillInstructions").value }; if (await platformAction(() => api("/api/skills", { method: "POST", body: JSON.stringify(payload) }), "Skill installed and enabled.")) formNode.reset(); });
  $("#skillGithubForm").addEventListener("submit", async (event) => { event.preventDefault(); const formNode = event.currentTarget, url = $("#skillGithubUrl").value.trim(); if (await platformAction(() => api("/api/skills/import/github", { method: "POST", body: JSON.stringify({ url }) }), "Skill instructions imported and enabled. No repository scripts were run.")) formNode.reset(); });
  $("#skillEditForm").addEventListener("submit", async (event) => { event.preventDefault(); const formNode = event.currentTarget, id = $("#skillEditId").value, payload = { name: $("#skillEditName").value.trim(), description: $("#skillEditDescription").value.trim(), instructions: $("#skillEditInstructions").value }; if (await platformAction(() => api(`/api/skills/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(payload) }), "Skill updated.")) formNode.hidden = true; });
  $("#cancelSkillEdit").addEventListener("click", () => { $("#skillEditForm").reset(); $("#skillEditForm").hidden = true; });
  $("#skillZipForm").addEventListener("submit", async (event) => { event.preventDefault(); const formNode = event.currentTarget, file = $("#skillZip").files[0]; if (!file) return; const ok = await platformAction(async () => { const form = new FormData(); form.append("file", file); const response = await fetch("/api/skills/upload", { method: "POST", body: form, cache: "no-store" }); const result = await response.json(); if (!response.ok) throw new Error(result.detail || "Skill ZIP import failed."); }, "Skill package imported and enabled. Scripts remain inactive."); if (ok) formNode.reset(); });
  $("#exampleForm").addEventListener("submit", async (event) => { event.preventDefault(); const formNode = event.currentTarget, payload = { question: $("#exampleQuestion").value.trim(), expected_answer: $("#exampleAnswer").value.trim(), category: $("#exampleCategory").value.trim() || "General", explanation: "" }; if (await platformAction(() => api("/api/training/examples", { method: "POST", body: JSON.stringify(payload) }), "Training example saved.")) formNode.reset(); });
  $("#mcpForm").addEventListener("submit", async (event) => { event.preventDefault(); const formNode = event.currentTarget, payload = { name: $("#mcpName").value.trim(), url: $("#mcpUrl").value.trim(), token: $("#mcpToken").value }; if (await platformAction(() => api("/api/mcp", { method: "POST", body: JSON.stringify(payload) }), "Server saved disabled. Test it and explicitly allow its tools before use.")) formNode.reset(); });
  $("#temporaryChatTop").addEventListener("click", () => startChat(true));
  $("#voiceInput").addEventListener("click", startVoiceInput);
  $("#stopGeneration").addEventListener("click", () => state.abortController?.abort());
  $("#openSettings").addEventListener("click", openSettings); $("#closeSettings").addEventListener("click", closeSettings);
  $("#settingsBackdrop").addEventListener("click", (event) => { if (event.target.id === "settingsBackdrop") closeSettings(); });
  $("#saveSettings").addEventListener("click", saveSettings);
  $("#agentSelectButton").addEventListener("click", openSettings);
  $("#chatForm").addEventListener("submit", (event) => { event.preventDefault(); sendMessage($("#messageInput").value || (state.uploaded ? "Summarize and explain this uploaded file." : "")); });
  $("#messageInput").addEventListener("input", () => { resizeComposer(); renderSlashMenu(); });
  $("#messageInput").addEventListener("click", renderSlashMenu);
  $("#slashMenu").addEventListener("click", (event) => { const button = event.target.closest("[data-slash]"); if (button) selectSlashCommand(button.dataset.slash); });
  $("#attachFile").addEventListener("click", () => $("#fileInput").click());
  $("#fileInput").addEventListener("change", (event) => { uploadSelectedFile(event.target.files[0]); event.target.value = ""; });
  $("#uploadStatus").addEventListener("click", (event) => { if (event.target.id === "removeUpload") { state.uploaded = null; event.currentTarget.hidden = true; } });
  $("#messageInput").addEventListener("keydown", (event) => {
    const menu = $("#slashMenu"), options = [...menu.querySelectorAll("[data-slash]")];
    if (!menu.hidden && options.length && ["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); slashIndex = (slashIndex + (event.key === "ArrowDown" ? 1 : options.length - 1)) % options.length; renderSlashMenu(); menu.querySelectorAll("[data-slash]")[slashIndex]?.scrollIntoView({ block: "nearest" }); return; }
    if (!menu.hidden && options.length && event.key === "Enter" && !event.shiftKey) { event.preventDefault(); selectSlashCommand(options[slashIndex].dataset.slash); return; }
    if (event.key === "Escape") menu.hidden = true;
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("#chatForm").requestSubmit(); }
  });
  const composer = $("#chatForm");
  composer.addEventListener("dragenter", (event) => { if (event.dataTransfer?.types.includes("Files")) { event.preventDefault(); composer.classList.add("drag-over"); } });
  composer.addEventListener("dragover", (event) => { if (event.dataTransfer?.types.includes("Files")) { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; composer.classList.add("drag-over"); } });
  composer.addEventListener("dragleave", (event) => { if (!composer.contains(event.relatedTarget)) composer.classList.remove("drag-over"); });
  composer.addEventListener("drop", (event) => { if (event.dataTransfer?.files.length) { event.preventDefault(); composer.classList.remove("drag-over"); uploadSelectedFile(event.dataTransfer.files[0]); } });
  document.addEventListener("dragover", (event) => { if (event.dataTransfer?.types.includes("Files")) event.preventDefault(); });
  document.addEventListener("drop", (event) => { if (event.dataTransfer?.types.includes("Files")) event.preventDefault(); });
  $("#searchChats").addEventListener("input", () => { clearTimeout(state.searchTimer); state.searchTimer = setTimeout(refreshChats, 180); });
  $("#toggleArchived").addEventListener("click", () => { state.archived = !state.archived; $("#toggleArchived").title = state.archived ? "Show recent chats" : "Show archived chats"; refreshChats(); });
  $("#chatList").addEventListener("click", (event) => { const menuButton = event.target.closest("[data-menu-id]"); if (menuButton) { event.stopPropagation(); openContextMenu(menuButton, menuButton.dataset.menuId); return; } const item = event.target.closest("[data-chat-id]"); if (item) { state.threadId = item.dataset.chatId; localStorage.setItem("assistant.lastChat", state.threadId); openChat(state.threadId); } });
  $("#messages").addEventListener("click", (event) => { const button = event.target.closest("[data-copy]"); if (button) navigator.clipboard.writeText(state.messages[Number(button.dataset.copy)]?.content || "").then(() => toast("Copied to clipboard")); });
  $("#messages").addEventListener("click", async (event) => { const button = event.target.closest("[data-copy-code]"); if (!button) return; const source = button.closest(".code-block")?.querySelector("pre code")?.textContent || ""; try { await navigator.clipboard.writeText(source); button.textContent = "Copied"; setTimeout(() => { button.textContent = "Copy"; }, 1200); } catch { toast("Clipboard access is unavailable"); } });
  $("#messages").addEventListener("click", async (event) => { const chip = event.target.closest("[data-agent-key]"); if (!chip) return; const label = chip.textContent.trim(); const keyToLabel = { code: "Code", math: "Math", writing: "Writing", research: "Research", general: "General", agent1: "Agent 1", agent2: "Agent 2" }; try { state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify({ settings: { ...state.settings, agent: keyToLabel[chip.dataset.agentKey] || "General" } }) }); updateAgentLabel(); toast(`${label} selected for future messages`); } catch (error) { toast(error.message); } });
  $("#messages").addEventListener("click", (event) => { const button = event.target.closest("[data-open-preview]"); if (button) openPreview(state.messages[Number(button.dataset.openPreview)]?.artifact || state.artifact); });
  $("#closePreview").addEventListener("click", closePreview);
  $("#previewPanel").addEventListener("click", (event) => {
    const tab = event.target.closest("[data-preview-tab]"); if (tab) { state.previewTab = tab.dataset.previewTab; renderPreview(); return; }
    const width = event.target.closest("[data-preview-width]"); if (width) { state.previewWidth = width.dataset.previewWidth; renderPreview(); return; }
  });
  $("#previewFileSelect").addEventListener("change", (event) => { state.previewFile = event.target.value; renderPreview(); });
  $("#previewVersionSelect").addEventListener("change", async (event) => { try { const project = await api(`/api/projects/${encodeURIComponent(state.threadId)}/versions/${event.target.value}`); state.previewFile = ""; state.artifact = project; renderPreview(); } catch (error) { toast(error.message); } });
  $("#refreshPreview").addEventListener("click", () => { if (state.artifact) { const frame = $("#previewFrame"); frame.srcdoc = ""; requestAnimationFrame(() => { frame.srcdoc = previewDocument(state.artifact.files); }); } });
  $("#openPreviewTab").addEventListener("click", () => { if (state.threadId) window.open(`/api/preview/${encodeURIComponent(state.threadId)}`, "_blank", "noopener,noreferrer"); });
  $("#fullscreenPreview").addEventListener("click", async () => { try { if (document.fullscreenElement) await document.exitFullscreen(); else await $("#previewPanel").requestFullscreen(); } catch { toast("Fullscreen is unavailable in this browser"); } });
  $("#copyPreviewCode").addEventListener("click", async () => { try { await navigator.clipboard.writeText(state.artifact?.files?.[state.previewFile] || ""); toast("Source copied"); } catch { toast("Clipboard access is unavailable"); } });
  $("#downloadPreviewCode").addEventListener("click", () => { const source = state.artifact?.files?.[state.previewFile]; if (source === undefined) return; const link = document.createElement("a"); const url = URL.createObjectURL(new Blob([source], { type: "text/plain;charset=utf-8" })); link.href = url; link.download = state.previewFile.split("/").pop() || "source.txt"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
  $(".starter-grid").addEventListener("click", (event) => { const card = event.target.closest("[data-prompt]"); if (!card) return; $("#messageInput").value = card.dataset.prompt; resizeComposer(); $("#messageInput").focus(); });
  $("#menuToggle").addEventListener("click", () => {
    if (window.innerWidth <= 800) { $("#sidebar").classList.add("mobile-open"); $("#sidebarBackdrop").classList.add("open"); }
    else { const collapsed = $(".app-shell").classList.toggle("sidebar-collapsed"); $("#menuToggle").setAttribute("aria-label", collapsed ? "Show sidebar" : "Hide sidebar"); }
  });
  $("#deleteAllChats").addEventListener("click", deleteAllChats);
  $("#deleteAllMemory").addEventListener("click", deleteAllMemory);
  $("#closeSidebar").addEventListener("click", closeMobileSidebar); $("#sidebarBackdrop").addEventListener("click", closeMobileSidebar);
  document.addEventListener("click", (event) => { if (!event.target.closest(".chat-item")) document.querySelector(".context-menu")?.remove(); });
  document.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); startChat(false); } if (event.key === "Escape") closeSettings(); });
}

init();
