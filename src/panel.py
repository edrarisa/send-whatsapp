"""Panel web para subir la lista de contactos.

Solo sube. No envia mensajes, no muestra telefonos y no recibe el token de
WhatsApp: si alguien entra, no se lleva la lista ni puede gastar dinero.
"""

import os
from datetime import datetime, timezone

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from src.contactos import leer_contactos
from src.intentos import ControlIntentos
from src.subida import ArchivoRechazado, ListaInvalida, guardar_lista, validar_archivo

CARPETA_PLANTILLAS = os.path.join(os.path.dirname(__file__), "plantillas_html")


def crear_app(config=None):
    """Fabrica de la app. Recibe la configuracion para poder probarla aislada."""
    app = Flask(__name__, template_folder=CARPETA_PLANTILLAS)

    ajustes = {
        "PANEL_PASSWORD_HASH": os.environ.get("PANEL_PASSWORD_HASH", ""),
        "PANEL_SECRET_KEY": os.environ.get("PANEL_SECRET_KEY", ""),
        "PANEL_DESTINO": os.environ.get("PANEL_DESTINO", "/datos/entrada/contactos.xlsx"),
        "PANEL_COOKIE_SEGURA": os.environ.get("PANEL_COOKIE_SEGURA", "1") == "1",
    }
    ajustes.update(config or {})

    app.config.update(
        SECRET_KEY=ajustes["PANEL_SECRET_KEY"],
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=ajustes["PANEL_COOKIE_SEGURA"],
        # Algo por encima del limite real, para poder dar un mensaje propio en
        # vez del 413 seco de Werkzeug.
        MAX_CONTENT_LENGTH=11 * 1024 * 1024,
        PANEL_PASSWORD_HASH=ajustes["PANEL_PASSWORD_HASH"],
        PANEL_DESTINO=ajustes["PANEL_DESTINO"],
    )

    control = ControlIntentos()

    def hay_sesion():
        return session.get("dentro") is True

    @app.get("/login")
    def mostrar_login():
        return render_template("login.html")

    @app.post("/login")
    def entrar():
        espera = control.segundos_de_espera()
        if espera:
            flash(f"Demasiados intentos. Espera {espera} segundos.")
            return redirect(url_for("mostrar_login"))

        if check_password_hash(
            app.config["PANEL_PASSWORD_HASH"], request.form.get("clave", "")
        ):
            control.registrar_acierto()
            session["dentro"] = True
            return redirect(url_for("portada"))

        control.registrar_fallo()
        flash("Contraseña incorrecta")
        return redirect(url_for("mostrar_login"))

    @app.post("/salir")
    def salir():
        session.clear()
        return redirect(url_for("mostrar_login"))

    @app.get("/")
    def portada():
        if not hay_sesion():
            return redirect(url_for("mostrar_login"))
        return render_template("subir.html", estado=_estado(app.config["PANEL_DESTINO"]))

    @app.post("/subir")
    def subir():
        if not hay_sesion():
            return redirect(url_for("mostrar_login"))

        archivo = request.files.get("archivo")
        nombre = archivo.filename if archivo else ""
        contenido = archivo.read() if archivo else b""

        try:
            validar_archivo(nombre, contenido)
            resumen = guardar_lista(contenido, app.config["PANEL_DESTINO"])
        except (ArchivoRechazado, ListaInvalida) as error:
            flash(str(error), "error")
            return redirect(url_for("portada"))

        detalle = ", ".join(f"{m}: {n}" for m, n in resumen.motivos.items())
        mensaje = f"Lista actualizada: {resumen.validos} contactos válidos"
        if resumen.descartados:
            mensaje += f", {resumen.descartados} descartados ({detalle})"
        flash(mensaje, "ok")
        return redirect(url_for("portada"))

    @app.errorhandler(413)
    def demasiado_grande(_error):
        flash("El archivo pesa más de 10 MB.", "error")
        return redirect(url_for("portada")), 302

    return app


def _estado(destino):
    """Que lista hay cargada ahora mismo, para mostrarla en la pagina."""
    if not os.path.exists(destino):
        return {"existe": False}

    momento = datetime.fromtimestamp(os.path.getmtime(destino), timezone.utc)
    fecha = momento.astimezone().strftime("%Y-%m-%d %H:%M")

    try:
        validos, descartes = leer_contactos(destino)
    except Exception:
        return {"existe": True, "validos": "?", "descartados": "?", "fecha": fecha}

    return {
        "existe": True,
        "validos": len(validos),
        "descartados": len(descartes),
        "fecha": fecha,
    }
