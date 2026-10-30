import { useEffect, useMemo, useRef, useState } from "react";
import { Code2, Copy, Download, Eye, RefreshCw, Save } from "lucide-react";
import { Button } from "@/components/ui/button";

const CSP = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'; frame-src 'none'">`;
const ERROR_BRIDGE = `<script>window.onerror=function(message){parent.postMessage({type:'generated-preview-error',message:String(message).slice(0,300)},'*')};window.onunhandledrejection=function(event){parent.postMessage({type:'generated-preview-error',message:String(event.reason||'Unhandled preview error').slice(0,300)},'*')};</script>`;

function makePreview(files) {
  let htmlName = Object.keys(files).find((name) => /\.html?$/i.test(name));
  if (!htmlName) return "";
  let source = files[htmlName];
  const base = htmlName.split("/").slice(0, -1).join("/");
  const localFile = (url) => {
    const clean = url.split(/[?#]/)[0].replace(/^\.\//, "");
    return files[base ? `${base}/${clean}` : clean];
  };
  source = source.replace(/<link\b([^>]*?)href=["']([^"']+\.css(?:\?[^"']*)?)["']([^>]*)>/gi, (tag, before, url, after) => {
    const css = localFile(url);
    return css === undefined ? tag : `<style>${css.replace(/<\/style/gi, "<\\/style")}</style>`;
  });
  source = source.replace(/<script\b([^>]*?)src=["']([^"']+\.js(?:\?[^"']*)?)["']([^>]*)>\s*<\/script>/gi, (tag, before, url, after) => {
    const js = localFile(url);
    return js === undefined ? tag : `<script>${js.replace(/<\/script/gi, "<\\/script")}</script>`;
  });
  if (/<head(?:\s[^>]*)?>/i.test(source)) return source.replace(/<head(?:\s[^>]*)?>/i, (head) => `${head}${CSP}${ERROR_BRIDGE}`);
  return `<!doctype html><html><head>${CSP}${ERROR_BRIDGE}<meta name="viewport" content="width=device-width, initial-scale=1"></head><body>${source}</body></html>`;
}

function download(name, content) {
  const link = document.createElement("a");
  const mime = { html: "text/html", htm: "text/html", css: "text/css", js: "text/javascript", jsx: "text/jsx", ts: "text/typescript", tsx: "text/tsx", py: "text/x-python", json: "application/json", md: "text/markdown" }[name.split(".").pop().toLowerCase()] || "text/plain";
  link.href = URL.createObjectURL(new Blob([content], { type: `${mime};charset=utf-8` }));
  link.download = name.split("/").pop() || "source.txt";
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

function highlighted(source) {
  const tokens = source.match(/<!--[\s\S]*?-->|\/\/[^\n]*|#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|<\/?[A-Za-z][^>]*>|\b(?:const|let|var|function|return|if|else|for|while|class|new|import|export|from|async|await|def|print|true|false|null|None|try|catch|throw)\b|\b\d+(?:\.\d+)?\b/g);
  if (!tokens) return source;
  const parts = [];
  let cursor = 0;
  for (const token of tokens) {
    const position = source.indexOf(token, cursor);
    if (position > cursor) parts.push(source.slice(cursor, position));
    const color = token.startsWith("<!--") || token.startsWith("//") || token.startsWith("#") ? "text-emerald-400" : token.startsWith("<") ? "text-sky-300" : /^[\"'`]/.test(token) ? "text-amber-300" : /^\d/.test(token) ? "text-violet-300" : "text-fuchsia-300";
    parts.push(<span key={`${position}-${token}`} className={color}>{token}</span>);
    cursor = position + token.length;
  }
  if (cursor < source.length) parts.push(source.slice(cursor));
  return parts;
}

export default function CodePreview() {
  const initialFiles = typeof props?.files === "object" && props.files ? props.files : (props?.code ? { "index.html": props.code } : {});
  const [files, setFiles] = useState(initialFiles);
  const [selected, setSelected] = useState(Object.keys(initialFiles)[0] || "");
  const [tab, setTab] = useState("preview");
  const [refresh, setRefresh] = useState(0);
  const [copied, setCopied] = useState(false);
  const [runtimeError, setRuntimeError] = useState("");
  const [saveState, setSaveState] = useState("");
  const frameRef = useRef(null);
  const preview = useMemo(() => makePreview(files), [files, refresh]);
  const webPreview = Object.keys(files).some((name) => /\.html?$/i.test(name));

  useEffect(() => {
    function receiveError(event) {
      if (event.source !== frameRef.current?.contentWindow || event.data?.type !== "generated-preview-error") return;
      setRuntimeError(String(event.data.message || "Preview error").slice(0, 300));
    }
    window.addEventListener("message", receiveError);
    return () => window.removeEventListener("message", receiveError);
  }, []);

  async function copySource() {
    try {
      await navigator.clipboard.writeText(files[selected] || "");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1300);
    } catch { setCopied(false); }
  }

  async function saveProject() {
    try {
      const result = await callAction({ name: "save_project_edits", payload: { files } });
      setSaveState(result?.success === false ? "Save failed" : "Saved");
      window.setTimeout(() => setSaveState(""), 1800);
    } catch { setSaveState("Save failed"); }
  }

  const tabs = [
    ...(webPreview ? [{ id: "preview", label: "Preview", icon: Eye }] : []),
    { id: "code", label: "Code", icon: Code2 },
  ];

  return (
    <section className="w-full overflow-hidden rounded-2xl border bg-card text-card-foreground shadow-sm">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{props?.title || "Generated project"}</div>
          <div className="text-xs text-muted-foreground">{Object.keys(files).length} source file{Object.keys(files).length === 1 ? "" : "s"} · sandboxed workspace</div>
        </div>
        <div className="flex items-center gap-1" role="tablist" aria-label="Generated project workspace">
          {tabs.map(({ id, label, icon: Icon }) => <Button key={id} size="sm" variant={tab === id ? "secondary" : "ghost"} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}><Icon className="mr-2 h-4 w-4" />{label}</Button>)}
        </div>
      </header>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
        <div className="flex min-w-0 flex-wrap gap-1" aria-label="Project files">
          {Object.keys(files).map((name) => <button key={name} type="button" onClick={() => setSelected(name)} className={`max-w-[220px] truncate rounded-lg px-3 py-1.5 text-xs ${selected === name ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:bg-background/70"}`}>{name}</button>)}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {tab === "code" && <>
            <Button size="sm" variant="ghost" onClick={copySource}><Copy className="mr-2 h-4 w-4" />{copied ? "Copied" : "Copy"}</Button>
            <Button size="sm" variant="ghost" onClick={() => download(selected, files[selected] || "")}><Download className="mr-2 h-4 w-4" />Download file</Button>
            <Button size="sm" variant="secondary" onClick={saveProject}><Save className="mr-2 h-4 w-4" />{saveState || "Save edits"}</Button>
          </>}
          {tab === "preview" && <Button size="sm" variant="ghost" onClick={() => { setRuntimeError(""); setRefresh((value) => value + 1); }}><RefreshCw className="mr-2 h-4 w-4" />Refresh preview</Button>}
        </div>
      </div>
      {tab === "preview" && webPreview ? (
        <iframe key={refresh} title="Isolated generated website preview" sandbox="allow-scripts" ref={frameRef} referrerPolicy="no-referrer" className="h-[min(76vh,840px)] min-h-[560px] w-full bg-white max-md:h-[65vh] max-md:min-h-[420px]" srcDoc={preview} />
      ) : (
        <div className="grid min-h-[min(58vh,560px)] grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(240px,0.85fr)]">
          <div className="min-w-0 border-b lg:border-b-0 lg:border-r">
            <div className="border-b px-4 py-2 text-xs text-muted-foreground">{selected} · syntax view and editable source</div>
            <pre className="m-0 max-h-56 overflow-auto rounded-none border-0 bg-[#111827] p-4 font-mono text-[13px] leading-6 text-slate-100"><code>{highlighted(files[selected] || "")}</code></pre>
            <textarea aria-label={`Edit ${selected}`} spellCheck="false" value={files[selected] || ""} onChange={(event) => setFiles((current) => ({ ...current, [selected]: event.target.value }))} className="min-h-[min(34vh,320px)] w-full resize-y border-t border-slate-700 bg-[#111827] p-4 font-mono text-[13px] leading-6 text-slate-100 outline-none" />
          </div>
          {webPreview ? <iframe title="Updated isolated generated website preview" sandbox="allow-scripts" ref={frameRef} referrerPolicy="no-referrer" className="h-[min(72vh,760px)] min-h-[520px] w-full bg-white max-md:h-[60vh] max-md:min-h-[400px]" srcDoc={preview} /> : <div className="flex items-center p-6 text-sm text-muted-foreground">No preview runtime is configured for this project type. Source editing and downloads are available.</div>}
        </div>
      )}
      {tab === "preview" && runtimeError && <div role="alert" className="border-t bg-destructive/10 px-4 py-3 text-sm text-destructive">Preview runtime error: {runtimeError}</div>}
      {tab === "code" && runtimeError && <div role="alert" className="border-t bg-destructive/10 px-4 py-3 text-sm text-destructive">Preview runtime error: {runtimeError}</div>}
    </section>
  );
}
