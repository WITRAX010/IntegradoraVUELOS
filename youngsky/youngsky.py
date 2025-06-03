from flask import Flask, request, jsonify
from flask import Flask, render_template
from flask import session, redirect, url_for
from admin_dashboard import admin_bp
from cliente_dashboard import cliente_bp
import pymysql
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

app.secret_key = 'clave_super_secreta'
app.register_blueprint(admin_bp)
app.register_blueprint(cliente_bp)

db = pymysql.connect(
    host='localhost',
    user='root',
    password='root',
    database='youngsky',
    cursorclass=pymysql.cursors.DictCursor
)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    data = request.get_json()
    email = data['email']
    contrasena_hash = data['contrasena_hash']  # Ya está hasheada del frontend

    try:
        with db.cursor() as cursor:
            sql = "SELECT * FROM usuarios WHERE email = %s AND contrasena_hash = %s"
            cursor.execute(sql, (email, contrasena_hash))
            usuario = cursor.fetchone()

            if usuario:
                session['usuario_id'] = usuario['id']
                session['rol'] = usuario['rol']

                if usuario['rol'] == 'admin':
                    return jsonify({"redirect": "/admin/dashboard"}), 200
                else:
                    return jsonify({"redirect": "/cliente/dashboard"}), 200
            else:
                return jsonify({"error": "Credenciales inválidas"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return render_template('view.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    return "<h1>Bienvenido al panel de administrador</h1>"

@app.route('/cliente/dashboard')
def cliente_dashboard():
    return "<h1>Bienvenido al panel de cliente</h1>"

@app.route('/reservar')
def reservar():
    return render_template('reservar.html')


@app.route('/registrar', methods=['POST'])
def registrar_usuario():
    data = request.get_json()
    nombre = data['nombre']
    email = data['email']
    contrasena_hash = data['contrasena_hash']  
    pais = data['pais_residencia']
    rol = data.get('rol', 'cliente')

    try:
        with db.cursor() as cursor:
            sql = """
                INSERT INTO usuarios (nombre, email, contrasena_hash, pais_residencia, rol)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (nombre, email, contrasena_hash, pais, rol))
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

if __name__ == '__main__':
    app.run(debug=True)