from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, make_response, redirect, request, session

from .store import auth_user, ensure_default_admin_if_empty
from .. import core


def register_ops_auth_routes(app: Flask) -> None:
    def _ctx() -> core.AppContext:
        return app.config["CARDAPIO_CTX"]

    @app.get("/ops/login")
    def ops_login_page():
        ensure_default_admin_if_empty(_ctx())
        nxt = str(request.args.get("next") or "").strip() or "/"
        nxt_safe = nxt.replace('"', "")
        html = f"""<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Login Operacional</title>
  <style>
    body{{font-family:Arial,Helvetica,sans-serif;margin:0;padding:18px;background:#0b0b0c;color:#fff}}
    .box{{max-width:420px;margin:0 auto;background:#151518;border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:14px}}
    h1{{font-size:18px;margin:0 0 12px 0}}
    label{{display:block;font-size:13px;opacity:.85;margin:10px 0 6px}}
    input{{width:100%;font-size:16px;padding:12px;border-radius:10px;border:1px solid rgba(255,255,255,0.10);background:#0f0f12;color:#fff;box-sizing:border-box}}
    button{{width:100%;margin-top:14px;font-size:16px;padding:12px 14px;border-radius:12px;border:0;background:#ffffff;color:#111;font-weight:700}}
    .muted{{opacity:.75;font-size:12px;margin-top:8px}}
  </style>
</head>
<body>
  <div class=\"box\">
    <h1>Login Operacional</h1>
    <form method=\"post\" action=\"/ops/login\">
      <input type=\"hidden\" name=\"next\" value=\"{nxt_safe}\" />
      <label>Usuário</label>
      <input name=\"username\" autocomplete=\"username\" />
      <label>Senha</label>
      <input name=\"password\" type=\"password\" autocomplete=\"current-password\" />
      <button type=\"submit\">Entrar</button>
    </form>
    <div class=\"muted\">Acesso restrito. Se você não tem credenciais, solicite ao administrador.</div>
  </div>
</body>
</html>"""
        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.post("/ops/login")
    def ops_login_post():
        ensure_default_admin_if_empty(_ctx())
        username = str(request.form.get("username") or "").strip().lower()
        password = str(request.form.get("password") or "")
        nxt = str(request.form.get("next") or "").strip() or "/"
        rec = auth_user(username=username, password=password)
        if rec is None:
            return redirect("/ops/login?next=" + nxt, code=302)

        session["ops_user_id"] = int(rec.get("id") or 0)
        session["ops_username"] = str(rec.get("username") or "")
        session["ops_role"] = str(rec.get("role") or "")
        return redirect(nxt, code=302)

    @app.post("/ops/logout")
    def ops_logout_post():
        session.pop("ops_user_id", None)
        session.pop("ops_username", None)
        session.pop("ops_role", None)
        return redirect("/ops/login", code=302)


def require_ops_login(*, role: str | None = None) -> Any:
    uid = session.get("ops_user_id")
    if not uid:
        path = str(request.path or "/")
        if path.startswith("/api/"):
            return jsonify({"error": "unauthorized"}), 401
        return redirect("/ops/login?next=" + path, code=302)
    if role is not None:
        got = str(session.get("ops_role") or "").strip().upper()
        if got != str(role).strip().upper():
            path = str(request.path or "/")
            if path.startswith("/api/"):
                return jsonify({"error": "forbidden"}), 403
            return make_response("forbidden", 403)
    return None
