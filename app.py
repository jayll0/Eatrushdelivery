import os
import logging
import traceback
from flask import Flask, render_template, redirect, url_for, session, abort, request


from routes.auth_routes import auth_bp
from routes.home_routes import home_bp
from routes.warung_routes import warung_bp
from routes.pesanan_routes import pesanan_bp
from routes.obrolan_routes import obrolan_bp
from routes.pengguna_routes import pengguna_bp
from routes.keranjang_routes import keranjang_bp
from routes.pembayaran_routes import pembayaran_bp

from models.Warung import Warung
from models.Makanan import Makanan

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change_this_in_production")

app.config.update({
    "MYSQL_HOST": os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "MYSQL_USER": os.environ.get("MYSQL_USER", "eatrushd"),
    "MYSQL_PASSWORD": os.environ.get("MYSQL_PASSWORD", "6!6Sgk1KP5s+Md"),
    "MYSQL_DB": os.environ.get("MYSQL_DB", "eatrushd_eatrushh")
})

def safe_register(bp, name=None):
    try:
        if bp:
            app.register_blueprint(bp)
            logger.info("Registered blueprint: %s", getattr(bp, "name", name or "<unknown>"))
    except Exception:
        logger.exception("Failed to register blueprint: %s", name or getattr(bp, "name", "<unknown>"))

safe_register(auth_bp)
safe_register(home_bp)
safe_register(warung_bp)
safe_register(pesanan_bp)
safe_register(obrolan_bp)
safe_register(pengguna_bp)
safe_register(keranjang_bp)
safe_register(pembayaran_bp)


@app.route("/")
def index():
    if "user" in session:
        user_data = session['user']
        peran = user_data.get('Peran')
        if peran == 'penjual':
            return redirect(url_for('warung.home_warung'))
        else:
            return redirect(url_for('home.home'))
            
    return redirect(url_for("auth.auth_page"))


if __name__ == "__main__":
    app.run(debug=True)
