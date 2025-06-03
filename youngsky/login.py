from flask import Flask, request, jsonify, render_template_string
import mysql.connector
import bcrypt

app = Flask(__name__)

# Configuración de la base de datos
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'youngsky'
}

# HTML incrustado
login_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login Moderno</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
    <style>
        {{ estilo }}
    </style>
</head>
<body>
    <div class="container" id="container">
        <!-- Sign Up -->
        <div class="form-container sign-up">
            <form onsubmit="return false;">
                <h1>Crear Cuenta</h1>
                <div class="social-icons">
                    <a href="#" class="icon"><i class="fa-brands fa-google-plus-g"></i></a>
                    <a href="#" class="icon"><i class="fa-brands fa-facebook-f"></i></a>
                    <a href="#" class="icon"><i class="fa-brands fa-github"></i></a>
                    <a href="#" class="icon"><i class="fa-brands fa-linkedin-in"></i></a>
                </div>
                <span>o usa un email para registrarte</span>
                <input type="text" placeholder="Name">
                <input type="email" placeholder="Email">
                <input type="password" placeholder="Password">
                <button type="submit">Sign Up</button>
            </form>
        </div>

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
                <input type="email" placeholder="Email" id="email">
                <input type="password" placeholder="Password" id="password">
                <a href="#">¿Olvidaste tu contraseña?</a>
                <button type="submit">Sign In</button>
                <p id="message" style="color:red;"></p>
            </form>
        </div>

        <!-- Toggle -->
        <div class="toggle-container">
            <div class="toggle">
                <div class="toggle-panel toggle-left">
                    <h1>¡Bienvenido de nuevo!</h1>
                    <p>Ingrese sus datos personales para utilizar todas las funciones del sitio</p>
                    <button class="hidden" id="login">Sign In</button>
                </div>
                <div class="toggle-panel toggle-right">
                    <h1>YoungSKY</h1>
                    <p>Regístrese con sus datos personales para utilizar todas las funciones del sitio</p>
                    <button class="hidden" id="register">Sign Up</button>
                </div>
            </div>
        </div>
    </div>

    <script>
    const container = document.getElementById('container');
    const registerBtn = document.getElementById('register');
    const loginBtn = document.getElementById('login');

    registerBtn.addEventListener('click', () => container.classList.add("active"));
    loginBtn.addEventListener('click', () => container.classList.remove("active"));

    // Función para obtener hash SHA-256
    async function sha256(str) {
        const buffer = new TextEncoder().encode(str);
        const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
        return Array.from(new Uint8Array(hashBuffer)).map(b => b.toString(16).padStart(2, '0')).join('');
    }

    // Lógica de envío del login usando fetch y hash SHA-256
    document.getElementById("loginForm").addEventListener("submit", async function (e) {
        e.preventDefault();
        const email = document.getElementById("email").value;
        const password = document.getElementById("password").value;
        const hash = await sha256(password);

        const response = await fetch("/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, contrasena_hash: hash })
        });

        const data = await response.json();
        const msg = document.getElementById("message");

        if (response.ok) {
            msg.style.color = "green";
            msg.innerText = `¡Bienvenido ${data.nombre}! Rol: ${data.rol}`;
        } else {
            msg.style.color = "red";
            msg.innerText = data.error || "Error desconocido";
        }
    });
</script>
</body>
</html>
"""

# Estilo como string para pasar a la plantilla
with open("login_style.css", "r", encoding="utf-8") as f:
    estilo_css = f.read()

@app.route('/', methods=['GET'])
def index():
    return render_template_string(login_html, estilo=estilo_css)

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        query = "SELECT * FROM usuarios WHERE email = %s"
        cursor.execute(query, (email,))
        user = cursor.fetchone()

        if user and bcrypt.checkpw(password.encode('utf-8'), user['contrasena_hash'].encode('utf-8')):
            return jsonify({
                'message': 'Inicio de sesión exitoso',
                'nombre': user['nombre'],
                'rol': user['rol']
            }), 200
        else:
            return jsonify({'error': 'Credenciales incorrectas'}), 401

    except mysql.connector.Error as err:
        return jsonify({'error': f'Error de base de datos: {err}'}), 500

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    app.run(debug=True)
