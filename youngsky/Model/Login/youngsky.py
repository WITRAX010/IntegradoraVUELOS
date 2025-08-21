from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from admin_dashboard import admin_bp
from cliente_dashboard import cliente_bp
from login import login_bp  # Importamos el blueprint del login
import pymysql
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

app.secret_key = 'clave_super_secreta'

# Registrar blueprints
app.register_blueprint(admin_bp)
app.register_blueprint(cliente_bp)
app.register_blueprint(login_bp)

db = pymysql.connect(
    host='localhost',
    user='root',
    password='root',
    database='youngsky',
    cursorclass=pymysql.cursors.DictCursor
)

@app.route('/')
def home():
    return render_template('view.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/cliente/dashboard')
def cliente_dashboard():
    return render_template('cliente_dashboard.html')

@app.route('/reservar')
def reservar():
    return redirect(url_for('login.mostrar_login'))

@app.route('/registrar', methods=['POST'])
def registrar_usuario():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No se recibió JSON válido"}), 400

    nombre = data.get('nombre')
    email = data.get('email')
    contrasena = data.get('password')  # Se recibe sin hash
    pais = data.get('pais_residencia')
    rol = data.get('rol', 'cliente')

    try:
        with db.cursor() as cursor:
            sql = """
                INSERT INTO usuarios (nombre, email, contrasena_hash, pais_residencia, rol)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (nombre, email, contrasena, pais, rol))
            db.commit()
        return jsonify({"mensaje": "Usuario registrado correctamente"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/usuarios', methods=['GET'])
def obtener_usuarios():
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT id, nombre, email, rol FROM usuarios")
            usuarios = cursor.fetchall()
        return jsonify(usuarios)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)

@app.route('/debug/session')
def debug_session():
    return jsonify(dict(session))
  
