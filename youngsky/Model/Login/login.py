from flask import Blueprint, request, jsonify, render_template_string, session
import mysql.connector


login_bp = Blueprint('login', __name__)

# Configuración base de datos
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'youngsky'
}

try:
    with open("estilos.css", "r", encoding="utf-8") as f:
        estilo_css = f.read()
except Exception:
    estilo_css = """
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; background:#f7f7f9; }
    .container{ max-width:960px; margin:40px auto; background:#fff; border-radius:16px; box-shadow:0 8px 24px rgba(0,0,0,.08); overflow:hidden; display:flex; }
    .form-container{ flex:1; padding:40px; }
    .toggle-container{ width:40%; background:#0d6efd; color:#fff; display:flex; align-items:center; justify-content:center; }
    input, button{ width:100%; padding:12px 14px; margin-top:10px; border-radius:10px; border:1px solid #ddd; }
    button{ border:0; background:#0d6efd; color:#fff; cursor:pointer; }
    button.hidden{ background:transparent; border:1px solid #fff; }
    .social-icons{ display:flex; gap:8px; margin:8px 0 16px; }
    .social-icons .icon{ display:inline-flex; width:36px; height:36px; align-items:center; justify-content:center; border:1px solid #ddd; border-radius:50%; color:#333; }
    .toggle{ padding:40px; text-align:center; }
    .toggle h1{ margin:0 0 8px; }
    /* animación simple del panel */
    #container.active .sign-in{ display:none; }
    #container.active .sign-up{ display:block; }
    #container .sign-up{ display:none; }
    """

# Vista HTML embebida
login_html = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YoungSKY - Login</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
    <style>{{ estilo }}</style>
</head>
<body>
    <div class="container" id="container">

        <!-- Sign In -->
        <div class="form-container sign-in">
            <form id="loginForm">
                <h1>Iniciar Sesión</h1>
                <div class="social-icons">
                    <a href="#" class="icon"><i class="fa-brands fa-google-plus-g"></i></a>
                    <a href="#" class="icon"><i class="fa-brands fa-facebook-f"></i></a>
                    <a href="#" class="icon"><i class="fa-brands fa-github"></i></a>
                    <a href="#" class="icon"><i class="fa-brands fa-linkedin-in"></i></a>
                </div>
                <span>o utiliza tu contraseña de correo electrónico</span>
                <input type="email" placeholder="Email" id="email" required>
                <input type="password" placeholder="Password" id="password" required>
                <a href="#">¿Olvidaste tu contraseña?</a>
                <p id="message" style="margin-top: 10px;"></p>
                <button type="submit">Sign In</button>
            </form>
        </div>

        <!-- Panel derecho con toggle + Sign Up -->
        <div class="toggle-container">
            <div class="toggle">
                <div class="toggle-panel toggle-left">
                    <h1>YoungSKY</h1>
                    <p>Regístrate o inicia sesión para usar todas las funciones.</p>
                    <button class="hidden" id="register">Sign Up</button>
                    <button class="hidden" id="login">Sign In</button>
                </div>
                <div class="form-container sign-up" style="margin-top:20px;">
                    <form id="signupForm">
                        <h1>Crear Cuenta</h1>
                        <span>o usa un email para registrarte</span>
                        <input type="text" id="su_nombre" placeholder="Nombre" required>
                        <input type="email" id="su_email" placeholder="Email" required>
                        <input type="password" id="su_password" placeholder="Password" required>
                        <input type="text" id="su_pais" placeholder="País de residencia (opcional)">
                        <button type="submit">Sign Up</button>
                        <p id="signup_msg" style="margin-top:10px;"></p>
                    </form>
                </div>
            </div>
        </div>
    </div>

    <!-- JS (sin scripts anidados) -->
    <script>
    const container = document.getElementById('container');
    const registerBtn = document.getElementById('register');
    const loginBtn = document.getElementById('login');

    // Mostrar/ocultar panel de registro
    registerBtn.addEventListener('click', () => container.classList.add("active"));
    loginBtn.addEventListener('click', () => container.classList.remove("active"));

    // Login
    document.getElementById("loginForm").addEventListener("submit", async function (e) {
        e.preventDefault();
        const email = document.getElementById("email").value.trim();
        const password = document.getElementById("password").value;

        const response = await fetch("/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });

        const data = await response.json();
        const msg = document.getElementById("message");

        if (response.ok) {
            msg.style.color = "green";
            msg.innerText = `¡Bienvenido ${data.nombre}! Rol: ${data.rol}`;
            if (data.rol === 'admin') {
                window.location.href = '/admin/dashboard';
            } else {
                window.location.href = '/cliente/dashboard';
            }
        } else {
            msg.style.color = "red";
            msg.innerText = data.error || "Error desconocido";
        }
    });

    // Sign Up
    document.getElementById("signupForm").addEventListener("submit", async function(e){
        e.preventDefault();
        const nombre = document.getElementById("su_nombre").value.trim();
        const email = document.getElementById("su_email").value.trim();
        const password = document.getElementById("su_password").value;
        const pais_residencia = document.getElementById("su_pais").value.trim();
        const msg = document.getElementById("signup_msg");

        try {
            const resp = await fetch("/registrar", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    nombre, email, password,
                    pais_residencia, rol: "cliente"
                })
            });

            const data = await resp.json();
            if (resp.ok) {
                msg.style.color = "green";
                msg.textContent = "Usuario registrado. Ahora puedes iniciar sesión.";
                // Cambiar a la vista de login
                container.classList.remove("active");
            } else {
                msg.style.color = "red";
                msg.textContent = data.error || "No se pudo registrar.";
            }
        } catch (err) {
            msg.style.color = "red";
            msg.textContent = "Error de red: " + err.message;
        }
    });
    </script>
</body>
</html>
"""

@login_bp.route('/login', methods=['GET'])
def mostrar_login():
    return render_template_string(login_html, estilo=estilo_css)

# Ruta POST: autenticación (plano por ahora; combina con /registrar actual)
@login_bp.route('/login', methods=['POST'])
def procesar_login():
    data = request.get_json()
    email = (data.get('email') or '').strip()
    password = data.get('password')

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        query = "SELECT * FROM usuarios WHERE email = %s AND contrasena_hash = %s"
        cursor.execute(query, (email, password))
        user = cursor.fetchone()

        if user:
            # Establecer múltiples identificadores de sesión
            session['usuario_id'] = user['id']
            session['user_id'] = user['id']  # Doble referencia
            session['id'] = user['id']  # Triple referencia
            session['rol'] = user['rol']
            session['nombre'] = user['nombre']
            session['email'] = user['email']
            
            # Hacer la sesión permanente
            session.permanent = True
            
            return jsonify({
                'nombre': user['nombre'], 
                'rol': user['rol'],
                'id': user['id']
            }), 200
        else:
            return jsonify({'error': 'Credenciales incorrectas'}), 401

    except mysql.connector.Error as err:
        return jsonify({'error': f'Error de base de datos: {err}'}), 500
    finally:
        try:
            if conn.is_connected():
                cursor.close()
                conn.close()
        except Exception:
            pass
