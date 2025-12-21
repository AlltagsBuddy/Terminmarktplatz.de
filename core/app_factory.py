import os
from flask import Flask

def create_app():
    ROOT = os.path.dirname(os.path.abspath(__file__))
    ROOT = os.path.dirname(ROOT)  # zurück ins Projekt-Root

    app = Flask(
        __name__,
        static_folder=os.path.join(ROOT, "static"),
        static_url_path="/static",
        template_folder=os.path.join(ROOT, "templates"),
    )

    return app
