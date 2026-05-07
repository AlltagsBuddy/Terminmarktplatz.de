"""Einheitliche JSON-Fehlerantworten für API-Endpunkte."""

from flask import jsonify


def json_error(msg, code=400):
    return jsonify({"error": msg}), code
