from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, make_response, redirect, request, session

from .store import auth_user, ensure_default_admin_if_empty
from .. import core
import os


def register_ops_auth_routes(app: Flask) -> None:
    def _ctx() -> core.AppContext:
        return app.config["CARDAPIO_CTX"]

    @app.get("/ops/login")
    def ops_login_page():
        ensure_default_admin_if_empty(_ctx())
        nxt = str(request.args.get("next") or "").strip() or "/"
        nxt_safe = nxt.replace('"', "")
        is_kds = "/cozinha" in nxt
        page_title = "Cozinha — Do'Rafa" if is_kds else "Login — Do'Rafa"
        logo_src = "/assets/KDS_COZINHA.png" if is_kds else "/assets/logo_cardapio.png"
        favicon_src = "/assets/KDS_COZINHA.ico" if is_kds else "/assets/logo_cardapio.ico"
        accent = "#fd6300" if is_kds else "#0a5c2f"
        accent_dark = "#0d0d0d" if is_kds else "#073d1f"
        heading = "Cozinha Do'Rafa" if is_kds else "Do'Rafa"
        subtitle = "Painel da Cozinha" if is_kds else "Área Operacional"
        html = f"""<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\" />
  <meta name=\"theme-color\" content=\"{accent}\" />
  <meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\" />
  <link rel=\"icon\" href=\"{favicon_src}\" />
  <title>{page_title}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{
      font-family:'Segoe UI',system-ui,-apple-system,sans-serif;
      min-height:100vh;display:flex;align-items:center;justify-content:center;
      background:linear-gradient(135deg,{accent_dark} 0%,#1a1a1a 100%);
      color:#f7f3ef;padding:20px
    }}
    .card{{
      width:100%;max-width:380px;
      background:rgba(20,20,20,0.85);backdrop-filter:blur(12px);
      border:1px solid rgba(255,255,255,0.08);border-radius:24px;
      padding:36px 28px 28px;text-align:center;
      box-shadow:0 24px 80px rgba(0,0,0,0.5)
    }}
    .logo{{
      width:84px;height:84px;border-radius:20px;margin:0 auto 20px;
      background:{accent};display:flex;align-items:center;justify-content:center;
      box-shadow:0 8px 32px {accent}66;overflow:hidden
    }}
    .logo img{{width:100%;height:100%;object-fit:cover;border-radius:20px}}
    h1{{font-size:22px;font-weight:700;color:#f7f3ef;margin-bottom:4px}}
    .subtitle{{font-size:14px;color:rgba(247,243,239,0.5);margin-bottom:28px}}
    form{{text-align:left}}
    label{{display:block;font-size:13px;color:rgba(247,243,239,0.6);margin-bottom:8px;font-weight:500}}
    .field{{margin-bottom:18px}}
    input{{
      width:100%;font-size:16px;padding:14px 16px;border-radius:12px;
      border:1px solid rgba(255,255,255,0.10);background:rgba(0,0,0,0.3);
      color:#f7f3ef;outline:none;transition:border-color .2s,box-shadow .2s
    }}
    input:focus{{border-color:{accent};box-shadow:0 0 0 3px {accent}33}}
    input::placeholder{{color:rgba(247,243,239,0.25)}}
    button{{
      width:100%;margin-top:8px;font-size:16px;padding:14px;border-radius:14px;
      border:0;background:{accent};color:#fff;font-weight:700;cursor:pointer;
      transition:transform .1s,box-shadow .2s
    }}
    button:hover{{box-shadow:0 8px 24px {accent}55}}
    button:active{{transform:scale(0.98)}}
    .muted{{font-size:12px;color:rgba(247,243,239,0.35);margin-top:22px}}
    .error{{
      background:rgba(220,38,38,0.15);border:1px solid rgba(220,38,38,0.3);
      color:#fca5a5;border-radius:10px;padding:10px 14px;font-size:13px;
      margin-bottom:18px;display:none
    }}
  </style>
</head>
<body>
  <div class=\"card\">
    <div class=\"logo\"><img src=\"{logo_src}\" alt=\"Logo\" /></div>
    <h1>{heading}</h1>
    <div class=\"subtitle\">{subtitle}</div>
    <form method=\"post\" action=\"/ops/login\">
      <input type=\"hidden\" name=\"next\" value=\"{nxt_safe}\" />
      <div class=\"field\">
        <label>Usuário</label>
        <input name=\"username\" autocomplete=\"username\" placeholder=\"Digite seu usuário\" />
      </div>
      <div class=\"field\">
        <label>Senha</label>
        <input name=\"password\" type=\"password\" autocomplete=\"current-password\" placeholder=\"••••••••\" />
      </div>
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
        admin_username = str(os.environ.get("OPS_ADMIN_USERNAME") or "").strip().lower()
        if admin_username:
            got_user = str(session.get("ops_username") or "").strip().lower()
            if got_user == admin_username:
                return None
        got = str(session.get("ops_role") or "").strip().upper()
        if got != str(role).strip().upper():
            path = str(request.path or "/")
            if path.startswith("/api/"):
                return jsonify({"error": "forbidden"}), 403
            return make_response("forbidden", 403)
    return None
