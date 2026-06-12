#!/usr/bin/env python3
"""
Zero-install web UI for the email tools.

Run:
    python3 app.py            # then open http://localhost:8000

Two tools in the browser:
  1. Generate  -- upload a contact CSV, map columns, choose patterns, download
                  the candidate emails to send to your verifier.
  2. Dedupe    -- upload the verifier's "Good Emails Only" export, see the
                  breakdown, download one trustworthy email per lead.

Uses only the Python standard library. Files are sent as text inside JSON, so
there is no multipart parsing and nothing is written to disk by the server --
downloads happen in your browser.
"""

import csv
import io
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import email_core

PORT = 8000


def parse_csv(text):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def to_csv(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj))

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        try:
            req = self._body()
            if self.path == "/api/inspect":
                return self._inspect(req)
            if self.path == "/api/generate":
                return self._generate(req)
            if self.path == "/api/dedupe":
                return self._dedupe(req)
            self._json(404, {"error": "unknown endpoint"})
        except Exception as e:  # surface a friendly message, not a traceback
            self._json(400, {"error": str(e)})

    def _inspect(self, req):
        header, rows = parse_csv(req.get("csv", ""))
        if not header:
            raise ValueError("That file looks empty or isn't a CSV.")
        self._json(200, {"header": header, "nrows": len(rows),
                         "guess": email_core.guess_columns(header)})

    def _generate(self, req):
        header, rows = parse_csv(req.get("csv", ""))
        if not header:
            raise ValueError("That file looks empty or isn't a CSV.")
        m = req["map"]
        enabled = req.get("patterns") or email_core.PATTERN_NAMES
        out_h, out_rows, stats = email_core.generate_candidates(
            header, rows, int(m["first"]), int(m["last"]), int(m["domain"]), enabled)
        self._json(200, {"stats": stats, "csv": to_csv(out_h, out_rows),
                         "filename": "candidate_emails.csv"})

    def _dedupe(self, req):
        header, rows = parse_csv(req.get("csv", ""))
        if not header:
            raise ValueError("That file looks empty or isn't a CSV.")
        m = req["map"]
        def opt(key):
            v = m.get(key)
            return int(v) if v not in (None, "") else None

        out_h, out_rows, other_h, other_rows, drop_h, drop_rows, stats = email_core.dedupe(
            header, rows, int(m["first"]), int(m["last"]),
            int(m["domain"]), int(m["email"]), opt("title"), opt("company"))
        self._json(200, {
            "stats": stats,
            "verified": {"csv": to_csv(out_h, out_rows), "filename": "verified_deduped.csv"},
            "other": {"csv": to_csv(other_h, other_rows), "filename": "verified_other_leads.csv"},
            "dropped": {"csv": to_csv(drop_h, drop_rows), "filename": "verified_dropped.csv"},
        })


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Email Tools</title>
<style>
  :root { --bg:#0f1115; --card:#171a21; --line:#2a2f3a; --fg:#e6e9ef; --mut:#9aa3b2;
          --acc:#5b8cff; --good:#3fb950; --warn:#d29922; --bad:#f85149; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         background:var(--bg); color:var(--fg); }
  header { padding:26px 24px 10px; }
  h1 { margin:0; font-size:20px; letter-spacing:.2px; }
  .sub { color:var(--mut); font-size:13px; margin-top:4px; }
  .tabs { display:flex; gap:8px; padding:14px 24px 0; }
  .tab { padding:9px 16px; border:1px solid var(--line); border-bottom:none;
         border-radius:9px 9px 0 0; cursor:pointer; color:var(--mut); background:transparent; }
  .tab.active { color:var(--fg); background:var(--card); border-color:var(--line); }
  main { padding:0 24px 60px; }
  .panel { display:none; background:var(--card); border:1px solid var(--line);
           border-radius:0 12px 12px 12px; padding:22px; max-width:880px; }
  .panel.active { display:block; }
  .drop { border:2px dashed var(--line); border-radius:12px; padding:30px; text-align:center;
          color:var(--mut); cursor:pointer; transition:.15s; }
  .drop.hl { border-color:var(--acc); color:var(--fg); background:#1b2030; }
  .drop b { color:var(--fg); }
  .row { display:flex; flex-wrap:wrap; gap:14px; margin:18px 0; }
  .fld { flex:1; min-width:170px; }
  label { display:block; font-size:12px; color:var(--mut); margin-bottom:5px; }
  select { width:100%; padding:8px; background:var(--bg); color:var(--fg);
           border:1px solid var(--line); border-radius:8px; }
  .pats { display:flex; flex-wrap:wrap; gap:10px 18px; margin:8px 0 4px; }
  .pat { display:flex; align-items:center; gap:6px; font-size:13px; color:var(--fg); }
  button.go { margin-top:10px; padding:11px 22px; border:none; border-radius:9px;
              background:var(--acc); color:#fff; font-weight:600; cursor:pointer; }
  button.go:disabled { opacity:.4; cursor:default; }
  .hint { color:var(--mut); font-size:12px; }
  .result { margin-top:22px; padding-top:18px; border-top:1px solid var(--line); display:none; }
  .result.show { display:block; }
  .stat { display:flex; gap:10px; align-items:baseline; }
  .big { font-size:30px; font-weight:700; }
  .pill { display:inline-block; padding:2px 9px; border-radius:20px; font-size:12px; margin-right:6px; }
  .pill.v { background:rgba(63,185,80,.15); color:var(--good); }
  .pill.h { background:rgba(91,140,255,.15); color:var(--acc); }
  .pill.l { background:rgba(210,153,34,.15); color:var(--warn); }
  table { border-collapse:collapse; margin:14px 0; font-size:13px; }
  td { padding:4px 14px 4px 0; color:var(--mut); }
  td.n { color:var(--fg); font-variant-numeric:tabular-nums; text-align:right; }
  .dl { display:inline-block; margin:10px 12px 0 0; padding:9px 16px; border-radius:8px;
        background:#1f2532; color:var(--fg); border:1px solid var(--line); cursor:pointer; }
  .dl:hover { border-color:var(--acc); }
  .err { color:var(--bad); margin-top:14px; display:none; }
  .err.show { display:block; }
  code { background:var(--bg); padding:1px 5px; border-radius:4px; }
</style>
</head>
<body>
<header>
  <h1>Email Tools</h1>
  <div class="sub">Generate candidate emails, then dedupe your verified sheet to one per lead.</div>
</header>
<div class="tabs">
  <div class="tab active" data-t="gen">1 · Generate combinations</div>
  <div class="tab" data-t="ded">2 · Dedupe verified sheet</div>
</div>
<main>
  <!-- GENERATE -->
  <section class="panel active" id="gen">
    <div class="drop" id="gen-drop"><b>Click to choose</b> or drop your contact CSV here</div>
    <div id="gen-cfg" style="display:none">
      <div class="row">
        <div class="fld"><label>First name column</label><select id="gen-first"></select></div>
        <div class="fld"><label>Last name column</label><select id="gen-last"></select></div>
        <div class="fld"><label>Company domain column</label><select id="gen-domain"></select></div>
      </div>
      <label>Patterns to generate</label>
      <div class="pats" id="gen-pats"></div>
      <button class="go" id="gen-go">Generate candidates</button>
      <span class="hint" id="gen-info"></span>
    </div>
    <div class="err" id="gen-err"></div>
    <div class="result" id="gen-res">
      <div class="stat"><span class="big" id="gen-count">0</span><span>candidate emails</span></div>
      <div class="hint" id="gen-detail"></div>
      <div id="gen-dls"></div>
    </div>
  </section>
  <!-- DEDUPE -->
  <section class="panel" id="ded">
    <div class="drop" id="ded-drop"><b>Click to choose</b> or drop your verified CSV here</div>
    <div id="ded-cfg" style="display:none">
      <div class="row">
        <div class="fld"><label>First name column</label><select id="ded-first"></select></div>
        <div class="fld"><label>Last name column</label><select id="ded-last"></select></div>
        <div class="fld"><label>Title column</label><select id="ded-title"></select></div>
        <div class="fld"><label>Company column</label><select id="ded-company"></select></div>
        <div class="fld"><label>Company domain column</label><select id="ded-domain"></select></div>
        <div class="fld"><label>Email column</label><select id="ded-email"></select></div>
      </div>
      <button class="go" id="ded-go">Dedupe to one per lead</button>
      <span class="hint" id="ded-info"></span>
    </div>
    <div class="err" id="ded-err"></div>
    <div class="result" id="ded-res">
      <div class="stat"><span class="big" id="ded-count">0</span><span>verified leads (clean send)</span></div>
      <div style="margin:12px 0">
        <span class="pill v" id="p-v"></span>
        <span class="pill h" id="p-h"></span>
        <span class="pill l" id="p-l"></span>
      </div>
      <table id="ded-table"></table>
      <div class="hint" id="ded-note"></div>
      <div id="ded-dls"></div>
    </div>
  </section>
</main>
<script>
const $ = s => document.querySelector(s);
const PATTERNS = ["first.last","firstlast","flast","f.last","first","firstl"];
const MAX_ROWS = 40000;  // verifier upload cap -- split bigger files into parts

function setupDrop(dropId, onText){
  const drop = $(dropId);
  const input = document.createElement("input");
  input.type = "file"; input.accept = ".csv,text/csv"; input.style.display = "none";
  document.body.appendChild(input);
  drop.onclick = () => input.click();
  input.onchange = () => input.files[0] && read(input.files[0]);
  drop.ondragover = e => { e.preventDefault(); drop.classList.add("hl"); };
  drop.ondragleave = () => drop.classList.remove("hl");
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove("hl");
                       e.dataTransfer.files[0] && read(e.dataTransfer.files[0]); };
  function read(file){
    const r = new FileReader();
    r.onload = () => onText(r.result, file.name);
    r.readAsText(file);
  }
}
function fillSelect(sel, header, chosen){
  sel.innerHTML = "";
  header.forEach((h,i) => {
    const o = document.createElement("option");
    o.value = i; o.textContent = h || ("column " + i);
    if (i === chosen) o.selected = true;
    sel.appendChild(o);
  });
}
async function post(url, payload){
  const r = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"},
                             body: JSON.stringify(payload)});
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || "Something went wrong.");
  return j;
}
function download(name, text){
  const blob = new Blob([text], {type:"text/csv"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  URL.revokeObjectURL(a.href);
}
function dlButton(label, name, text){
  const b = document.createElement("span");
  b.className = "dl"; b.textContent = label;
  b.onclick = () => download(name, text);
  return b;
}
// Split a CSV into parts of at most MAX_ROWS data rows, repeating the header in
// each. Fields here (names, domains, emails) never contain newlines, so a plain
// line split is safe.
function splitCsv(text, maxRows){
  const lines = text.split(/\r?\n/);
  const header = lines[0];
  const body = lines.slice(1).filter(l => l.length > 0);
  if (body.length <= maxRows) return [text];
  const parts = [];
  for (let i = 0; i < body.length; i += maxRows){
    parts.push([header, ...body.slice(i, i + maxRows)].join("\r\n") + "\r\n");
  }
  return parts;
}
// Add one download button, or one per part with a clear name when the file is
// over the row cap.
function addDownload(container, label, name, text){
  const parts = splitCsv(text, MAX_ROWS);
  if (parts.length === 1){
    container.appendChild(dlButton("⬇ " + label, name, text));
    return;
  }
  const base = name.replace(/\.csv$/i, "");
  parts.forEach((p, i) =>
    container.appendChild(dlButton(
      `⬇ ${label} — part ${i + 1}/${parts.length}`,
      `${base}_part${i + 1}_of_${parts.length}.csv`, p)));
}

// tabs
document.querySelectorAll(".tab").forEach(t => t.onclick = () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
  document.querySelectorAll(".panel").forEach(x => x.classList.remove("active"));
  t.classList.add("active"); $("#"+t.dataset.t).classList.add("active");
});

// ---- Generate ----
let genCsv = "";
$("#gen-pats").innerHTML = PATTERNS.map(p =>
  `<label class="pat"><input type="checkbox" value="${p}" checked> ${p}</label>`).join("");
setupDrop("#gen-drop", async (text, name) => {
  genCsv = text;
  $("#gen-err").classList.remove("show");
  try {
    const r = await post("/api/inspect", {csv:text});
    fillSelect($("#gen-first"), r.header, r.guess.first ?? 0);
    fillSelect($("#gen-last"), r.header, r.guess.last ?? 0);
    fillSelect($("#gen-domain"), r.header, r.guess.domain ?? 0);
    $("#gen-cfg").style.display = "block";
    $("#gen-info").textContent = `${name} · ${r.nrows} rows`;
    $("#gen-res").classList.remove("show");
  } catch(e){ showErr("#gen-err", e); }
});
$("#gen-go").onclick = async () => {
  const pats = [...document.querySelectorAll('#gen-pats input:checked')].map(c=>c.value);
  if (!pats.length) return showErr("#gen-err", new Error("Pick at least one pattern."));
  $("#gen-err").classList.remove("show");
  try {
    const r = await post("/api/generate", {csv:genCsv, patterns:pats, map:{
      first:$("#gen-first").value, last:$("#gen-last").value, domain:$("#gen-domain").value}});
    $("#gen-count").textContent = r.stats.candidates_written.toLocaleString();
    $("#gen-detail").textContent =
      `from ${r.stats.contacts_read.toLocaleString()} contacts · ${r.stats.blank_rows} had no usable name/domain`;
    const dls = $("#gen-dls"); dls.innerHTML = "";
    addDownload(dls, "Download candidate emails", r.filename, r.csv);
    $("#gen-res").classList.add("show");
  } catch(e){ showErr("#gen-err", e); }
};

// ---- Dedupe ----
let dedCsv = "";
setupDrop("#ded-drop", async (text, name) => {
  dedCsv = text;
  $("#ded-err").classList.remove("show");
  try {
    const r = await post("/api/inspect", {csv:text});
    fillSelect($("#ded-first"), r.header, r.guess.first ?? 0);
    fillSelect($("#ded-last"), r.header, r.guess.last ?? 0);
    fillSelect($("#ded-title"), r.header, r.guess.title ?? 0);
    fillSelect($("#ded-company"), r.header, r.guess.company ?? 0);
    fillSelect($("#ded-domain"), r.header, r.guess.domain ?? 0);
    fillSelect($("#ded-email"), r.header, r.guess.email ?? 0);
    $("#ded-cfg").style.display = "block";
    $("#ded-info").textContent = `${name} · ${r.nrows} rows`;
    $("#ded-res").classList.remove("show");
  } catch(e){ showErr("#ded-err", e); }
});
$("#ded-go").onclick = async () => {
  $("#ded-err").classList.remove("show");
  try {
    const r = await post("/api/dedupe", {csv:dedCsv, map:{
      first:$("#ded-first").value, last:$("#ded-last").value,
      title:$("#ded-title").value, company:$("#ded-company").value,
      domain:$("#ded-domain").value, email:$("#ded-email").value}});
    const s = r.stats;
    $("#ded-count").textContent = s.verified_out.toLocaleString();
    $("#p-v").textContent = `${s.confidence.verified} verified`;
    $("#p-h").textContent = `${s.confidence.high} high`;
    $("#p-l").textContent = `${s.confidence.low_catchall} low / catch-all`;
    $("#ded-table").innerHTML = `
      <tr><td>verified — clean send list</td><td class="n">${s.verified_out}</td></tr>
      <tr><td>other (real aliases / catch-all)</td><td class="n">${s.other_out}</td></tr>
      <tr><td>aliases set aside</td><td class="n">${s.dropped}</td></tr>`;
    $("#ded-note").textContent =
      `Order used: ${s.global_order.join(" › ")} · ${s.conventions} domains had a learned convention · ` +
      `${s.catchall_domains.length} catch-all domains excluded from the verified list.`;
    const dls = $("#ded-dls"); dls.innerHTML = "";
    addDownload(dls, "Download VERIFIED list (clean send)", r.verified.filename, r.verified.csv);
    addDownload(dls, "Download other leads (alias / catch-all)", r.other.filename, r.other.csv);
    addDownload(dls, "Download dropped aliases", r.dropped.filename, r.dropped.csv);
    $("#ded-res").classList.add("show");
  } catch(e){ showErr("#ded-err", e); }
};

function showErr(sel, e){ const el = $(sel); el.textContent = e.message; el.classList.add("show"); }
</script>
</body>
</html>"""


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Email Tools running at {url}  (Ctrl+C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
