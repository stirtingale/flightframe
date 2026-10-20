"""Settings page you open from your phone (http://flightframe.local)."""
import os
import re

import requests
from flask import Flask, jsonify, redirect, render_template_string, request, send_file

from . import config, wifi
from .display import PREVIEW_PATH
from .render import ACCENTS

NOMINATIM = "https://nominatim.openstreetmap.org/search"
COORDS = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


def create_app(worker):
    app = Flask(__name__)

    @app.get("/")
    def index():
        cfg = config.load()
        return render_template_string(PAGE, cfg=cfg, s=worker.snapshot(),
                                      accents=list(ACCENTS), wifi_ok=wifi.available(),
                                      saved=request.args.get("saved"))

    @app.post("/settings")
    def save_settings():
        cfg = config.load()
        f = request.form

        def num(name, cast=float, lo=None, hi=None):
            v = f.get(name, "").strip()
            if v == "":
                return
            try:
                v = cast(v)
            except ValueError:
                return
            if lo is not None:
                v = max(lo, v)
            if hi is not None:
                v = min(hi, v)
            cfg[name] = v

        cfg["label"] = f.get("label", "").strip()[:40]
        num("lat", float, -90, 90)
        num("lon", float, -180, 180)
        num("radius_km", float, 1, 100)
        num("max_altitude_ft", int, 0, 60000)
        num("min_refresh_seconds", int, 60, 3600)
        num("stats_refresh_minutes", int, 3, 120)
        for key, allowed in (("units", {"metric", "imperial"}),
                             ("orientation", {"landscape", "portrait"}),
                             ("accent", set(ACCENTS))):
            if f.get(key) in allowed:
                cfg[key] = f[key]
        cfg["show_plane"] = f.get("show_plane") == "1"
        cfg["flip"] = f.get("flip") == "1"
        for key in ("quiet_start", "quiet_end"):
            v = f.get(key, "").strip()
            cfg[key] = v if re.fullmatch(r"\d{2}:\d{2}", v) else ""
        config.save(cfg)
        worker.poke(force=True)
        return redirect("/?saved=1")

    @app.get("/api/geocode")
    def geocode():
        q = request.args.get("q", "").strip()
        m = COORDS.match(q)
        if m:
            return jsonify([{"name": q, "lat": float(m[1]), "lon": float(m[2])}])
        if len(q) < 3:
            return jsonify([])
        try:
            r = requests.get(NOMINATIM, params={"q": q, "format": "jsonv2", "limit": 5},
                             headers={"User-Agent": "flightframe-pi/1.0"}, timeout=10)
            r.raise_for_status()
            return jsonify([{"name": x["display_name"], "lat": float(x["lat"]),
                             "lon": float(x["lon"])} for x in r.json()])
        except Exception as e:
            return jsonify({"error": str(e)}), 502

    @app.get("/api/status")
    def status():
        return jsonify(worker.snapshot())

    @app.post("/refresh")
    def refresh():
        worker.poke(force=True)
        return redirect("/")

    @app.get("/screen.png")
    def screen():
        if not os.path.exists(PREVIEW_PATH):
            return "", 404
        resp = send_file(PREVIEW_PATH, mimetype="image/png")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/api/wifi")
    def wifi_list():
        return jsonify(wifi.scan())

    @app.post("/wifi")
    def wifi_join():
        ssid = request.form.get("ssid", "").strip()
        if not ssid:
            return redirect("/")
        worker.join_wifi(ssid, request.form.get("password", ""))
        return render_template_string(JOINING, ssid=ssid)

    # Phones probe these when joining a hotspot; send them to the settings page.
    @app.get("/generate_204")
    @app.get("/hotspot-detect.html")
    @app.get("/ncsi.txt")
    @app.get("/connecttest.txt")
    def captive():
        return redirect("/")

    return app


JOINING = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Joining Wi-Fi</title>
<style>body{font:17px/1.45 system-ui,-apple-system,sans-serif;margin:0;padding:32px 20px;max-width:520px}
h1{font-size:28px;margin:0 0 12px}</style>
<h1>Joining {{ ssid }}</h1>
<p>Your phone will drop off the setup network now. That's expected.</p>
<p>Watch the frame. If it connects you'll see either your sky or a prompt to set your
location, with the address to open next. If the password was wrong, the setup screen comes back
and you can try again.</p>"""

PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Flight frame</title>
<style>
:root{--ink:#111;--muted:#6b6b6b;--line:#e4e2dd;--bg:#faf9f6;--card:#fff;--accent:#e33b22}
@media (prefers-color-scheme:dark){:root{--ink:#f2f0eb;--muted:#a19d96;--line:#33312d;--bg:#161513;--card:#1f1e1b}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:560px;margin:0 auto;padding:20px 16px 64px}
header{display:flex;justify-content:space-between;align-items:baseline;margin:6px 0 18px}
h1{font-size:26px;letter-spacing:-.02em;margin:0}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 12px}
.status{font-size:14px;color:var(--muted)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--accent);margin-right:6px;vertical-align:1px}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:14px}
.screen{width:100%;border-radius:6px;border:1px solid var(--line);background:#fff;display:block}
.screen.portrait{max-width:300px;margin:0 auto}
label{display:block;font-size:14px;font-weight:600;margin:14px 0 6px}
label:first-of-type{margin-top:0}
.hint{font-weight:400;color:var(--muted);font-size:13px}
input,select{width:100%;font:inherit;color:inherit;background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:11px 12px}
input:focus,select:focus{outline:2px solid var(--accent);outline-offset:-1px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.row label{margin-top:14px}
button{font:inherit;font-weight:600;border:0;border-radius:10px;padding:13px 16px;width:100%;background:var(--ink);color:var(--bg);cursor:pointer}
button.ghost{background:transparent;color:var(--ink);border:1px solid var(--line)}
.results{list-style:none;margin:8px 0 0;padding:0}
.results li{padding:10px 12px;border:1px solid var(--line);border-radius:10px;margin-top:6px;font-size:14px;cursor:pointer}
.results li:active{background:var(--line)}
.picked{font-size:14px;color:var(--muted);margin-top:8px}
.swatches{display:flex;gap:10px}
.swatches input{display:none}
.swatches span{display:block;width:38px;height:38px;border-radius:50%;border:3px solid transparent;cursor:pointer}
.swatches input:checked+span{border-color:var(--ink)}
.seg{display:flex;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.seg label{flex:1;margin:0;font-weight:500;text-align:center}
.seg input{display:none}
.seg span{display:block;padding:10px 6px;cursor:pointer}
.seg input:checked+span{background:var(--ink);color:var(--bg)}
.toast{background:var(--ink);color:var(--bg);padding:10px 14px;border-radius:10px;margin-bottom:14px;font-size:14px}
.nets li{display:flex;justify-content:space-between}
.stack>*+*{margin-top:10px}
.sources{list-style:none;margin:0;padding:0}
.sources li{padding:8px 0;border-top:1px solid var(--line);font-size:14px;display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}
.sources li:first-child{border-top:0}
.pill{font-size:12px;font-weight:600;padding:2px 8px;border-radius:99px;background:var(--line)}
.pill.ok{background:#d8f0dd;color:#185c2a}.pill.paused{background:#fbecc8;color:#6b4a00}.pill.failing{background:#f8d7d3;color:#8a1c12}
@media (prefers-color-scheme:dark){.pill.ok{background:#1f3b26;color:#9fe0ae}.pill.paused{background:#3f3416;color:#f3d48a}.pill.failing{background:#4a1f1b;color:#f4a79e}}
a{color:inherit}
</style></head>
<body><main>
<header><h1>Your sky</h1><span class="status" id="status"></span></header>

{% if saved %}<div class="toast">Saved. The frame will refresh in a moment (E Ink takes about 20 seconds).</div>{% endif %}

{% if s.setup_mode %}
<section>
  <h2>Wi-Fi</h2>
  <p style="margin-top:0">Pick your home network. Your phone will disconnect from the setup network once the frame switches over.</p>
  <ul class="results nets" id="nets"><li>Looking for networks…</li></ul>
  <form method="post" action="/wifi" class="stack" style="margin-top:12px">
    <input name="ssid" id="ssid" placeholder="Network name" required>
    <input name="password" type="password" placeholder="Password" autocomplete="current-password">
    <button>Connect</button>
  </form>
</section>
{% endif %}

<section>
  <h2>On the frame</h2>
  <img class="screen {{ cfg.orientation }}" src="/screen.png" id="shot" alt="Current screen"
       onerror="this.replaceWith(Object.assign(document.createElement('p'),{textContent:'Nothing drawn yet.'}))">
  <form method="post" action="/refresh" style="margin-top:12px"><button class="ghost">Refresh now</button></form>
</section>

<section>
  <h2>Flight data</h2>
  {% if s.offline_since %}<p style="margin-top:0">No data since {{ s.offline_since }}. The frame keeps trying by itself.</p>{% endif %}
  <ul class="sources">
  {% for src in s.sources %}
    <li><span class="pill {{ src.state }}">{{ {'ok':'Working','paused':'Paused','failing':'Not answering','standby':'Standby'}[src.state] }}</span>
      <strong>{{ src.name }}</strong>
      <span class="hint">{% if src.state == 'paused' %}{{ src.error }}{% if src.resumes %} (until {{ src.resumes }}){% endif %}{% elif src.state == 'failing' %}{{ src.error }}{% elif src.last_ok %}last answered {{ src.last_ok }}{% else %}used if the others are down{% endif %}</span></li>
  {% endfor %}
  </ul>
  <p class="hint" style="margin:10px 0 0">Aircraft positions from <a href="https://adsb.fi" target="_blank" rel="noopener">adsb.fi</a> and <a href="https://adsb.lol" target="_blank" rel="noopener">adsb.lol</a>, routes from <a href="https://www.adsbdb.com" target="_blank" rel="noopener">adsbdb</a>. Free community services for personal use.</p>
</section>

<form method="post" action="/settings">
<section>
  <h2>Location</h2>
  <label for="q">Search an address or postcode <span class="hint">or paste "lat, lon"</span></label>
  <input id="q" type="search" placeholder="e.g. BA1 1LT" autocomplete="off">
  <ul class="results" id="results"></ul>
  <div class="picked" id="picked">{% if cfg.lat is not none %}Set to {{ '%.4f'|format(cfg.lat) }}, {{ '%.4f'|format(cfg.lon) }}{% else %}No location yet{% endif %}</div>
  <input type="hidden" name="lat" id="lat" value="{{ cfg.lat if cfg.lat is not none else '' }}">
  <input type="hidden" name="lon" id="lon" value="{{ cfg.lon if cfg.lon is not none else '' }}">
  <label for="label">Name on the frame <span class="hint">optional</span></label>
  <input id="label" name="label" value="{{ cfg.label }}" placeholder="Home, Bath" maxlength="40">
  <label for="radius">Overhead means within <span class="hint">km</span></label>
  <input id="radius" name="radius_km" type="number" min="1" max="100" step="1" value="{{ cfg.radius_km|int }}">
  <label for="maxalt">Ignore aircraft above <span class="hint">feet, 0 for no limit</span></label>
  <input id="maxalt" name="max_altitude_ft" type="number" min="0" max="60000" step="1000" value="{{ cfg.max_altitude_ft }}">
</section>

<section>
  <h2>Look</h2>
  <label>Units</label>
  <div class="seg">
    <label><input type="radio" name="units" value="metric" {{ 'checked' if cfg.units=='metric' }}><span>Metric</span></label>
    <label><input type="radio" name="units" value="imperial" {{ 'checked' if cfg.units=='imperial' }}><span>Imperial</span></label>
  </div>
  <label>Orientation</label>
  <div class="seg">
    <label><input type="radio" name="orientation" value="landscape" {{ 'checked' if cfg.orientation=='landscape' }}><span>Landscape</span></label>
    <label><input type="radio" name="orientation" value="portrait" {{ 'checked' if cfg.orientation=='portrait' }}><span>Portrait</span></label>
  </div>
  <label>Mounted</label>
  <div class="seg">
    <label><input type="radio" name="flip" value="0" {{ 'checked' if not cfg.flip }}><span>Normal</span></label>
    <label><input type="radio" name="flip" value="1" {{ 'checked' if cfg.flip }}><span>Upside down</span></label>
  </div>
  <label>Aircraft drawing</label>
  <div class="seg">
    <label><input type="radio" name="show_plane" value="1" {{ 'checked' if cfg.show_plane }}><span>With airline logo</span></label>
    <label><input type="radio" name="show_plane" value="0" {{ 'checked' if not cfg.show_plane }}><span>Off</span></label>
  </div>
  <label>Accent colour</label>
  <div class="swatches">
    {% set hex = {'red':'#e8382a','blue':'#2a4fd6','green':'#2f9a4a','yellow':'#f2d13a'} %}
    {% for a in accents %}
    <label style="margin:0"><input type="radio" name="accent" value="{{ a }}" {{ 'checked' if cfg.accent==a }}><span style="background:{{ hex[a] }}" title="{{ a }}"></span></label>
    {% endfor %}
  </div>
</section>

<section>
  <h2>Refresh</h2>
  <div class="row">
    <div><label for="minr">New flight after <span class="hint">sec</span></label>
      <input id="minr" name="min_refresh_seconds" type="number" min="60" max="3600" value="{{ cfg.min_refresh_seconds }}"></div>
    <div><label for="stat">Update figures <span class="hint">min</span></label>
      <input id="stat" name="stats_refresh_minutes" type="number" min="3" max="120" value="{{ cfg.stats_refresh_minutes }}"></div>
  </div>
  <p class="hint" style="margin:8px 0 0">The colour E Ink panel takes about 20 seconds per refresh and wants at least 3 minutes between them.</p>
  <div class="row">
    <div><label for="qs">Quiet from</label><input id="qs" name="quiet_start" type="time" value="{{ cfg.quiet_start }}"></div>
    <div><label for="qe">until</label><input id="qe" name="quiet_end" type="time" value="{{ cfg.quiet_end }}"></div>
  </div>
</section>

<button>Save</button>
</form>
</main>
<script>
const $ = s => document.querySelector(s);
const labels = {flight:"Showing a flight", quiet:"Quiet skies", needs_location:"Needs a location",
  setup:"Wi-Fi setup", joining:"Joining Wi-Fi", quiet_hours:"Quiet hours", feed_error:"Waiting for flight data",
  starting:"Starting", online:"Online", offline:"Offline"};
async function status(){
  try{
    const s = await (await fetch('/api/status')).json();
    let t = labels[s.status] || s.status;
    if (s.flight) t = `${s.flight.flight}${s.flight.to ? ' to '+s.flight.to : ''}`;
    $('#status').innerHTML = '<span class="dot"></span>' + t.replace(/</g,'&lt;');
    if (s.last_render && s.last_render !== window._lr){ if (window._lr) $('#shot') && ($('#shot').src='/screen.png?'+Date.now()); window._lr = s.last_render; }
  }catch(e){}
}
status(); setInterval(status, 10000);

let timer;
$('#q').addEventListener('input', e => {
  clearTimeout(timer);
  const q = e.target.value.trim();
  if (q.length < 3){ $('#results').innerHTML=''; return; }
  timer = setTimeout(async () => {
    const r = await fetch('/api/geocode?q='+encodeURIComponent(q));
    const list = await r.json();
    const ul = $('#results'); ul.innerHTML='';
    (Array.isArray(list) ? list : []).forEach(p => {
      const li = document.createElement('li'); li.textContent = p.name;
      li.onclick = () => {
        $('#lat').value = p.lat.toFixed(5); $('#lon').value = p.lon.toFixed(5);
        $('#picked').textContent = 'Set to ' + p.lat.toFixed(4) + ', ' + p.lon.toFixed(4) + ' (save to apply)';
        if (!$('#label').value) $('#label').value = p.name.split(',').slice(0,2).join(',').trim().slice(0,40);
        ul.innerHTML=''; $('#q').value='';
      };
      ul.appendChild(li);
    });
    if (!ul.children.length) ul.innerHTML = '<li>No matches</li>';
  }, 400);
});

{% if s.setup_mode %}
fetch('/api/wifi').then(r=>r.json()).then(nets=>{
  const ul = $('#nets'); ul.innerHTML='';
  nets.forEach(n=>{
    const li=document.createElement('li');
    li.innerHTML = '<span></span><span class="hint"></span>';
    li.children[0].textContent = n.ssid; li.children[1].textContent = (n.secure?'Secured · ':'Open · ') + n.signal + '%';
    li.onclick = ()=>{ $('#ssid').value = n.ssid; document.querySelector('[name=password]').focus(); };
    ul.appendChild(li);
  });
  if(!nets.length) ul.innerHTML='<li>None found. Type the name below.</li>';
});
{% endif %}
</script>
</body></html>"""
