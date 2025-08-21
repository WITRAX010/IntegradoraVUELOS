
from flask import Blueprint, render_template_string, session, redirect, url_for, request, jsonify
from werkzeug.utils import secure_filename
from flask import send_from_directory
from flask import render_template, request, redirect, url_for
import pymysql
from decimal import Decimal
import os
from werkzeug.utils import secure_filename

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root")   
DB_NAME = os.getenv("DB_NAME", "youngsky")
DB_PORT = int(os.getenv("DB_PORT", 3306))


USE_HASH = False


try:
    from werkzeug.security import generate_password_hash
except Exception:
    generate_password_hash = None

def get_conn():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        port=DB_PORT,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )


# Configuración para uploads
UPLOAD_FOLDER = 'uploads/comprobantes'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

# Asegúrate de que la carpeta exista
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



def fetch_metrics(conn):
    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) AS total FROM usuarios;")
        usuarios = c.fetchone()["total"]

        # Pedidos activos = solicitudes pendientes
        c.execute("SELECT COUNT(*) AS total FROM solicitudes_viaje WHERE estado='pendiente';")
        pedidos_activos = c.fetchone()["total"]

        # Reservas confirmadas + Ingresos (si existe 'propuestas')
        try:
            c.execute("SELECT COUNT(*) AS total FROM propuestas WHERE estado='aceptada';")
            reservas_confirmadas = c.fetchone()["total"]
            c.execute("SELECT COALESCE(SUM(costo_estimado),0) AS total FROM propuestas WHERE estado='aceptada';")
            ingresos = c.fetchone()["total"] or 0
        except Exception:
            reservas_confirmadas = 0
            ingresos = 0

    if isinstance(ingresos, Decimal):
        ingresos = float(ingresos)
    ingresos_txt = f"${ingresos:,.2f}"

    return {
        "usuarios": usuarios,
        "pedidos_activos": pedidos_activos,
        "reservas_confirmadas": reservas_confirmadas,
        "ingresos_txt": ingresos_txt
    }

def fetch_usuarios(conn):
    with conn.cursor() as c:
        c.execute("""
            SELECT id, nombre, email, rol, pais_residencia, fecha_registro
            FROM usuarios
            ORDER BY id DESC
            LIMIT 500;
        """)
        return c.fetchall()

def fetch_pedidos(conn):
    with conn.cursor() as c:
        c.execute("""
            SELECT s.id,
                   COALESCE(u.nombre, CONCAT('Usuario #', s.usuario_id)) AS cliente,
                   s.pais_destino,
                   s.tipo_viaje,
                   s.estado,
                   DATE(s.fecha_solicitud) AS fecha_solicitud
            FROM solicitudes_viaje s
            LEFT JOIN usuarios u ON u.id = s.usuario_id
            ORDER BY s.id DESC
            LIMIT 500;
        """)
        return c.fetchall()

def fetch_series(conn, meses=6):
    # Usuarios por mes (últimos N)
    with conn.cursor() as c:
        c.execute("""
            SELECT DATE_FORMAT(fecha_registro, '%Y-%m') AS ym, COUNT(*) AS cnt
            FROM usuarios
            GROUP BY ym
            ORDER BY ym ASC;
        """)
        u_rows = c.fetchall()

    # Solicitudes por estado (snapshot)
    with conn.cursor() as c:
        c.execute("""
            SELECT estado, COUNT(*) AS cnt
            FROM solicitudes_viaje
            GROUP BY estado;
        """)
        s_estado = c.fetchall()

    # Solicitudes por mes (últimos N)
    with conn.cursor() as c:
        c.execute("""
            SELECT DATE_FORMAT(fecha_solicitud, '%Y-%m') AS ym, COUNT(*) AS cnt
            FROM solicitudes_viaje
            GROUP BY ym
            ORDER BY ym ASC;
        """)
        s_mes = c.fetchall()

    # Tomar sólo los últimos N meses si hay más
    u_labels = [r["ym"] for r in u_rows][-meses:]
    u_data   = [r["cnt"] for r in u_rows][-meses:]

    s_estado_labels = [r["estado"] for r in s_estado] if s_estado else []
    s_estado_data   = [r["cnt"] for r in s_estado] if s_estado else []

    s_mes_labels = [r["ym"] for r in s_mes][-meses:]
    s_mes_data   = [r["cnt"] for r in s_mes][-meses:]

    return {
        "usuarios": {"labels": u_labels, "data": u_data},
        "solicitudes_estado": {"labels": s_estado_labels, "data": s_estado_data},
        "solicitudes_mes": {"labels": s_mes_labels, "data": s_mes_data},
    }

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

html_admin_dashboard = '''
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Panel Administrador - YoungSky</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1"></script>
  <style>
    body { margin: 0; font-family: 'Segoe UI', sans-serif; background-color: #fff; }
    .nav-link, .navbar-brand, .btn { color: white !important; }
    .nav-link.active { background-color: #0a5b5e; border-radius: 20px; padding: 5px 15px; }
    .admin-card { background-color: #f8f9fa; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); padding: 20px; margin-bottom: 20px; }
    .table th { background-color: #0a5b5e; color: white; }
    .main-footer { background-color: rgba(0,0,0,0.6); color: #ccc; padding: 30px 20px; display:flex; flex-wrap:wrap; justify-content:space-between; font-size:14px; }
    .main-footer .footer-left, .main-footer .footer-column { flex:1; min-width:200px; margin-bottom:20px; }
    footer.copyright { text-align:center; padding:10px; background-color:#111; color:#aaa; font-size:12px; }
    .chart-card { background:#f8f9fa; border-radius:10px; padding:16px; box-shadow:0 4px 10px rgba(0,0,0,0.06); height:100%; }
    canvas { max-height: 260px; }
    .form-section { background:#f8f9fa; border-radius:12px; padding:18px; box-shadow:0 4px 10px rgba(0,0,0,0.06); }
  </style>
</head>
<body>

<nav class="navbar navbar-dark navbar-expand-lg px-4">
  <a class="navbar-brand" href="#">YoungSKY Admin</a>
  <div class="collapse navbar-collapse">
    <ul class="navbar-nav me-auto">
      <li class="nav-item"><a class="nav-link" href="/admin/dashboard">Dashboard</a></li>
      <li class="nav-item"><a class="nav-link" href="/admin/solicitudes">Solicitudes</a></li> 
      <li class="nav-item"><a class="nav-link" href="/admin/usuarios">Usuarios</a></li>
      <li class="nav-item"><a class="nav-link" href="/admin/pedidos">Pedidos</a></li>
      <li class="nav-item"><a class="nav-link" href="/admin/configuracion">Configuración</a></li>
    </ul>
  </div>
</nav>


<nav class="navbar navbar-expand-lg navbar-dark bg-dark px-4">
  <a class="navbar-brand" href="#">YoungSKY</a>
  <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarAdmin">
    <span class="navbar-toggler-icon"></span>
  </button>
  <div class="collapse navbar-collapse" id="navbarAdmin">
    <ul class="navbar-nav me-auto mb-2 mb-lg-0">
      <li class="nav-item"><a class="nav-link active" href="#" onclick="mostrarSeccion('panel')">Panel</a></li>
      <li class="nav-item"><a class="nav-link" href="#" onclick="mostrarSeccion('usuarios')">Usuarios</a></li>
      <li class="nav-item"><a class="nav-link" href="#" onclick="mostrarSeccion('pedidos')">Pedidos</a></li>
      <li class="nav-item"><a class="nav-link" href="#" onclick="mostrarSeccion('config')">Configuración</a></li>
      <li class="nav-item"><a class="nav-link" href="#" onclick="mostrarSeccion('solicitudes')">Solicitudes</a></li>
    </ul>
    <div class="d-flex align-items-center">
      <a href="#" class="btn me-2" onclick="mostrarModalCerrarSesion()" style="background-color: #686868; color: white;">Cerrar sesión</a>
    </div>
  </div>
</nav>

<!-- PANEL -->
<div class="container mt-4" id="panel">
  <div class="row g-3">
    <div class="col-md-3"><div class="admin-card text-center"><h6 class="mb-1">Usuarios registrados</h6><p class="fs-3 mb-0">{{ metrics.usuarios }}</p></div></div>
    <div class="col-md-3"><div class="admin-card text-center"><h6 class="mb-1">Pedidos activos</h6><p class="fs-3 mb-0">{{ metrics.pedidos_activos }}</p></div></div>
    <div class="col-md-3"><div class="admin-card text-center"><h6 class="mb-1">Reservas confirmadas</h6><p class="fs-3 mb-0">{{ metrics.reservas_confirmadas }}</p></div></div>
    <div class="col-md-3"><div class="admin-card text-center"><h6 class="mb-1">Ingresos estimados</h6><p class="fs-3 mb-0">{{ metrics.ingresos_txt }}</p></div></div>
  </div>

  <!-- GRÁFICAS -->
  <div class="row g-3 mt-1">
    <div class="col-lg-4 col-md-12">
      <div class="chart-card">
        <h6 class="mb-3">Usuarios nuevos • últimos 6 meses</h6>
        <canvas id="chartUsuarios"></canvas>
      </div>
    </div>
    <div class="col-lg-4 col-md-12">
      <div class="chart-card">
        <h6 class="mb-3">Solicitudes por estado</h6>
        <canvas id="chartEstados"></canvas>
      </div>
    </div>
    <div class="col-lg-4 col-md-12">
      <div class="chart-card">
        <h6 class="mb-3">Solicitudes por mes • últimos 6 meses</h6>
        <canvas id="chartSolicitudesMes"></canvas>
      </div>
    </div>
  </div>
</div>

<!-- USUARIOS -->
<div class="container mt-4" id="usuarios" style="display:none;">
  <h4>👤 Lista de Usuarios</h4>
  <div class="table-responsive">
    <table class="table table-bordered mt-3 align-middle">
      <thead>
        <tr><th>ID</th><th>Nombre</th><th>Email</th><th>Rol</th><th>País</th><th>Registro</th></tr>
      </thead>
      <tbody id="tablaUsuariosBody">
        {% for u in usuarios %}
        <tr data-id="{{ u.id }}">
          <td>{{ u.id }}</td>
          <td class="col-nombre">{{ u.nombre }}</td>
          <td class="col-email">{{ u.email }}</td>
          <td class="col-rol"><span class="badge {{ 'bg-success' if u.rol=='admin' else 'bg-secondary' }}">{{ u.rol }}</span></td>
          <td class="col-pais">{{ u.pais_residencia or '-' }}</td>
          <td>{{ u.fecha_registro }}</td>
        </tr>
        {% else %}
        <tr><td colspan="6" class="text-center text-muted">Sin registros</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<!-- PEDIDOS (solicitudes_viaje) -->
<div class="container mt-4" id="pedidos" style="display:none;">
  <h4>📦 Historial de Pedidos</h4>
  <div class="table-responsive">
    <table class="table table-striped mt-3 align-middle">
      <thead>
        <tr>
          <th>ID Pedido</th><th>Cliente</th><th>Destino</th><th>Tipo</th><th>Fecha solicitud</th><th>Estado</th>
        </tr>
      </thead>
      <tbody>
        {% for p in pedidos %}
        <tr>
          <td>{{ p.id }}</td>
          <td>{{ p.cliente }}</td>
          <td>{{ p.pais_destino }}</td>
          <td>{{ p.tipo_viaje or '-' }}</td>
          <td>{{ p.fecha_solicitud }}</td>
          <td>
            {% if p.estado == 'pendiente' %}
              <span class="badge bg-warning text-dark">Pendiente</span>
            {% elif p.estado == 'atendida' %}
              <span class="badge bg-info text-dark">Atendida</span>
            {% elif p.estado == 'cancelada' %}
              <span class="badge bg-danger">Cancelada</span>
            {% else %}
              <span class="badge bg-secondary">{{ p.estado }}</span>
            {% endif %}
          </td>
        </tr>
        {% else %}
        <tr><td colspan="6" class="text-center text-muted">Sin registros</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <p class="text-muted small">* Los “pedidos” corresponden a <strong>solicitudes_viaje</strong>.</p>
</div>

<!-- CONFIGURACIÓN (Editar usuarios + Reset contraseña) -->
<div class="container mt-4" id="config" style="display:none;">
  <h4>⚙️ Configuración de Usuarios</h4>
  <div class="form-section mt-3">
    <div class="row g-3">
      <div class="col-lg-4">
        <label class="form-label">Usuario</label>
        <select id="selUsuario" class="form-select">
          <option value="">— Selecciona —</option>
          {% for u in usuarios %}
            <option value="{{ u.id }}">{{ u.id }} — {{ u.nombre }} ({{ u.email }})</option>
          {% endfor %}
        </select>
      </div>
      <div class="col-lg-4">
        <label class="form-label">Nombre</label>
        <input id="inpNombre" type="text" class="form-control" placeholder="Nombre completo">
      </div>
      <div class="col-lg-4">
        <label class="form-label">Email</label>
        <input id="inpEmail" type="email" class="form-control" placeholder="correo@dominio.com">
      </div>

      <div class="col-lg-4">
        <label class="form-label">Rol</label>
        <select id="inpRol" class="form-select">
          <option value="cliente">cliente</option>
          <option value="admin">admin</option>
        </select>
      </div>
      <div class="col-lg-4">
        <label class="form-label">País de residencia</label>
        <input id="inpPais" type="text" class="form-control" placeholder="México, EUA, ...">
      </div>
      <div class="col-lg-4 d-flex align-items-end">
        <button id="btnGuardar" class="btn btn-dark w-100">Guardar cambios</button>
      </div>
    </div>

    <hr class="my-4">

    <div class="row g-3">
      <div class="col-lg-4">
        <label class="form-label">Nueva contraseña</label>
        <div class="input-group">
          <input id="inpPass" type="password" class="form-control" placeholder="Mínimo 6 caracteres">
          <button class="btn btn-outline-secondary" type="button" id="btnVerPass">👁️</button>
        </div>
      </div>
      <div class="col-lg-4">
        <label class="form-label">Confirmar contraseña</label>
        <input id="inpPass2" type="password" class="form-control" placeholder="Repite la contraseña">
      </div>
      <div class="col-lg-4 d-flex align-items-end gap-2">
        <button id="btnGenPass" class="btn btn-secondary w-50" type="button">Generar temporal</button>
        <button id="btnGuardarPass" class="btn btn-danger w-50" type="button">Restablecer contraseña</button>
      </div>
    </div>

    <div id="alerta" class="alert mt-3 d-none" role="alert"></div>
  </div>

  <p class="text-muted small mt-2">Los cambios se guardan en la base de datos y se reflejan en la tabla de Usuarios.</p>
</div>

<!-- SOLICITUDES -->
<div class="container mt-4" id="solicitudes" style="display:none;">
  <h4>📝 Reservas de Clientes</h4>
  <div class="table-responsive">
    <table class="table table-striped mt-3 align-middle">
      <thead>
        <tr>
          <th>ID</th>
          <th>Cliente</th>
          <th>Email</th>
          <th>Destino</th>
          <th>Estado</th>
          <th>Fecha</th>
          <th>Acciones</th>
        </tr>
      </thead>
      <tbody>
        {% for s in solicitudes %}
        <tr>
          <td>{{ s.id }}</td>
          <td>{{ s.cliente }} (Rol: {{ s.rol }})</td>
          <td>{{ s.email }}</td>
          <td>{{ s.destino or '-' }}</td>
          <td>
            {% if s.estado == 'pendiente' %}
              <span class="badge bg-warning text-dark">Pendiente</span>
            {% else %}
              <span class="badge bg-secondary">{{ s.estado }}</span>
            {% endif %}
          </td>
          <td>{{ s.created_at }}</td>
          <td>
            <a href="/admin/solicitud/{{ s.id }}" class="btn btn-sm btn-primary">
              <i class="fas fa-eye"></i> Ver Detalles
            </a>
          </td>
        </tr>
        {% else %}
        <tr><td colspan="7" class="text-center text-muted">No hay reservas registradas</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>


<!-- Modal Cerrar Sesión -->
<div class="modal fade" id="modalCerrarSesion" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered"><div class="modal-content">
    <div class="modal-header"><h5 class="modal-title">¿Cerrar sesión?</h5></div>
    <div class="modal-body text-center">
      <img src="https://cdn-icons-png.flaticon.com/512/463/463612.png" width="80"><br><br>
      ¿Estás seguro de que deseas cerrar sesión?
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
      <button class="btn btn-danger" onclick="cerrarSesion()">Sí, cerrar sesión</button>
    </div>
  </div></div>
</div>

<div class="main-footer">
  <div class="footer-left">México · Español (MX) · MXN</div>
  <div class="footer-column">
    <ul><li>Ayuda</li><li>Configuración de privacidad</li><li>Iniciar sesión</li></ul>
  </div>
  <div class="footer-column">
    <ul><li>Política de cookies</li><li>Política de privacidad</li><li>Términos de servicio</li><li>Información de la empresa</li></ul>
  </div>
  <div class="footer-column">
    <ul><li>Explorar</li><li>Compañía</li><li>Partners</li><li>Viajes</li><li>Sitios internacionales</li></ul>
  </div>
</div>

<footer class="copyright">© 2025 YoungSky – Tu aventura comienza aquí ✈️</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script>
  // Mostrar secciones
  function mostrarSeccion(id) {
    document.getElementById("panel").style.display = "none";
    document.getElementById("usuarios").style.display = "none";
    document.getElementById("pedidos").style.display = "none";
    document.getElementById("config").style.display = "none";
     document.getElementById("solicitudes").style.display = "none";
    document.getElementById(id).style.display = "block";
  }
  function mostrarModalCerrarSesion() {
    var modal = new bootstrap.Modal(document.getElementById('modalCerrarSesion'));
    modal.show();
  }
  function cerrarSesion() {
    fetch("/admin/logout", { method: "POST" }).then(() => {
      window.location.href = "/";
    });
  }

  // ====== DATA PARA CHARTS (inyectada por Jinja) ======
  const USUARIOS_LABELS = {{ series.usuarios.labels|tojson }};
  const USUARIOS_DATA   = {{ series.usuarios.data|tojson }};

  const ESTADO_LABELS = {{ series.solicitudes_estado.labels|tojson }};
  const ESTADO_DATA   = {{ series.solicitudes_estado.data|tojson }};

  const SOLMES_LABELS = {{ series.solicitudes_mes.labels|tojson }};
  const SOLMES_DATA   = {{ series.solicitudes_mes.data|tojson }};

  // ====== CHARTS ======
  document.addEventListener("DOMContentLoaded", () => {
    const nFormatter = (v) => new Intl.NumberFormat('es-MX').format(v || 0);

    // Usuarios nuevos (línea)
    const ctxU = document.getElementById('chartUsuarios').getContext('2d');
    new Chart(ctxU, {
      type: 'line',
      data: {
        labels: USUARIOS_LABELS,
        datasets: [{
          label: 'Usuarios',
          data: USUARIOS_DATA,
          tension: 0.3,
          fill: false
        }]
      },
      options: {
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => ` ${nFormatter(c.parsed.y)} usuarios` } }
        },
        scales: {
          y: { beginAtZero: true, ticks: { callback: (v)=> nFormatter(v) } }
        }
      }
    });

    // Solicitudes por estado (doughnut)
    const ctxE = document.getElementById('chartEstados').getContext('2d');
    new Chart(ctxE, {
      type: 'doughnut',
      data: { labels: ESTADO_LABELS, datasets: [{ data: ESTADO_DATA }] },
      options: {
        plugins: {
          legend: { position: 'bottom' },
          tooltip: { callbacks: { label: (c)=> ` ${c.label}: ${nFormatter(c.parsed)}` } }
        },
        cutout: '60%'
      }
    });

    // Solicitudes por mes (barras)
    const ctxM = document.getElementById('chartSolicitudesMes').getContext('2d');
    new Chart(ctxM, {
      type: 'bar',
      data: {
        labels: SOLMES_LABELS,
        datasets: [{ label: 'Solicitudes', data: SOLMES_DATA }]
      },
      options: {
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c)=> ` ${nFormatter(c.parsed.y)} solicitudes` } }
        },
        scales: {
          y: { beginAtZero: true, ticks: { callback: (v)=> nFormatter(v) } }
        }
      }
    });
  });

  // ====== CONFIGURACIÓN: EDITAR USUARIO ======
  const USERS = {{ usuarios|tojson }};
  const selUsuario = document.getElementById('selUsuario');
  const inpNombre  = document.getElementById('inpNombre');
  const inpEmail   = document.getElementById('inpEmail');
  const inpRol     = document.getElementById('inpRol');
  const inpPais    = document.getElementById('inpPais');
  const alerta     = document.getElementById('alerta');

  function setAlert(tipo, msg) {
    alerta.className = 'alert mt-3 alert-' + tipo;
    alerta.textContent = msg;
  }

  selUsuario && selUsuario.addEventListener('change', () => {
    const id = parseInt(selUsuario.value || '0', 10);
    const u = USERS.find(x => x.id === id);
    if (u) {
      inpNombre.value = u.nombre || '';
      inpEmail.value  = u.email || '';
      inpRol.value    = (u.rol === 'admin') ? 'admin' : 'cliente';
      inpPais.value   = u.pais_residencia || '';
      alerta.classList.add('d-none');
    } else {
      inpNombre.value = '';
      inpEmail.value  = '';
      inpRol.value    = 'cliente';
      inpPais.value   = '';
      alerta.classList.add('d-none');
    }
  });

  document.getElementById('btnGuardar')?.addEventListener('click', async () => {
    const id = parseInt(selUsuario.value || '0', 10);
    const nombre = inpNombre.value.trim();
    const email  = inpEmail.value.trim();
    const rol    = inpRol.value;
    const pais   = inpPais.value.trim();

    if (!id) { setAlert('warning', 'Selecciona un usuario.'); return; }
    if (!nombre) { setAlert('warning', 'El nombre es obligatorio.'); return; }
    if (!email || !/^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/.test(email)) { setAlert('warning', 'Email inválido.'); return; }
    if (!['cliente','admin'].includes(rol)) { setAlert('warning', 'Rol inválido.'); return; }

    try {
      const res = await fetch('/admin/usuarios/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, nombre, email, rol, pais_residencia: pais })
      });
      const data = await res.json();

      if (!res.ok || !data.ok) {
        setAlert('danger', data.error || 'No se pudo guardar.');
        return;
      }

      // Actualizar cache local y tabla de "Usuarios"
      const idx = USERS.findIndex(x => x.id === id);
      if (idx !== -1) {
        USERS[idx].nombre = nombre;
        USERS[idx].email  = email;
        USERS[idx].rol    = rol;
        USERS[idx].pais_residencia = pais;
      }

      const fila = document.querySelector(`#tablaUsuariosBody tr[data-id="${id}"]`);
      if (fila) {
        fila.querySelector('.col-nombre').textContent = nombre;
        fila.querySelector('.col-email').textContent  = email;
        fila.querySelector('.col-pais').textContent   = pais || '-';
        const tdRol = fila.querySelector('.col-rol');
        tdRol.innerHTML = '';
        const span = document.createElement('span');
        span.className = 'badge ' + (rol === 'admin' ? 'bg-success' : 'bg-secondary');
        span.textContent = rol;
        tdRol.appendChild(span);
      }

      setAlert('success', 'Cambios guardados correctamente.');
    } catch (e) {
      setAlert('danger', 'Error de red al guardar.');
    }
  });

  // ====== CONFIGURACIÓN: RESETEAR CONTRASEÑA ======
  const inpPass  = document.getElementById('inpPass');
  const inpPass2 = document.getElementById('inpPass2');
  const btnVerPass = document.getElementById('btnVerPass');
  const btnGenPass = document.getElementById('btnGenPass');
  const btnGuardarPass = document.getElementById('btnGuardarPass');

  function genPassword(len = 12) {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%^&*?';
    let p = '';
    for (let i = 0; i < len; i++) {
      p += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return p;
  }

  btnGenPass?.addEventListener('click', () => {
    const p = genPassword();
    inpPass.value  = p;
    inpPass2.value = p;
    setAlert('info', 'Se generó una contraseña temporal. Recuerda comunicarla al usuario.');
  });

  btnVerPass?.addEventListener('click', () => {
    const t = inpPass.type === 'password' ? 'text' : 'password';
    inpPass.type = t;
    inpPass2.type = t;
  });

  btnGuardarPass?.addEventListener('click', async () => {
    const id = parseInt(selUsuario.value || '0', 10);
    const p1 = (inpPass.value || '').trim();
    const p2 = (inpPass2.value || '').trim();

    if (!id) { setAlert('warning', 'Selecciona un usuario.'); return; }
    if (p1.length < 6) { setAlert('warning', 'La contraseña debe tener al menos 6 caracteres.'); return; }
    if (p1 !== p2) { setAlert('warning', 'Las contraseñas no coinciden.'); return; }

    if (!confirm('¿Confirmas restablecer la contraseña de este usuario?')) return;

    try {
      const res = await fetch('/admin/usuarios/reset_password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, nueva_contrasena: p1 })
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        setAlert('danger', data.error || 'No se pudo restablecer la contraseña.');
        return;
      }
      setAlert('success', 'Contraseña restablecida correctamente.');
      inpPass.value = '';
      inpPass2.value = '';
    } catch (e) {
      setAlert('danger', 'Error de red al restablecer contraseña.');
    }
  });
</script>

</body>
</html>
'''
html_detalles_solicitud = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Detalles de Reserva - YoungSky Admin</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" rel="stylesheet">
  <style>
    body { font-family: 'Segoe UI', sans-serif; background-color: #f8f9fa; }
    .navbar { background-color: #0a5b5e; }
    .card { border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); border: none; }
    .detail-card { background: white; padding: 25px; margin-bottom: 20px; }
    .detail-section { margin-bottom: 25px; padding-bottom: 20px; border-bottom: 1px solid #eee; }
    .detail-label { font-weight: 600; color: #555; margin-bottom: 5px; }
    .detail-value { font-size: 1.1rem; color: #333; }
    .badge-status { font-size: 0.9rem; padding: 8px 12px; border-radius: 20px; }
    .comprobante-preview { max-width: 100%; max-height: 200px; border: 2px dashed #ddd; padding: 10px; }
  </style>
</head>
<body>

<nav class="navbar navbar-dark navbar-expand-lg px-4">
  <a class="navbar-brand" href="/admin/dashboard">YoungSKY Admin</a>
  <div class="collapse navbar-collapse">
    <ul class="navbar-nav me-auto">
      <li class="nav-item"><a class="nav-link" href="/admin/dashboard">Dashboard</a></li>
      <li class="nav-item"><a class="nav-link" href="/admin/dashboard#solicitudes">Solicitudes</a></li>
    </ul>
  </div>
</nav>

<div class="container my-4">
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h2>📋 Detalles de la Reserva #{{ solicitud.id }}</h2>
    <a href="/admin/dashboard#solicitudes" class="btn btn-secondary">
      <i class="fas fa-arrow-left"></i> Volver a Solicitudes
    </a>
  </div>

  <div class="row">
    <div class="col-lg-8">
      <!-- Información del Cliente -->
      <div class="card detail-card">
        <h4 class="mb-4"><i class="fas fa-user"></i> Información del Cliente</h4>
        <div class="row">
          <div class="col-md-6 detail-section">
            <div class="detail-label">Nombre</div>
            <div class="detail-value">{{ solicitud.cliente_nombre or 'No disponible' }}</div>
          </div>
          <div class="col-md-6 detail-section">
            <div class="detail-label">Email</div>
            <div class="detail-value">{{ solicitud.cliente_email or 'No disponible' }}</div>
          </div>
          <div class="col-md-6">
            <div class="detail-label">Rol</div>
            <div class="detail-value">
              <span class="badge {{ 'bg-success' if solicitud.cliente_rol=='admin' else 'bg-secondary' }} badge-status">
                {{ solicitud.cliente_rol or 'cliente' }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Detalles del Vuelo -->
      <div class="card detail-card">
        <h4 class="mb-4"><i class="fas fa-plane"></i> Detalles del Vuelo</h4>
        <div class="row">
          <div class="col-md-6 detail-section">
            <div class="detail-label">Origen</div>
            <div class="detail-value">{{ solicitud.origen or 'No especificado' }}</div>
          </div>
          <div class="col-md-6 detail-section">
            <div class="detail-label">Destino</div>
            <div class="detail-value">{{ solicitud.destino or 'No especificado' }}</div>
          </div>
          <div class="col-md-6 detail-section">
            <div class="detail-label">Fecha de Salida</div>
            <div class="detail-value">{{ solicitud.salida or 'No especificada' }}</div>
          </div>
          <div class="col-md-6 detail-section">
            <div class="detail-label">Fecha de Regreso</div>
            <div class="detail-value">{{ solicitud.regreso or 'Vuelo sencillo' }}</div>
          </div>
          <div class="col-md-6">
            <div class="detail-label">Clase</div>
            <div class="detail-value">{{ solicitud.clase or 'ECONOMY' }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="col-lg-4">
      <!-- Información de la Reserva -->
      <div class="card detail-card">
        <h4 class="mb-4"><i class="fas fa-receipt"></i> Información de la Reserva</h4>
        
        <div class="detail-section">
          <div class="detail-label">Estado Actual</div>
          <div class="detail-value">
            {% if solicitud.estado == 'pendiente' %}
              <span class="badge bg-warning text-dark badge-status">Pendiente</span>
            {% elif solicitud.estado == 'completada' %}
              <span class="badge bg-success badge-status">Completada</span>
            {% else %}
              <span class="badge bg-secondary badge-status">{{ solicitud.estado }}</span>
            {% endif %}
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">Fecha de Creación</div>
          <div class="detail-value">{{ solicitud.created_at or 'No disponible' }}</div>
        </div>

        <div class="detail-section">
          <div class="detail-label">Número de Boletos</div>
          <div class="detail-value">{{ solicitud.boletos or 1 }}</div>
        </div>

        <div class="detail-section">
          <div class="detail-label">Servicios Adicionales</div>
          <div class="detail-value">
            {% if solicitud.seguro %}
              <span class="badge bg-info">Seguro de Viaje</span>
            {% endif %}
            {% if solicitud.transporte %}
              <span class="badge bg-secondary">Transporte Aeropuerto</span>
            {% endif %}
            {% if not solicitud.seguro and not solicitud.transporte %}
              Ninguno
            {% endif %}
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">Precio Total</div>
          <div class="detail-value h4 text-primary">
            {{ solicitud.moneda or 'MXN' }} {{ solicitud.precio or '0.00' }}
          </div>
        </div>

        <!-- Comprobante existente -->
        {% if solicitud.comprobante %}
        <div class="detail-section">
          <div class="detail-label">Comprobante Actual</div>
          <div class="detail-value">
            <a href="/uploads/comprobantes/{{ solicitud.comprobante }}" target="_blank" class="btn btn-sm btn-outline-primary">
              <i class="fas fa-download"></i> Ver Comprobante
            </a>
          </div>
        </div>
        {% endif %}

        <!-- Formulario para subir comprobante -->
        <div class="detail-section">
          <div class="detail-label">Subir Comprobante</div>
          <form id="comprobanteForm" enctype="multipart/form-data">
            <div class="mb-2">
              <input type="file" id="comprobanteFile" accept="image/*,.pdf" class="form-control" required>
            </div>
            <div id="previewContainer" class="text-center mb-2" style="display: none;">
              <img id="previewImage" class="comprobante-preview" src="">
            </div>
            <button type="button" class="btn btn-info w-100" onclick="subirComprobante()">
              <i class="fas fa-upload"></i> Subir Comprobante
            </button>
          </form>
        </div>

        <!-- Botón para completar reserva -->
        {% if solicitud.estado == 'pendiente' %}
        <div class="text-center mt-4">
          <form id="completarForm" method="POST" action="/admin/completar_solicitud/{{ solicitud.id }}">
            <button type="button" class="btn btn-success btn-lg w-100" onclick="completarReserva()">
              <i class="fas fa-check-circle"></i> Completar Reserva
            </button>
          </form>
        </div>
        {% endif %}
      </div>
    </div>
  </div>
</div>

<script>
// Preview de imagen seleccionada
document.getElementById('comprobanteFile').addEventListener('change', function(e) {
  const file = e.target.files[0];
  const previewContainer = document.getElementById('previewContainer');
  const previewImage = document.getElementById('previewImage');
  
  if (file && file.type.startsWith('image/')) {
    const reader = new FileReader();
    reader.onload = function(e) {
      previewImage.src = e.target.result;
      previewContainer.style.display = 'block';
    }
    reader.readAsDataURL(file);
  } else {
    previewContainer.style.display = 'none';
  }
});

function subirComprobante() {
  const fileInput = document.getElementById('comprobanteFile');
  const file = fileInput.files[0];
  
  if (!file) {
    alert('Por favor selecciona un archivo');
    return;
  }
  
  const formData = new FormData();
  formData.append('comprobante', file);
  
  // Mostrar loading
  const btn = document.querySelector('#comprobanteForm button');
  const originalText = btn.innerHTML;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Subiendo...';
  btn.disabled = true;
  
  fetch('/admin/subir_comprobante/{{ solicitud.id }}', {
    method: 'POST',
    body: formData
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert('Comprobante subido exitosamente');
      window.location.reload();
    } else {
      alert('Error: ' + (data.error || 'No se pudo subir el comprobante'));
    }
  })
  .catch(error => {
    alert('Error de conexión');
  })
  .finally(() => {
    btn.innerHTML = originalText;
    btn.disabled = false;
  });
}

function completarReserva() {
  if (confirm('¿Estás seguro de que deseas marcar esta reserva como COMPLETADA? El cliente podrá ver este cambio.')) {
    // Mostrar loading
    const btn = document.querySelector('#completarForm button');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Procesando...';
    btn.disabled = true;
    
    // Enviar formulario via AJAX
    fetch('/admin/completar_solicitud/{{ solicitud.id }}', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        alert('Reserva completada exitosamente');
        window.location.reload();
      } else {
        alert('Error: ' + (data.error || 'No se pudo completar la reserva'));
        btn.innerHTML = originalText;
        btn.disabled = false;
      }
    })
    .catch(error => {
      alert('Error de conexión');
      btn.innerHTML = originalText;
      btn.disabled = false;
    });
  }
}
</script>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""



@admin_bp.route("/dashboard")
def dashboard():
    if session.get("rol") != "admin":
        return redirect(url_for("login.mostrar_login"))

    try:
        conn = get_conn()
        metrics = fetch_metrics(conn)
        usuarios = fetch_usuarios(conn)
        pedidos = fetch_pedidos(conn)
        series = fetch_series(conn, meses=6)
        
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    r.id,
                    r.destino,
                    r.estado,
                    r.created_at,
                    r.usuario_id,
                    COALESCE(u.nombre, CONCAT('Usuario #', r.usuario_id)) AS cliente,
                    COALESCE(u.email, 'No disponible') AS email,
                    u.rol  -- Mostrar también el rol para debug
                FROM reservas r
                LEFT JOIN usuarios u ON u.id = r.usuario_id
                ORDER BY r.created_at DESC
            """)
            solicitudes = cur.fetchall()
    except Exception as e:
        print(f"Error obteniendo datos: {e}")
        solicitudes = []
        metrics = {"usuarios": 0, "pedidos_activos": 0, "reservas_confirmadas": 0, "ingresos_txt": "$0.00"}
        usuarios = []
        pedidos = []
        series = {"usuarios": {"labels": [], "data": []}, "solicitudes_estado": {"labels": [], "data": []}, "solicitudes_mes": {"labels": [], "data": []}}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return render_template_string(
        html_admin_dashboard,
        metrics=metrics,
        usuarios=usuarios,
        pedidos=pedidos,
        solicitudes=solicitudes, 
        series=series
    )


@admin_bp.route("/usuarios/update", methods=["POST"])
def actualizar_usuario():
    # Solo admins
    if session.get("rol") != "admin":
        return jsonify({"ok": False, "error": "No autorizado"}), 403

    data = request.get_json(silent=True) or {}
    user_id = data.get("id")
    nombre = (data.get("nombre") or "").strip()
    email = (data.get("email") or "").strip()
    rol = (data.get("rol") or "").strip()
    pais = (data.get("pais_residencia") or "").strip()

    if not user_id or not nombre or not email or rol not in ("cliente","admin"):
        return jsonify({"ok": False, "error": "Datos inválidos"}), 400

    try:
        conn = get_conn()
        with conn.cursor() as c:
            c.execute("""
                UPDATE usuarios
                   SET nombre=%s,
                       email=%s,
                       rol=%s,
                       pais_residencia=%s
                 WHERE id=%s;
            """, (nombre, email, rol, pais if pais else None, user_id))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return jsonify({"ok": True})

@admin_bp.route("/usuarios/reset_password", methods=["POST"])
def reset_password():
    # Solo admins
    if session.get("rol") != "admin":
        return jsonify({"ok": False, "error": "No autorizado"}), 403

    data = request.get_json(silent=True) or {}
    user_id = data.get("id")
    nueva = (data.get("nueva_contrasena") or "").strip()

    if not user_id or len(nueva) < 6:
        return jsonify({"ok": False, "error": "Contraseña inválida"}), 400

    # Decide cómo guardar: texto plano o hash
    valor_guardar = nueva
    if USE_HASH:
        if generate_password_hash is None:
            return jsonify({"ok": False, "error": "Falta soporte de hashing (werkzeug)"}), 500
        valor_guardar = generate_password_hash(nueva, method="pbkdf2:sha256", salt_length=16)

    try:
        conn = get_conn()
        with conn.cursor() as c:
            c.execute("""
                UPDATE usuarios
                   SET contrasena_hash=%s
                 WHERE id=%s;
            """, (valor_guardar, user_id))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return jsonify({"ok": True})

@admin_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return ("", 204)

@admin_bp.route("/solicitudes")
def solicitudes():
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # Obtener todas las solicitudes pendientes (reservas no completadas)
            cur.execute("SELECT * FROM reservas WHERE estado = 'pendiente' ORDER BY created_at DESC")
            solicitudes = cur.fetchall()
        return render_template("admin/solicitudes.html", solicitudes=solicitudes)
    except Exception as e:
        print(f"Error al cargar solicitudes: {e}")
        return render_template("admin/solicitudes.html", solicitudes=[])
    
@admin_bp.route("/completar_reserva/<int:id>", methods=["POST"])
def completar_reserva(id):
    try:
        # Aquí manejarás el archivo adjunto
        if 'evidencia' not in request.files:
            return redirect(url_for("admin.solicitudes"))

        evidencia = request.files['evidencia']
        if evidencia.filename == '':
            return redirect(url_for("admin.solicitudes"))

        # Guardar evidencia (en la carpeta 'uploads')
        filename = secure_filename(evidencia.filename)
        evidencia.save(os.path.join('uploads', filename))

        # Actualizar estado de la solicitud a 'completada'
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE reservas 
                SET estado = 'completada', evidencia = %s 
                WHERE id = %s
            """, (filename, id))
            conn.commit()

        return redirect(url_for("admin.solicitudes"))
    except Exception as e:
        print(f"Error al completar reserva: {e}")
        return redirect(url_for("admin.solicitudes"))
        

@admin_bp.route("/solicitud/<int:id>")
def ver_solicitud(id):
    if session.get("rol") != "admin":
        return redirect(url_for("login.mostrar_login"))
    
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # Obtener detalles completos de la reserva con mejor formato
            cur.execute("""
                SELECT 
                    r.*,
                    u.nombre as cliente_nombre,
                    u.email as cliente_email,
                    u.rol as cliente_rol,
                    DATE_FORMAT(r.created_at, '%%Y-%%m-%%d %%H:%%i:%%s') as created_at_formatted,
                    DATE_FORMAT(r.salida, '%%Y-%%m-%%d %%H:%%i') as salida_formatted,
                    DATE_FORMAT(r.regreso, '%%Y-%%m-%%d %%H:%%i') as regreso_formatted
                FROM reservas r
                LEFT JOIN usuarios u ON u.id = r.usuario_id
                WHERE r.id = %s
            """, (id,))
            solicitud = cur.fetchone()
            
            if not solicitud:
                return "Reserva no encontrada", 404
                
            # Formatear datos para mejor visualización
            if solicitud.get('salida_formatted'):
                solicitud['salida'] = solicitud['salida_formatted']
            if solicitud.get('regreso_formatted'):
                solicitud['regreso'] = solicitud['regreso_formatted']
            if solicitud.get('created_at_formatted'):
                solicitud['created_at'] = solicitud['created_at_formatted']
                
    except Exception as e:
        print(f"Error obteniendo detalles de reserva: {e}")
        return "Error al cargar la reserva", 500
    finally:
        try:
            conn.close()
        except Exception:
            pass
    
    return render_template_string(html_detalles_solicitud, solicitud=solicitud)

@admin_bp.route("/completar_solicitud/<int:id>", methods=["POST"])
def completar_solicitud(id):
    if session.get("rol") != "admin":
        return jsonify({"success": False, "error": "No autorizado"}), 403
    
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # Actualizar estado a completada
            cur.execute("""
                UPDATE reservas 
                SET estado = 'completada'
                WHERE id = %s
            """, (id,))
            conn.commit()
            
        return jsonify({"success": True, "message": "Reserva completada exitosamente"})
        
    except Exception as e:
        print(f"Error completando reserva: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass
        
@admin_bp.route("/uploads/comprobantes/<filename>")
def servir_comprobante(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@admin_bp.route("/subir_comprobante/<int:id>", methods=["POST"])
def subir_comprobante(id):
    if session.get("rol") != "admin":
        return jsonify({"success": False, "error": "No autorizado"}), 403
    
    if 'comprobante' not in request.files:
        return jsonify({"success": False, "error": "No se seleccionó archivo"}), 400
    
    file = request.files['comprobante']
    if file.filename == '':
        return jsonify({"success": False, "error": "No se seleccionó archivo"}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"comprobante_{id}_{file.filename}")
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        try:
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE reservas 
                    SET comprobante = %s
                    WHERE id = %s
                """, (filename, id))
                conn.commit()
                
            return jsonify({"success": True, "message": "Comprobante subido exitosamente"})
            
        except Exception as e:
            print(f"Error guardando comprobante: {e}")
            return jsonify({"success": False, "error": "Error al guardar en BD"}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass
    
    return jsonify({"success": False, "error": "Tipo de archivo no permitido"}), 400

@admin_bp.route("/comprobantes/<filename>")
def servir_comprobante_cliente(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)