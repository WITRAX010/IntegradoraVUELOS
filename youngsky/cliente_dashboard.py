from flask import Blueprint, render_template, session, redirect, url_for

cliente_bp = Blueprint("cliente", __name__, url_prefix="/cliente")

@cliente_bp.route("/dashboard")
def dashboard():
    if session.get("rol") != "cliente":
        return redirect(url_for("login"))
    return render_template("cliente_dashboard.html")