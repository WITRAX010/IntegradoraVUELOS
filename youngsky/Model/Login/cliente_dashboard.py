# cliente_dashboard.py
from flask import Blueprint, session, redirect, url_for, render_template_string, request, jsonify,flash
import os, time
try:
    import requests
except Exception:
    requests = None  # UI funciona aunque no haya requests instalado

# === DB (MySQL) para Reservas/Historial ===
import pymysql
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root")
DB_NAME = os.getenv("DB_NAME", "youngsky")
DB_PORT = int(os.getenv("DB_PORT", 3306))

def get_conn():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME,
        port=DB_PORT, cursorclass=pymysql.cursors.DictCursor, autocommit=True
    )

cliente_bp = Blueprint("cliente", __name__, url_prefix="/cliente")

# =========================
# AMADEUS (opcional)
# =========================
AMADEUS_API_KEY = "YzluQvDV69sa28AS8f6HQrMOWk1TIp51"
AMADEUS_API_SECRET = "fUaowqaKhPVThWFx"
AMADEUS_BASE = "https://test.api.amadeus.com"
_token_cache = {"access_token": None, "exp": 0}

def have_amadeus():
    return bool(AMADEUS_API_KEY and AMADEUS_API_SECRET and requests is not None)

def _get_amadeus_token():
    if _token_cache["access_token"] and time.time() < _token_cache["exp"] - 60:
        return _token_cache["access_token"]
    if not have_amadeus():
        raise RuntimeError("Faltan llaves de Amadeus o paquete 'requests'")
    url = f"{AMADEUS_BASE}/v1/security/oauth2/token"
    r = requests.post(url, data={
        "grant_type": "client_credentials",
        "client_id": AMADEUS_API_KEY,
        "client_secret": AMADEUS_API_SECRET
    }, timeout=20)
    r.raise_for_status()
    js = r.json()
    _token_cache["access_token"] = js["access_token"]
    _token_cache["exp"] = time.time() + int(js.get("expires_in", 1800))
    return _token_cache["access_token"]

def _amadeus_get(path, params):
    token = _get_amadeus_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{AMADEUS_BASE}{path}"
    r = requests.get(url, headers=headers, params=params, timeout=25)
    if r.status_code == 401:
        _token_cache["access_token"] = None
        headers["Authorization"] = f"Bearer {_get_amadeus_token()}"
        r = requests.get(url, headers=headers, params=params, timeout=25)
    r.raise_for_status()
    return r.json()

def _iso_duration_to_hm(iso):  # "PT8H30M" -> "8h 30m"
    if not iso or not iso.startswith("PT"):
        return iso or ""
    iso = iso[2:]
    h, m = 0, 0
    if "H" in iso:
        parts = iso.split("H")
        h = int(parts[0] or 0)
        iso = parts[1] if len(parts) > 1 else ""
    if "M" in iso:
        m = int(iso.split("M")[0] or 0)
    return (f"{h}h " if h else "") + (f"{m}m" if m else ("" if h else "0m"))

# =========================
# +++ NUEVO: helper de modo/fuente + imports para vista previa
# =========================
def _current_mode():
    mode = "DEMO"
    base = AMADEUS_BASE
    if requests is not None and AMADEUS_API_KEY and AMADEUS_API_SECRET:
        if "api.amadeus.com" in base:
            mode = "AMADEUS_PROD"
        elif "test.api.amadeus.com" in base:
            mode = "AMADEUS_TEST"
        else:
            mode = "AMADEUS_CUSTOM"
    return mode

import base64, json
from markupsafe import escape

# =========================
# HTML (cards + chips + filtro País→País + banner modo)
# =========================
html_cliente_dashboard = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ofertas de Vuelos</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css" rel="stylesheet">
  <style>
    body { margin:0; font-family:'Segoe UI',sans-serif; background:#fff; }
    .hero { background-image:url('https://josepesteveguia.com/wp-content/uploads/2022/12/alpinismo-ordesa-monteperdido.jpg');
            background-size:cover; background-position:center; color:white; text-align:center; padding:100px 20px 130px; }
    .nav-link, .navbar-brand, .btn { color:white !important; }
    .nav-link.active { background:#0a5b5e; border-radius:20px; padding:5px 15px; }

    .pillbar { max-width:1100px; margin:-60px auto 10px; display:flex; gap:8px; flex-wrap:wrap; justify-content:center; }
    .pillbar .btn { border-radius:20px; border:1px solid rgba(255,255,255,.4); background:rgba(0,0,0,.25); backdrop-filter: blur(4px); }
    .pillbar .btn.active { background:#0a5b5e; border-color:#0a5b5e; }

    .grid-wrap { max-width:1200px; margin: 20px auto; }
    .card-flight { border-radius:14px; box-shadow:0 12px 28px rgba(0,0,0,0.08); border:1px solid #eee; transition:transform .12s ease; }
    .card-flight:hover { transform: translateY(-2px); }
    .badge-stop { background:#0a5b5e; }
    .price { font-size:1.4rem; font-weight:700; }
    .airline { font-weight:600; }
    .skeleton { background:linear-gradient(90deg,#f0f0f0 25%,#f7f7f7 37%,#f0f0f0 63%); background-size:400% 100%; animation:shimmer 1.4s ease infinite; border-radius:10px; height:140px; }
    @keyframes shimmer { 0%{background-position:100% 0} 100%{background-position:0 0} }

    .main-footer { background:rgba(0,0,0,0.6); color:#ccc; padding:30px 20px; display:flex; flex-wrap:wrap; justify-content:space-between; font-size:14px; }
    .main-footer .footer-left, .main-footer .footer-column { flex:1; min-width:200px; margin-bottom:20px; }
    .main-footer ul { list-style:none; padding:0; margin:0; }
    .main-footer ul li { margin-bottom:5px; }
    footer.copyright { text-align:center; padding:10px; background:#111; color:#aaa; font-size:12px; }
  </style>
</head>
<body>

  <nav class="navbar navbar-expand-lg navbar-dark bg-dark px-4">
    <a class="navbar-brand" href="#">YoungSKY</a>
    <div class="collapse navbar-collapse">
      <ul class="navbar-nav me-auto mb-2 mb-lg-0">
        <li class="nav-item"><a class="nav-link active" href="/cliente/dashboard">✈ Vuelos</a></li>
        <li class="nav-item"><a class="nav-link" href="/cliente/reservas">🏨 Reservas</a></li>
        <li class="nav-item"><a class="nav-link" href="/cliente/historial">🧳 Historial</a></li>
      </ul>
      <div class="d-flex align-items-center">
        <button class="btn btn-outline-light" data-bs-toggle="modal" data-bs-target="#logoutModal">Cerrar sesión</button>
      </div>
    </div>
  </nav>

  <div class="hero">
    <h1 class="display-6 fw-bold">Ofertas destacadas para tus próximas vacaciones</h1>
    <p class="lead">Vuelos seleccionados desde Ciudad de México</p>
  </div>

  <!-- Chips + Toggle -->
  <div class="pillbar container">
    <button class="btn btn-sm text-white" data-pack="mex_pop">Populares 🇲🇽</button>
    <button class="btn btn-sm text-white" data-pack="usa">USA 🇺🇸</button>
    <button class="btn btn-sm text-white" data-pack="eu">Europa 🇪🇺</button>
    <button class="btn btn-sm text-white" data-pack="playa">Playa 🏝️</button>
    <button class="btn btn-sm text-white" data-pack="directos">Solo directos ✈️</button>

    <div class="btn-group ms-2" role="group" aria-label="Tipo de viaje">
      <button id="btnRound" class="btn btn-sm text-white active" data-trip="round">🔁 Redondos ★</button>
      <button id="btnOneWay" class="btn btn-sm text-white" data-trip="oneway">➡️ Sencillos</button>
    </div>
  </div>

  <!-- Banner modo -->
  <div id="modoBanner" class="container mt-2 d-none">
    <div id="modoAlert" class="alert alert-warning py-2 small mb-0">
      <span id="modoText"></span>
    </div>
  </div>

  <!-- Buscador País → País -->
  <div class="container mt-2">
    <div class="country-search d-flex flex-wrap gap-2 justify-content-center">
      <select id="countryFrom" class="form-select form-select-sm" style="max-width:220px">
        <option value="">País origen…</option>
        <option value="MX">México</option>
        <option value="US">Estados Unidos</option>
        <option value="CA">Canadá</option>
        <option value="ES">España</option>
        <option value="FR">Francia</option>
        <option value="GB">Reino Unido</option>
        <option value="DE">Alemania</option>
        <option value="IT">Italia</option>
        <option value="BR">Brasil</option>
        <option value="AR">Argentina</option>
        <option value="CO">Colombia</option>
        <option value="CL">Chile</option>
        <option value="PE">Perú</option>
        <option value="JP">Japón</option>
      </select>
      <span class="align-self-center">→</span>
      <select id="countryTo" class="form-select form-select-sm" style="max-width:220px">
        <option value="">País destino…</option>
        <option value="MX">México</option>
        <option value="US">Estados Unidos</option>
        <option value="CA">Canadá</option>
        <option value="ES">España</option>
        <option value="FR">Francia</option>
        <option value="GB">Reino Unido</option>
        <option value="DE">Alemania</option>
        <option value="IT">Italia</option>
        <option value="BR">Brasil</option>
        <option value="AR">Argentina</option>
        <option value="CO">Colombia</option>
        <option value="CL">Chile</option>
        <option value="PE">Perú</option>
        <option value="JP">Japón</option>
      </select>
      <button id="btnCountrySearch" class="btn btn-sm btn-dark">Buscar</button>
    </div>
  </div>

  <div class="container">
    <div id="boxEstado" class="alert d-none"></div>
  </div>

  <!-- Grid de tarjetas (skeleton inicial) -->
  <div class="grid-wrap container">
    <div id="resultados" class="row g-3">
      <div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>
      <div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>
      <div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>
      <div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>
      <div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>
      <div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>
      <div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>
      <div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>
      <div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>
      <div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>
      <div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>
      <div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>
    </div>
  </div>

  <div class="main-footer">
    <div class="footer-left">México · Español (MX) · MXN</div>
    <div class="footer-column"><ul><li>Ayuda</li><li>Configuración de privacidad</li><li>Iniciar sesión</li></ul></div>
    <div class="footer-column"><ul><li>Política de cookies</li><li>Política de privacidad</li><li>Términos de servicio</li><li>Información de la empresa</li></ul></div>
    <div class="footer-column"><ul><li>Explorar</li><li>Compañía</li><li>Partners</li><li>Viajes</li><li>Sitios internacionales</li></ul></div>
  </div>

  <footer class="copyright">© 2025 YoungSky – Tu aventura comienza aquí ✈️</footer>

  <!-- Modal salir -->
  <div class="modal fade" id="logoutModal" tabindex="-1" aria-labelledby="logoutModalLabel" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
      <div class="modal-content text-center">
        <div class="modal-header bg-danger text-white"><h5 class="modal-title" id="logoutModalLabel">¿Cerrar sesión?</h5></div>
        <div class="modal-body"><p>¿Estás seguro de que deseas cerrar sesión?</p>
          <img src="https://cdn-icons-png.flaticon.com/512/1828/1828479.png" width="100"></div>
        <div class="modal-footer justify-content-center">
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
          <button type="button" class="btn btn-danger" onclick="cerrarSesion()">Sí, salir</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    function cerrarSesion(){ fetch("/logout",{method:"POST"}).then(()=>{ window.location.href="/"; }); }

    const boxEstado = document.getElementById('boxEstado');
    const resultados = document.getElementById('resultados');

    // Config
    const TARGET_CARDS = 12;   // mínimo de tarjetas
    const PER_ROUTE   = 3;     // por ruta

    // Estado global
    let TRIP_TYPE = 'round';       // 'round' | 'oneway'
    let CURRENT_PACK = 'mex_pop';

    // Fecha base
    function fmt(d){ return d.toISOString().slice(0,10); }
    function addDays(d, n){ const x=new Date(d); x.setDate(x.getDate()+n); return x; }
    const today = new Date();
    const salidaBase = addDays(today, 21);
    const regresoBase = addDays(salidaBase, 7);

    // Packs (incluye USA/EU como tenías)
    const PACKS = {
      mex_pop: [
        {o:'MEX', d:'CUN'}, {o:'MEX', d:'GDL'}, {o:'MEX', d:'MTY'},
        {o:'MEX', d:'PVR'}, {o:'MEX', d:'SJD'}, {o:'MEX', d:'OAX'}
      ],
      usa: [
        {o:'MEX', d:'JFK'}, {o:'MEX', d:'LAX'}, {o:'MEX', d:'IAH'},
        {o:'MEX', d:'MIA'}, {o:'MEX', d:'ORD'}, {o:'MEX', d:'DFW'}
      ],
      eu: [
        {o:'MEX', d:'MAD'}, {o:'MEX', d:'BCN'}, {o:'MEX', d:'CDG'},
        {o:'MEX', d:'AMS'}, {o:'MEX', d:'LHR'}, {o:'MEX', d:'FRA'}
      ],
      playa: [
        {o:'MEX', d:'CUN'}, {o:'MEX', d:'PVR'}, {o:'MEX', d:'SJD'},
        {o:'MEX', d:'CZM'}, {o:'MEX', d:'MID'}, {o:'MEX', d:'ZIH'}
      ],
      directos: [
        {o:'MEX', d:'CUN', nonstop:true}, {o:'MEX', d:'GDL', nonstop:true}, {o:'MEX', d:'MTY', nonstop:true},
        {o:'MEX', d:'TIJ', nonstop:true}, {o:'MEX', d:'VER', nonstop:true}, {o:'MEX', d:'TAM', nonstop:true}
      ]
    };

    // Aeropuertos por país (para el filtro País→País)
    const COUNTRY_AIRPORTS = {
      MX: ["MEX","GDL","CUN","MTY","PVR","SJD"],
      US: ["JFK","LAX","IAH","MIA","ORD","DFW","SFO","LAS"],
      CA: ["YYZ","YVR","YYC","YUL"],
      ES: ["MAD","BCN","AGP","SVQ"],
      FR: ["CDG","ORY","NCE"],
      GB: ["LHR","LGW","MAN"],
      DE: ["FRA","MUC","BER"],
      IT: ["FCO","MXP","VCE"],
      BR: ["GRU","GIG","BSB"],
      AR: ["EZE","AEP"],
      CO: ["BOG","MDE","CTG"],
      CL: ["SCL"],
      PE: ["LIM","CUZ"],
      JP: ["HND","NRT","KIX"]
    };

    // +++ NUEVO: helpers para vista previa
    function b64u(obj){
      return btoa(unescape(encodeURIComponent(JSON.stringify(obj)))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'');
    }
    function openPreview(oferta, from, to){
      const meta = { from, to, tripType: TRIP_TYPE };
      const q = b64u({ oferta, meta });
      window.location.href = `/cliente/preview?q=${q}`;
    }

    // Init
    window.addEventListener('DOMContentLoaded', ()=>{
      loadPack(CURRENT_PACK);

      document.getElementById('btnRound').addEventListener('click', ()=> setTripType('round'));
      document.getElementById('btnOneWay').addEventListener('click', ()=> setTripType('oneway'));

      document.querySelectorAll('.pillbar .btn[data-pack]').forEach(btn=>{
        btn.addEventListener('click', ()=>{
          CURRENT_PACK = btn.dataset.pack;
          loadPack(CURRENT_PACK);
        });
      });

      // Diagnóstico modo
      fetch('/cliente/api/diagnostico')
        .then(r=>r.json()).then(js=>{
          const wrap=document.getElementById('modoBanner');
          const alertBox=document.getElementById('modoAlert');
          const txt=document.getElementById('modoText');
          let msg='';
          if(js.mode==='DEMO'){ msg='Modo DEMO: resultados simulados (no reales).'; alertBox.classList.add('alert-warning'); }
          else if(js.mode==='AMADEUS_TEST'){ msg='Modo AMADEUS TEST: datos de prueba limitados.'; alertBox.classList.add('alert-warning'); }
          else if(js.mode==='AMADEUS_PROD'){ msg='Modo AMADEUS PRODUCCIÓN: resultados en vivo.'; alertBox.classList.add('alert-success'); }
          else { msg = `Modo ${js.mode}`; }
          wrap.classList.remove('d-none'); txt.textContent=`${msg} · BASE=${js.base}`;
        }).catch(()=>{});

      // Buscar País→País
      document.getElementById('btnCountrySearch').addEventListener('click', (ev)=>{
        ev.preventDefault();
        const from=document.getElementById('countryFrom').value;
        const to=document.getElementById('countryTo').value;
        if(!from||!to||from===to){
          boxEstado.className='alert alert-warning';
          boxEstado.textContent='Selecciona país origen y destino distintos.';
          boxEstado.classList.remove('d-none');
          return;
        }
        loadByCountry(from,to);
      });
    });

    function setTripType(t){
      TRIP_TYPE = t;
      document.getElementById('btnRound').classList.toggle('active', t==='round');
      document.getElementById('btnOneWay').classList.toggle('active', t==='oneway');
      loadPack(CURRENT_PACK);
    }

    async function loadPack(key){
      resultados.innerHTML = `${'<div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>'.repeat(12)}`;
      boxEstado.className = 'alert alert-info';
      boxEstado.textContent = 'Buscando ofertas destacadas...';
      boxEstado.classList.remove('d-none');

      const routes = PACKS[key] || PACKS.mex_pop;
      let cards = [];

      for (const r of routes){
        if (cards.length >= TARGET_CARDS) break;

        const params = new URLSearchParams({
          origen:  r.o,
          destino: r.d,
          salida:  fmt(salidaBase),
          adultos: '1',
          clase:   'ECONOMY',
          nonstop: r.nonstop ? 'true' : 'false',
          tipo:    TRIP_TYPE
        });
        if (TRIP_TYPE === 'round') params.set('regreso', fmt(regresoBase));

        try{
          const res = await fetch(`/cliente/api/vuelos?${params.toString()}`);
          const js = await res.json();
          if(res.ok){
            const list = (js.ofertas || []).slice(0, PER_ROUTE);
            cards.push(...list.map(o => drawCard(o, r.o, r.d)));
          }
        }catch(e){}
      }

      resultados.innerHTML = cards.length ? cards.join('') :
        '<div class="col-12 text-center text-muted">No encontramos ofertas ahora mismo.</div>';

      boxEstado.className = 'alert alert-success';
      boxEstado.textContent = 'Ofertas actualizadas';
    }

    function drawCard(o, from, to){
      const legs = o.legs.map(l => `
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <div class="airline">${l.from} → ${l.to}</div>
            <div class="small text-muted">${l.dep_local} — ${l.arr_local}</div>
          </div>
          <div class="text-end">
            <span class="badge badge-stop">${l.stops === 0 ? 'Directo' : (l.stops + ' escala' + (l.stops>1?'s':''))}</span><br>
            <span class="small">${l.duration}</span>
          </div>
        </div>`).join('<hr class="my-2">');

      const airlines = (o.airlines||['—']).join(', ');
      return `
        <div class="col-12 col-md-6 col-xl-4">
          <div class="card card-flight p-3 h-100">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <div><i class="bi bi-airplane"></i> ${airlines}</div>
              <div class="price">${o.currency} ${o.price}</div>
            </div>
            <div class="small text-muted mb-2">Ruta: ${from} → ${to} · <span class="badge bg-secondary">${TRIP_TYPE === 'round' ? 'Redondo' : 'Sencillo'}</span></div>
            ${legs}
            <div class="d-flex justify-content-between align-items-center mt-3">
              <div class="small text-muted">Adultos: ${o.adults} · Clase: ${o.travelClass}</div>
              <button class="btn btn-dark" onclick='openPreview(${JSON.stringify(o)}, "${from}", "${to}")'>Reservar</button>
            </div>
          </div>
        </div>`;
    }

    // === Filtro País → País ===
    async function loadByCountry(fromCountry, toCountry){
      resultados.innerHTML = `${'<div class="col-12 col-md-6 col-xl-4"><div class="skeleton"></div></div>'.repeat(12)}`;
      boxEstado.className = 'alert alert-info';
      boxEstado.textContent = `Buscando ofertas ${fromCountry} → ${toCountry}...`;
      boxEstado.classList.remove('d-none');

      const origins = COUNTRY_AIRPORTS[fromCountry] || [];
      const dests   = COUNTRY_AIRPORTS[toCountry] || [];

      if(!origins.length || !dests.length){
        resultados.innerHTML = '<div class="col-12 text-center text-muted">Sin aeropuertos configurados para ese país.</div>';
        boxEstado.className = 'alert alert-warning';
        boxEstado.textContent = 'Intenta con otro país.';
        return;
      }

      let cards = [];
      outer:
      for(const o of origins){
        for(const d of dests){
          if(cards.length >= TARGET_CARDS) break outer;

          const params = new URLSearchParams({
            origen:  o,
            destino: d,
            salida:  fmt(salidaBase),
            adultos: '1',
            clase:   'ECONOMY',
            nonstop: 'false',
            tipo:    TRIP_TYPE
          });
          if (TRIP_TYPE === 'round') params.set('regreso', fmt(regresoBase));

          try{
            const res = await fetch(`/cliente/api/vuelos?${params.toString()}`);
            const js = await res.json();
            if(res.ok){
              const list = (js.ofertas || []).slice(0, PER_ROUTE);
              cards.push(...list.map(of => drawCard(of, o, d)));
            }
          }catch(e){}
        }
      }

      resultados.innerHTML = cards.length ? cards.join('') :
        '<div class="col-12 text-center text-muted">No encontramos ofertas ahora mismo.</div>';

      boxEstado.className = 'alert alert-success';
      boxEstado.textContent = 'Ofertas actualizadas';
    }
  </script>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# =========================
# RESERVAS (pendientes/completadas)
# =========================
html_cliente_reservas = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Mis Reservas</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {font-family:'Segoe UI',sans-serif;}
    .navbar {background:#0a5b5e;}
    .badge-status{font-size:.75rem}
    .card {border-radius:14px; box-shadow:0 10px 24px rgba(0,0,0,.06); border:1px solid #eee;}
    .table > :not(caption) > * > * { vertical-align: middle; }
    .muted { color:#6b7280; }
  </style>
</head>
<body>
<nav class="navbar navbar-dark navbar-expand-lg px-4">
  <a class="navbar-brand" href="/cliente/dashboard">YoungSKY</a>
  <div class="collapse navbar-collapse">
    <ul class="navbar-nav me-auto">
      <li class="nav-item"><a class="nav-link" href="/cliente/dashboard">✈ Vuelos</a></li>
      <li class="nav-item"><a class="nav-link active" href="/cliente/reservas">🏨 Reservas</a></li>
      <li class="nav-item"><a class="nav-link" href="/cliente/historial">🧳 Historial</a></li>
    </ul>
  </div>
</nav>

<div class="container my-4">
  <h3 class="mb-3">Mis reservas</h3>

  <ul class="nav nav-pills mb-3" id="pills-tab" role="tablist">
    <li class="nav-item" role="presentation">
      <button class="nav-link active" id="pills-pend-tab" data-bs-toggle="pill" data-bs-target="#pills-pend" type="button" role="tab">
        Pendientes <span class="badge text-bg-warning ms-1">{{ pendientes|length }}</span>
      </button>
    </li>
    <li class="nav-item" role="presentation">
      <button class="nav-link" id="pills-comp-tab" data-bs-toggle="pill" data-bs-target="#pills-comp" type="button" role="tab">
        Completadas <span class="badge text-bg-success ms-1">{{ completadas|length }}</span>
      </button>
    </li>
  </ul>

  <div class="tab-content">
    <!-- PENDIENTES -->
    <div class="tab-pane fade show active" id="pills-pend" role="tabpanel">
      <div class="card">
        <div class="card-body">
          {% if pendientes and pendientes|length > 0 %}
          <div class="table-responsive">
            <table class="table align-middle">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Ruta</th>
                  <th>Fechas</th>
                  <th>Clase</th>
                  <th>Boletos</th>
                  <th>Extras</th>
                  <th>Precio</th>
                  <th>Comprobante</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                <tbody>
    {% for r in pendientes %}
    <tr>
        <td>{{ r.id }}</td>
        <td><strong>{{ r.origen }} → {{ r.destino }}</strong></td>
        <td>
            <div>{{ r.salida or '—' }}</div>
            {% if r.regreso %}<div class="text-muted small">Regreso: {{ r.regreso }}</div>{% endif %}
        </td>
        <td>{{ r.clase }}</td>
        <td>{{ r.boletos or r.cantidad or 1 }}</td>
        <td>
            {% set seguro = (r.seguro|default(0))|int %}
            {% set transporte = (r.transporte|default(0))|int %}
            {% if seguro == 1 %}<span class="badge bg-info">Seguro</span>{% endif %}
            {% if transporte == 1 %}<span class="badge bg-secondary">Transporte</span>{% endif %}
            {% if seguro == 0 and transporte == 0 %}<span class="text-muted">—</span>{% endif %}
        </td>
        <td>{{ r.moneda or 'MXN' }} {{ r.precio }}</td>
        <td><span class="badge text-bg-warning badge-status">Pendiente</span></td>
        <td class="text-muted">—</td>
    </tr>
    {% endfor %}
</tbody>
            </table>
          </div>
          {% else %}
          <div class="text-center text-muted py-4">No tienes reservas pendientes.</div>
          {% endif %}
        </div>
      </div>
    </div>

    <!-- COMPLETADAS -->
<div class="tab-pane fade" id="pills-comp" role="tabpanel">
  <div class="card">
    <div class="card-body">
      {% if completadas and completadas|length > 0 %}
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>#</th>
              <th>Ruta</th>
              <th>Fechas</th>
              <th>Clase</th>
              <th>Boletos</th>
              <th>Extras</th>
              <th>Precio</th>
              <th>Estado</th>
              <th>Comprobante</th>  <!-- COLUMNA AÑADIDA -->
            </tr>
          </thead>
          <tbody>
            {% for r in completadas %}
            <tr>
              <td>{{ r.id }}</td>
              <td><strong>{{ r.origen }} → {{ r.destino }}</strong></td>
              <td>
                <div>{{ r.salida or '—' }}</div>
                {% if r.regreso %}<div class="text-muted small">Regreso: {{ r.regreso }}</div>{% endif %}
              </td>
              <td>{{ r.clase }}</td>
              <td>{{ r.boletos or r.cantidad or 1 }}</td>
              <td>
                {% set seguro = (r.seguro|default(0))|int %}
                {% set transporte = (r.transporte|default(0))|int %}
                {% if seguro == 1 %}<span class="badge bg-info">Seguro</span>{% endif %}
                {% if transporte == 1 %}<span class="badge bg-secondary">Transporte</span>{% endif %}
                {% if seguro == 0 and transporte == 0 %}<span class="text-muted">—</span>{% endif %}
              </td>
              <td>{{ r.moneda or 'MXN' }} {{ r.precio }}</td>
              <td><span class="badge text-bg-success badge-status">Completada</span></td>
              <td>
                {% if r.comprobante %}
                <a href="{{ comprobante_base_url }}{{ r.comprobante }}" 
                   target="_blank" 
                   class="btn btn-sm btn-outline-primary">
                    📄 Descargar
                </a>
                {% else %}
                <span class="text-muted">—</span>
                {% endif %}
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
      <div class="text-center text-muted py-4">Aún no hay reservas completadas.</div>
      {% endif %}
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>

"""


# =========================
# HISTORIAL (timeline)
# =========================
html_cliente_historial = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Historial de Reservas</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {font-family:'Segoe UI',sans-serif;}
    .navbar {background:#0a5b5e;}
    .timeline {position:relative; padding-left:1rem;}
    .timeline::before {content:""; position:absolute; left:12px; top:0; bottom:0; width:2px; background:#e5e7eb;}
    .t-item {position:relative; padding-left:2.2rem; margin-bottom:1rem;}
    .t-item::before {content:""; position:absolute; left:6px; top:.35rem; width:12px; height:12px; border-radius:50%; background:#0a5b5e;}
    .card {border-radius:14px; box-shadow:0 10px 24px rgba(0,0,0,.06); border:1px solid #eee;}
  </style>
</head>
<body>
<nav class="navbar navbar-dark navbar-expand-lg px-4">
  <a class="navbar-brand" href="/cliente/dashboard">YoungSKY</a>
  <div class="collapse navbar-collapse">
    <ul class="navbar-nav me-auto">
      <li class="nav-item"><a class="nav-link" href="/cliente/dashboard">✈ Vuelos</a></li>
      <li class="nav-item"><a class="nav-link" href="/cliente/reservas">🏨 Reservas</a></li>
      <li class="nav-item"><a class="nav-link active" href="/cliente/historial">🧳 Historial</a></li>
    </ul>
  </div>
</nav>

<div class="container my-4">
  <h3 class="mb-3">Historial de reservas</h3>
  {% if historial %}
  <div class="card">
    <div class="card-body">
      <div class="timeline">
        {% for r in historial %}
        <div class="t-item">
          <div class="d-flex justify-content-between">
            <div>
              <strong>{{ r.origen }} → {{ r.destino }}</strong>
              <div class="text-muted small">
                {{ r.salida or '—' }}
                {% if r.regreso %} · Regreso: {{ r.regreso }}{% endif %}
                · Clase: {{ r.clase }}
              </div>
            </div>
            <div class="text-end">
              <div><strong>{{ r.moneda }} {{ r.precio }}</strong></div>
              <span class="badge {{ 'text-bg-success' if r.estado in ['completada','confirmada','finalizada','completed'] else 'text-bg-secondary' }}">{{ r.estado|capitalize }}</span>
            </div>
          </div>
          {% if r.creado %}<div class="small text-muted mt-1">Creada: {{ r.creado }}</div>{% endif %}
        </div>
        {% endfor %}
      </div>
    </div>
  </div>
  {% else %}
  <div class="text-center text-muted py-5">Aún no tienes historial de reservas.</div>
  {% endif %}
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# =========================
# +++ NUEVO: HTML para vista previa
# =========================
html_preview = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Mis Reservas</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {font-family:'Segoe UI',sans-serif;}
    .navbar {background:#0a5b5e;}
    .badge-status{font-size:.75rem}
    .card {border-radius:14px; box-shadow:0 10px 24px rgba(0,0,0,.06); border:1px solid #eee;}
    .table > :not(caption) > * > * { vertical-align: middle; }
    .muted { color:#6b7280; }
  </style>
</head>
<body>
<nav class="navbar navbar-dark navbar-expand-lg px-4">
  <a class="navbar-brand" href="/cliente/dashboard">YoungSKY</a>
  <div class="collapse navbar-collapse">
    <ul class="navbar-nav me-auto">
      <li class="nav-item"><a class="nav-link" href="/cliente/dashboard">✈ Vuelos</a></li>
      <li class="nav-item"><a class="nav-link active" href="/cliente/reservas">🏨 Reservas</a></li>
      <li class="nav-item"><a class="nav-link" href="/cliente/historial">🧳 Historial</a></li>
    </ul>
  </div>
</nav>

<div class="container my-4">
  <h3 class="mb-3">Mis reservas</h3>

  <ul class="nav nav-pills mb-3" id="pills-tab" role="tablist">
    <li class="nav-item" role="presentation">
      <button class="nav-link active" id="pills-pend-tab" data-bs-toggle="pill" data-bs-target="#pills-pend" type="button" role="tab">
        Pendientes <span class="badge text-bg-warning ms-1">{{ pendientes|length }}</span>
      </button>
    </li>
    <li class="nav-item" role="presentation">
      <button class="nav-link" id="pills-comp-tab" data-bs-toggle="pill" data-bs-target="#pills-comp" type="button" role="tab">
        Completadas <span class="badge text-bg-success ms-1">{{ completadas|length }}</span>
      </button>
    </li>
  </ul>

  <div class="tab-content">
    <!-- PENDIENTES -->
    <div class="tab-pane fade show active" id="pills-pend" role="tabpanel">
      <div class="card">
        <div class="card-body">
          {% if pendientes and pendientes|length > 0 %}
          <div class="table-responsive">
            <table class="table align-middle">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Ruta</th>
                  <th>Fechas</th>
                  <th>Clase</th>
                  <th>Boletos</th>
                  <th>Extras</th>
                  <th>Precio</th>
                  <th>Estado</th>
                  <th>Comprobante</th>
                </tr>
              </thead>
              <tbody>
                {% for r in pendientes %}
                <tr>
                  <td>{{ r.id }}</td>
                  <td><strong>{{ r.origen }} → {{ r.destino }}</strong></td>
                  <td>
                    <div>{{ r.salida or '—' }}</div>
                    {% if r.regreso %}<div class="text-muted small">Regreso: {{ r.regreso }}</div>{% endif %}
                  </td>
                  <td>{{ r.clase }}</td>
                  <td>{{ r.boletos or r.cantidad or 1 }}</td>
                  <td>
                    {% set seguro = (r.seguro|default(0))|int %}
                    {% set transporte = (r.transporte|default(0))|int %}
                    {% if seguro == 1 %}<span class="badge bg-info">Seguro</span>{% endif %}
                    {% if transporte == 1 %}<span class="badge bg-secondary">Transporte</span>{% endif %}
                    {% if seguro == 0 and transporte == 0 %}<span class="text-muted">—</span>{% endif %}
                  </td>
                  <td>{{ r.moneda or 'MXN' }} {{ r.precio }}</td>
                  <td><span class="badge text-bg-warning badge-status">Pendiente</span></td>
                  <td class="text-muted">—</td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
          {% else %}
          <div class="text-center text-muted py-4">No tienes reservas pendientes.</div>
          {% endif %}
        </div>
      </div>
    </div>

   <!-- COMPLETADAS -->
<div class="tab-pane fade" id="pills-comp" role="tabpanel">
  <div class="card">
    <div class="card-body">
      {% if completadas and completadas|length > 0 %}
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>#</th>
              <th>Ruta</th>
              <th>Fechas</th>
              <th>Clase</th>
              <th>Boletos</th>
              <th>Extras</th>
              <th>Precio</th>
              <th>Estado</th>
              <th>Comprobante</th>  <!-- COLUMNA AÑADIDA -->
            </tr>
          </thead>
          <tbody>
            {% for r in completadas %}
            <tr>
              <td>{{ r.id }}</td>
              <td><strong>{{ r.origen }} → {{ r.destino }}</strong></td>
              <td>
                <div>{{ r.salida or '—' }}</div>
                {% if r.regreso %}<div class="text-muted small">Regreso: {{ r.regreso }}</div>{% endif %}
              </td>
              <td>{{ r.clase }}</td>
              <td>{{ r.boletos or r.cantidad or 1 }}</td>
              <td>
                {% set seguro = (r.seguro|default(0))|int %}
                {% set transporte = (r.transporte|default(0))|int %}
                {% if seguro == 1 %}<span class="badge bg-info">Seguro</span>{% endif %}
                {% if transporte == 1 %}<span class="badge bg-secondary">Transporte</span>{% endif %}
                {% if seguro == 0 and transporte == 0 %}<span class="text-muted">—</span>{% endif %}
              </td>
              <td>{{ r.moneda or 'MXN' }} {{ r.precio }}</td>
              <td><span class="badge text-bg-success badge-status">Completada</span></td>
              <td>
                {% if r.comprobante %}
                <a href="{{ comprobante_base_url }}{{ r.comprobante }}" 
                   target="_blank" 
                   class="btn btn-sm btn-outline-primary">
                    📄 Descargar
                </a>
                {% else %}
                <span class="text-muted">—</span>
                {% endif %}
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
      <div class="text-center text-muted py-4">Aún no hay reservas completadas.</div>
      {% endif %}
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# =========================
# Rutas: Dashboard / Reservas / Historial
# =========================
@cliente_bp.route("/dashboard")
def dashboard():
    if session.get("rol") != "cliente":
        return redirect(url_for("login.mostrar_login"))
    return render_template_string(html_cliente_dashboard)

@cliente_bp.route("/reservas")
def reservas_view():
    if session.get("rol") != "cliente":
        return redirect(url_for("login.mostrar_login"))
    user_id = session.get("id_usuario") or session.get("user_id") or session.get("id")
    pendientes, completadas, _ = _fetch_reservas(user_id)
    
    # Obtener la URL base para los comprobantes
    comprobante_base_url = url_for('admin.servir_comprobante_cliente', filename='')
    return render_template_string(html_cliente_reservas, 
                                pendientes=pendientes, 
                                completadas=completadas,
                                comprobante_base_url=comprobante_base_url)

@cliente_bp.route("/eliminar_reserva/<int:id>", methods=["POST"])
def eliminar_reserva(id):
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # Eliminar la reserva con el id especificado
            cur.execute("DELETE FROM reservas WHERE id = %s", (id,))
            conn.commit()
        return redirect(url_for("cliente.reservas_view"))
    except Exception as e:
        print(f"Error al eliminar la reserva: {e}")
        return redirect(url_for("cliente.reservas_view"))

@cliente_bp.route("/historial")
def historial_view():
    if session.get("rol") != "cliente":
        return redirect(url_for("login.mostrar_login"))
    user_id = session.get("id_usuario") or session.get("user_id") or session.get("id")
    _, _, historial = _fetch_reservas(user_id)
    return render_template_string(html_cliente_historial, historial=historial)

# =========================
# +++ NUEVO: Rutas de vista previa y confirmación
# =========================
@cliente_bp.route("/preview")
def preview():
    if session.get("rol") != "cliente":
        return redirect(url_for("login.mostrar_login"))
    raw_b64 = request.args.get("q") or ""
    try:
        js = json.loads(base64.urlsafe_b64decode(raw_b64 + "==="))
    except Exception:
        return "Parámetros inválidos", 400

    oferta = js.get("oferta", {})
    meta   = js.get("meta", {})
    airlines = ", ".join(oferta.get("airlines") or ["—"])
    otype = "Redondo" if meta.get("tripType") == "round" else "Sencillo"
    return render_template_string(
        html_preview,
        oferta=oferta,
        airlines=airlines,
        ofrom=escape(meta.get("from","")),
        oto=escape(meta.get("to","")),
        otype=otype,
        raw_b64=raw_b64
    )

@cliente_bp.route("/confirmar", methods=["POST"])
def confirmar():
    # Verificar sesión de manera más robusta
    if 'rol' not in session or session.get("rol") != "cliente":
        return redirect(url_for("login.mostrar_login"))
    
    # Obtener ID de usuario de múltiples formas posibles
    user_id = (session.get("id_usuario") or 
               session.get("user_id") or 
               session.get("id") or
               session.get("usuario_id"))
    
    if not user_id:
        print("DEBUG: No se encontró user_id en sesión:", session)
        return redirect(url_for("login.mostrar_login"))

    raw_b64 = request.form.get("payload") or ""
    try:
        data = json.loads(base64.urlsafe_b64decode(raw_b64 + "==="))
    except Exception:
        return "Datos inválidos", 400

    oferta = data.get("oferta", {})
    meta = data.get("meta", {})

    # === Leer formulario ===
    try:
        qty = max(1, int(request.form.get("qty", "1")))
    except Exception:
        qty = 1
    want_seguro = (request.form.get("want_seguro") == "1")
    want_trans = (request.form.get("want_transporte") == "1")

    # === Precios base ===
    def _to_float(s):
        try:
            return float(str(s).replace(",", "").strip())
        except Exception:
            import re
            return float(re.sub(r"[^0-9.]", "", str(s)) or 0)

    base_unit = _to_float(oferta.get("price", "0"))
    seguro_unit = 249.00
    transporte_unit = 180.00

    # Normaliza datos de vuelo
    origen = (oferta.get("legs") or [{}])[0].get("from")
    destino = (oferta.get("legs") or [{}])[-1].get("to")
    salida = (oferta.get("legs") or [{}])[0].get("dep_local")
    regreso = ""
    if len(oferta.get("legs") or []) > 1:
        regreso = (oferta["legs"][-1] or {}).get("dep_local")

    moneda = oferta.get("currency") or "MXN"
    clase = oferta.get("travelClass") or "ECONOMY"
    estado = "pendiente"
    fuente = oferta.get("source") or "?"

    # Totales
    extra_seguro = seguro_unit * qty if want_seguro else 0.0
    extra_trans = transporte_unit * qty if want_trans else 0.0
    total_amount = (base_unit * qty) + extra_seguro + extra_trans

    # Inserta en DB
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO reservas 
                (usuario_id, origen, destino, salida, regreso, precio, moneda, clase, estado, boletos, seguro, transporte, fuente, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """, (
                user_id,  # Usar el ID obtenido de la sesión
                origen, destino, salida, regreso,
                f"{total_amount:.2f}", moneda, clase, estado,
                qty, int(want_seguro), int(want_trans), fuente
            ))
            conn.commit()  # Asegurar commit
        print(f"DEBUG: Reserva creada para usuario {user_id}")
    except Exception as e:
        print("Error guardando reserva:", e)
        # Podrías mostrar un mensaje de error al usuario
        return "Error al guardar la reserva", 500

    return redirect(url_for("cliente.reservas_view"))


# =========================
# API: Autocomplete y Vuelos y Diagnóstico
# =========================
@cliente_bp.route("/api/locations")
def locations():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"items": []})

    if not have_amadeus():
        sample = [
            {"code":"MEX","label":"Ciudad de México (MEX) — México"},
            {"code":"GDL","label":"Guadalajara (GDL) — México"},
            {"code":"CUN","label":"Cancún (CUN) — México"},
            {"code":"JFK","label":"New York (JFK) — United States"},
            {"code":"LAX","label":"Los Angeles (LAX) — United States"},
        ]
        items = [x for x in sample if q.lower() in x["label"].lower() or q.lower() in x["code"].lower()]
        return jsonify({"items": items[:8]})

    try:
        js = _amadeus_get("/v1/reference-data/locations", {
            "subType": "CITY,AIRPORT",
            "keyword": q,
            "page[limit]": 8,
        })
        items = []
        for it in js.get("data", []):
            code = it.get("iataCode") or ""
            name = it.get("name") or ""
            city = (it.get("address") or {}).get("cityName") or ""
            country = (it.get("address") or {}).get("countryName") or ""
            if code:
                label = f"{city or name} ({code}) — {country}".strip()
                items.append({"code": code, "label": label})
        return jsonify({"items": items})
    except Exception as e:
        return jsonify({"items": [], "error": str(e)}), 500

@cliente_bp.route("/api/vuelos")
def vuelos():
    """
    Busca ofertas de vuelos. Si hay Amadeus, consulta real; si no, devuelve demo.
    Parámetros: origen, destino, salida (YYYY-MM-DD), regreso (opcional), adultos, clase, nonstop(true/false), tipo(round/oneway)
    """
    origen = (request.args.get("origen") or "").strip().upper()
    destino = (request.args.get("destino") or "").strip().upper()
    salida = (request.args.get("salida") or "").strip()
    regreso = (request.args.get("regreso") or "").strip()
    adultos = int(request.args.get("adultos") or 1)
    clase = (request.args.get("clase") or "ECONOMY").strip().upper()
    nonstop = (request.args.get("nonstop") or "false").lower() == "true"
    tipo = (request.args.get("tipo") or "round").lower()

    if not (origen and destino and salida):
        return jsonify({"error": "Origen, destino y fecha de salida son obligatorios."}), 400
    if tipo == "oneway":
        regreso = ""

    # +++ NUEVO: fuente actual
    src = _current_mode()

    if not have_amadeus():
        legs_ida = {"from":origen,"to":destino,"dep_local":f"{salida} 08:25","arr_local":f"{salida} 12:10","duration":"3h 45m","stops":0}
        legs_vta = {"from":destino,"to":origen,"dep_local":f"{regreso} 18:20","arr_local":f"{regreso} 21:55","duration":"3h 35m","stops":0}
        demo_legs = [legs_ida] if tipo=="oneway" else [legs_ida, legs_vta]
        demo = {"ofertas":[
            {"price":"3,850.00","currency":"MXN","airlines":["AM"],"adults":str(adultos),"travelClass":clase,"legs":demo_legs, "source": src},
            {"price":"4,299.00","currency":"MXN","airlines":["AA"],"adults":str(adultos),"travelClass":clase,"legs":demo_legs, "source": src},
        ]}
        return jsonify(demo)

    try:
        params = {
            "originLocationCode": origen,
            "destinationLocationCode": destino,
            "departureDate": salida,
            "adults": adultos,
            "currencyCode": "MXN",
            "travelClass": clase,
            "nonStop": str(nonstop).lower(),
            "max": 30
        }
        if regreso:
            params["returnDate"] = regreso

        js = _amadeus_get("/v2/shopping/flight-offers", params)
        data = js.get("data", [])
        ofertas = []
        for off in data:
            price = off.get("price", {})
            currency = price.get("currency", "MXN")
            total = price.get("total", "0.00")
            tp = (off.get("travelerPricings") or [{}])[0]
            travel_class = (tp.get("fareDetailsBySegment") or [{}])[0].get("cabin", clase)
            airlines = off.get("validatingAirlineCodes") or []

            legs = []
            for itin in off.get("itineraries", []):
                segs = itin.get("segments", [])
                if not segs: continue
                first, last = segs[0], segs[-1]
                from_code = (first.get("departure") or {}).get("iataCode", "")
                to_code   = (last.get("arrival") or {}).get("iataCode", "")
                dep = (first.get("departure") or {}).get("at", "").replace("T"," ")
                arr = (last.get("arrival") or {}).get("at", "").replace("T"," ")
                dur = _iso_duration_to_hm(itin.get("duration"))
                stops = max(len(segs) - 1, 0)
                legs.append({"from":from_code,"to":to_code,"dep_local":dep,"arr_local":arr,"duration":dur,"stops":stops})

            ofertas.append({
                "price": total,
                "currency": currency,
                "airlines": airlines or ["—"],
                "adults": str(adultos),
                "travelClass": travel_class,
                "legs": legs,
                "source": src  # +++ NUEVO
            })

        return jsonify({"ofertas": ofertas})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@cliente_bp.route("/api/diagnostico")
def diagnostico():
    mode = "DEMO"
    base = AMADEUS_BASE
    reasons = []
    if requests is None:
        reasons.append("paquete requests no instalado")
    if AMADEUS_API_KEY and AMADEUS_API_SECRET and requests is not None:
        if "api.amadeus.com" in base:
            mode = "AMADEUS_PROD"
        elif "test.api.amadeus.com" in base:
            mode = "AMADEUS_TEST"
        else:
            mode = "AMADEUS_CUSTOM"
    else:
        if not AMADEUS_API_KEY: reasons.append("Falta AMADEUS_API_KEY")
        if not AMADEUS_API_SECRET: reasons.append("Falta AMADEUS_API_SECRET")
    return jsonify({"mode": mode, "base": base, "reasons": reasons})


def _normalize_reserva(row):
    import json as _json

    def pick(*keys, default=""):
        for k in keys:
            if k in row and row[k] is not None:
                return row[k]
        return default

    # cantidad / boletos
    boletos = pick("boletos", "cantidad", "qty", "num_boletos", default=1)
    try: boletos = int(boletos)
    except Exception: boletos = 1

    # flags extras (pueden venir como None/True/False/"0"/"1")
    def to_int01(v, default=0):
        try:
            if isinstance(v, bool): return 1 if v else 0
            if v in ("", None): return default
            return 1 if int(v) == 1 else 0
        except Exception:
            return default

    seguro = to_int01(pick("seguro", "has_seguro", "insurance", default=0), default=0)
    transporte = to_int01(pick("transporte", "shuttle", "transfer", "trans", default=0), default=0)

    # extras_json puede rellenar si faltan
    extras_raw = pick("extras_json", "extras", default="")
    if extras_raw and (seguro == 0 or transporte == 0):
        try:
            ej = extras_raw if isinstance(extras_raw, dict) else _json.loads(extras_raw)
            if seguro == 0 and bool(ej.get("seguro")): seguro = 1
            if transporte == 0 and bool(ej.get("transporte")): transporte = 1
        except Exception:
            pass

    # string legible de extras (opcional)
    parts = []
    if seguro: parts.append("Seguro")
    if transporte: parts.append("Transporte")
    extras_str = ", ".join(parts)

    return {
        "id":        pick("id","id_reserva","id_solicitud"),
        "usuario_id":pick("usuario_id","user_id","id_usuario", default=None),
        "origen":    pick("origen","origen_iata","from_code"),
        "destino":   pick("destino","destino_iata","to_code"),
        "salida":    pick("salida","fecha_salida","fecha_ida"),
        "regreso":   pick("regreso","fecha_regreso","fecha_vuelta"),
        "precio":    pick("precio","precio_total","total","price"),
        "moneda":    pick("moneda","currency","divisa", default="MXN"),
        "clase":     pick("clase","travelClass","cabina","cabin", default="ECONOMY"),
        "estado":    (pick("estado","status", default="pendiente") or "").lower(),
        "creado":    pick("created_at","fecha_creacion","fecha","creado_en"),
        "boletos":   boletos,
        "seguro":    seguro,
        "transporte":transporte,
        "extras":    extras_str,
        "comprobante": pick("comprobante", "evidencia", default=None),  
    }


def _fetch_reservas(usuario_id=None):
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            try:
                if usuario_id:
                    cur.execute("SELECT * FROM reservas WHERE usuario_id=%s ORDER BY created_at DESC LIMIT 500", (usuario_id,))
                else:
                    cur.execute("SELECT * FROM reservas ORDER BY created_at DESC LIMIT 500")
                rows = cur.fetchall()
            except Exception:
                if usuario_id:
                    cur.execute("SELECT * FROM solicitudes_viaje WHERE usuario_id=%s ORDER BY created_at DESC LIMIT 500", (usuario_id,))
                else:
                    cur.execute("SELECT * FROM solicitudes_viaje ORDER BY created_at DESC LIMIT 500")
                rows = cur.fetchall()
    except Exception:
        rows = [{
            "id": 1, "usuario_id": usuario_id or 1, "origen":"MEX","destino":"CUN",
            "salida":"2025-09-01 08:25","regreso":"2025-09-08 21:55","precio":"4,299.00",
            "moneda":"MXN","clase":"ECONOMY","estado":"pendiente","created_at":"2025-08-01"
        },{
            "id": 2, "usuario_id": usuario_id or 1, "origen":"MEX","destino":"GDL",
            "salida":"2025-09-05 09:00","regreso":"2025-09-09 18:00","precio":"2,199.00",
            "moneda":"MXN","clase":"ECONOMY","estado":"completada","created_at":"2025-07-20"
        }]
    norm = [_normalize_reserva(r) for r in rows]
    pend = [r for r in norm if r["estado"] in ("pendiente","en_proceso","procesando","por_confirmar","","pending")]
    comp = [r for r in norm if r["estado"] in ("completada","confirmada","finalizada","completed","cerrada")]
    hist = norm
    return pend, comp, hist

@cliente_bp.route('/reservas/crear', methods=['POST'])
def crear_reserva():
    if 'user_id' not in session:
        flash('Debes iniciar sesión para hacer una reserva', 'error')
        return redirect(url_for('login.mostrar_login'))

    usuario_id = session['user_id']  
    origen = request.form.get('origen')
    destino = request.form.get('destino')
    salida = request.form.get('salida')
    regreso = request.form.get('regreso')
    precio = request.form.get('precio')
    moneda = request.form.get('moneda')
    clase = request.form.get('clase')
    boletos = request.form.get('boletos', 1)
    seguro = request.form.get('seguro', 0)
    transporte = request.form.get('transporte', 0)
    fuente = "WEB"

    try:
        conn = get_conn()  # Aquí conectas a tu base de datos
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO reservas (
                    usuario_id, origen, destino, salida, regreso, 
                    precio, moneda, clase, estado, boletos, seguro, transporte, fuente
                ) VALUES (
                    %s, %s, %s, %s, %s, 
                    %s, %s, %s, 'pendiente', %s, %s, %s, %s
                )
            """, (
                usuario_id, origen, destino, salida, regreso,
                precio, moneda, clase, boletos, seguro, transporte, fuente
            ))
        flash("Reserva creada con éxito ", "success")
    except Exception as e:
        print("Error creando reserva:", e)
        flash("Hubo un error al crear la reserva", "error")
    finally:
        conn.close()

    return redirect(url_for('usuarios.mis_pedidos'))  