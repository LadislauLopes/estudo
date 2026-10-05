#!/usr/bin/env python3
"""Banco de questões local.

Uso:  python3 app.py        → abre em http://localhost:8765
As questões e as respostas ficam em questoes.sqlite, nesta mesma pasta.
"""
import datetime as dt
import json
import os
import sqlite3
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent
DB = Path(os.environ.get("QDB", BASE / "questoes.sqlite"))
PORT = int(os.environ.get("QPORT", 8765))

SCHEMA = """
CREATE TABLE IF NOT EXISTS questoes (
    id              INTEGER PRIMARY KEY,
    codigo          TEXT UNIQUE,              -- código do QConcursos (ex.: Q2345678), se houver
    banca           TEXT,
    ano             INTEGER,
    orgao           TEXT,
    cargo           TEXT,
    disciplina      TEXT NOT NULL,
    assunto         TEXT NOT NULL,
    tipo            TEXT NOT NULL CHECK (tipo IN ('ME', 'CE')),   -- múltipla escolha ou certo/errado
    enunciado       TEXT NOT NULL,
    alternativas    TEXT,                     -- JSON {"A": "...", "B": "..."}; NULL em certo/errado
    gabarito        TEXT NOT NULL,            -- letra; 'C'/'E' em certo/errado; 'X' se anulada
    gabarito_fonte  TEXT NOT NULL DEFAULT 'qconcursos'
                    CHECK (gabarito_fonte IN ('qconcursos', 'oficial', 'claude')),
    comentario      TEXT,
    contestada      INTEGER NOT NULL DEFAULT 0,
    obs_contestacao TEXT,
    criada_em       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS respostas (
    id             INTEGER PRIMARY KEY,
    questao_id     INTEGER NOT NULL REFERENCES questoes (id) ON DELETE CASCADE,
    respondida_em  TEXT NOT NULL,
    resposta       TEXT NOT NULL,
    correta        INTEGER NOT NULL,
    chute          INTEGER NOT NULL DEFAULT 0,
    tempo_seg      INTEGER,
    tipo_erro      TEXT CHECK (tipo_erro IN ('A', 'B', 'C', 'D')),
    nota           TEXT,
    origem         TEXT NOT NULL DEFAULT 'app' CHECK (origem IN ('app', 'qconcursos'))
);
CREATE INDEX IF NOT EXISTS idx_respostas_questao ON respostas (questao_id);

-- Simulados ficam em tabelas próprias: não entram no banco de questões nem nas estatísticas.
CREATE TABLE IF NOT EXISTS simulados (
    id          INTEGER PRIMARY KEY,
    codigo      TEXT UNIQUE NOT NULL,
    nome        TEXT NOT NULL,
    descricao   TEXT,
    duracao_min INTEGER NOT NULL DEFAULT 240,
    textos      TEXT,                         -- JSON {"T1": "texto de apoio"}
    regras      TEXT NOT NULL,                -- JSON com peso e mínimo de cada disciplina
    criado_em   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS simulado_questoes (
    id           INTEGER PRIMARY KEY,
    simulado_id  INTEGER NOT NULL REFERENCES simulados (id) ON DELETE CASCADE,
    numero       INTEGER NOT NULL,
    disciplina   TEXT NOT NULL,
    assunto      TEXT NOT NULL,
    peso         INTEGER NOT NULL DEFAULT 1,
    texto        TEXT,                        -- chave do texto de apoio em simulados.textos
    enunciado    TEXT NOT NULL,
    alternativas TEXT NOT NULL,
    gabarito     TEXT NOT NULL,
    comentario   TEXT,
    base         TEXT,                        -- questão das provas antigas que serviu de modelo
    UNIQUE (simulado_id, numero)
);
CREATE TABLE IF NOT EXISTS simulado_tentativas (
    id          INTEGER PRIMARY KEY,
    simulado_id INTEGER NOT NULL REFERENCES simulados (id) ON DELETE CASCADE,
    iniciada_em TEXT NOT NULL,
    entregue_em TEXT
);
CREATE TABLE IF NOT EXISTS simulado_respostas (
    tentativa_id  INTEGER NOT NULL REFERENCES simulado_tentativas (id) ON DELETE CASCADE,
    questao_id    INTEGER NOT NULL REFERENCES simulado_questoes (id) ON DELETE CASCADE,
    resposta      TEXT,
    chute         INTEGER NOT NULL DEFAULT 0,
    respondida_em TEXT NOT NULL,
    PRIMARY KEY (tentativa_id, questao_id)
);
"""

ULTIMA = "(SELECT MAX(id) FROM respostas WHERE questao_id = q.id)"
MODOS = {
    "novas": "NOT EXISTS (SELECT 1 FROM respostas r WHERE r.questao_id = q.id)",
    "erradas": f"EXISTS (SELECT 1 FROM respostas r WHERE r.id = {ULTIMA} AND (r.correta = 0 OR r.chute = 1))",
    "todas": "1 = 1",
}


def agora():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def conectar():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(SCHEMA)
    return con


def filtro_sql(p):
    where, args = [], []
    if p.get("disc"):
        where.append("q.disciplina = ?")
        args.append(p["disc"])
    if p.get("ass"):
        where.append("q.assunto = ?")
        args.append(p["ass"])
    where.append(MODOS.get(p.get("modo"), MODOS["novas"]))
    return " AND ".join(where), args


def proxima(p):
    where, args = filtro_sql(p)
    excluir = [int(x) for x in p.get("excluir", "").split(",") if x.strip().isdigit()]
    with conectar() as con:
        restam = con.execute(f"SELECT COUNT(*) FROM questoes q WHERE {where}", args).fetchone()[0]
        extra = f" AND q.id NOT IN ({','.join('?' * len(excluir))})" if excluir else ""
        row = con.execute(f"SELECT q.* FROM questoes q WHERE {where}{extra} ORDER BY RANDOM() LIMIT 1",
                          args + excluir).fetchone()
        if not row:
            return {"questao": None, "restam": restam}
        tent = con.execute("SELECT COUNT(*), COALESCE(SUM(correta = 1 AND chute = 0), 0) FROM respostas WHERE questao_id = ?",
                           (row["id"],)).fetchone()
    q = {k: row[k] for k in ("id", "codigo", "banca", "ano", "orgao", "cargo", "disciplina", "assunto", "tipo", "enunciado")}
    q["alternativas"] = json.loads(row["alternativas"]) if row["alternativas"] else None
    q["tentativas"], q["acertos"] = tent[0], tent[1]
    return {"questao": q, "restam": restam}


def responder(b):
    with conectar() as con:
        q = con.execute("SELECT * FROM questoes WHERE id = ?", (int(b["questao_id"]),)).fetchone()
        resp = str(b["resposta"]).upper()
        correta = 1 if q["gabarito"] in (resp, "X") else 0
        cur = con.execute(
            "INSERT INTO respostas (questao_id, respondida_em, resposta, correta, chute, tempo_seg) VALUES (?, ?, ?, ?, ?, ?)",
            (q["id"], agora(), resp, correta, 1 if b.get("chute") else 0, b.get("tempo_seg")))
        return {"resposta_id": cur.lastrowid, "correta": bool(correta), "gabarito": q["gabarito"],
                "gabarito_fonte": q["gabarito_fonte"], "comentario": q["comentario"] or ""}


def marcar_chute(b):
    with conectar() as con:
        con.execute("UPDATE respostas SET chute = ? WHERE id = ?",
                    (1 if b.get("chute") else 0, int(b["resposta_id"])))
    return {"ok": True}


def classificar(b):
    tipo = b.get("tipo_erro") or None
    with conectar() as con:
        con.execute("UPDATE respostas SET tipo_erro = ?, nota = ? WHERE id = ?",
                    (tipo, (b.get("nota") or "").strip() or None, int(b["resposta_id"])))
    return {"ok": True}


def contestar(b):
    with conectar() as con:
        con.execute("UPDATE questoes SET contestada = 1, obs_contestacao = TRIM(COALESCE(obs_contestacao, '') || ' ' || ?) WHERE id = ?",
                    ((b.get("obs") or "").strip(), int(b["questao_id"])))
    return {"ok": True}


def filtros():
    with conectar() as con:
        rows = con.execute("SELECT disciplina, assunto, COUNT(*) n FROM questoes GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
        tot = con.execute("""SELECT (SELECT COUNT(*) FROM questoes),
                                    (SELECT COUNT(DISTINCT questao_id) FROM respostas),
                                    (SELECT COUNT(*) FROM respostas),
                                    (SELECT COALESCE(SUM(correta = 1 AND chute = 0), 0) FROM respostas)""").fetchone()
    return {"assuntos": [dict(r) for r in rows],
            "total": {"questoes": tot[0], "respondidas": tot[1], "tentativas": tot[2], "acertos": tot[3]}}


def stats():
    with conectar() as con:
        rows = con.execute("""
            SELECT q.disciplina, q.assunto, COUNT(DISTINCT q.id) AS questoes,
                   COUNT(DISTINCT r.questao_id) AS respondidas, COUNT(r.id) AS tentativas,
                   COALESCE(SUM(r.correta = 1 AND r.chute = 0), 0) AS acertos,
                   COALESCE(SUM(r.chute), 0) AS chutes
            FROM questoes q LEFT JOIN respostas r ON r.questao_id = q.id
            GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
    return {"linhas": [dict(r) for r in rows]}


def caderno():
    with conectar() as con:
        rows = con.execute("""
            SELECT r.id, r.respondida_em, r.resposta, r.chute, r.tipo_erro, r.nota,
                   q.codigo, q.assunto, q.gabarito, SUBSTR(q.enunciado, 1, 220) AS trecho
            FROM respostas r JOIN questoes q ON q.id = r.questao_id
            WHERE r.correta = 0 OR r.chute = 1
            ORDER BY r.id DESC LIMIT 300""").fetchall()
    return {"linhas": [dict(r) for r in rows]}


def sim_lista():
    with conectar() as con:
        sims = [dict(r) for r in con.execute(
            "SELECT s.id, s.codigo, s.nome, s.descricao, s.duracao_min, COUNT(q.id) AS questoes "
            "FROM simulados s LEFT JOIN simulado_questoes q ON q.simulado_id = s.id GROUP BY s.id ORDER BY s.id")]
        tents = con.execute("SELECT id, simulado_id, iniciada_em, entregue_em FROM simulado_tentativas ORDER BY id DESC").fetchall()
        for s in sims:
            s["tentativas"] = [dict(t, **({"resultado": sim_resultado(con, t["id"])["resumo"]} if t["entregue_em"] else {}))
                               for t in tents if t["simulado_id"] == s["id"]]
    return {"simulados": sims}


def sim_iniciar(b):
    with conectar() as con:
        aberta = con.execute("SELECT id FROM simulado_tentativas WHERE simulado_id = ? AND entregue_em IS NULL",
                             (int(b["simulado_id"]),)).fetchone()
        if aberta:
            return {"tentativa_id": aberta["id"]}
        cur = con.execute("INSERT INTO simulado_tentativas (simulado_id, iniciada_em) VALUES (?, ?)", (int(b["simulado_id"]), agora()))
        return {"tentativa_id": cur.lastrowid}


def sim_resultado(con, tid):
    t = con.execute("SELECT * FROM simulado_tentativas WHERE id = ?", (tid,)).fetchone()
    regras = json.loads(con.execute("SELECT regras FROM simulados WHERE id = ?", (t["simulado_id"],)).fetchone()[0])
    rows = con.execute("""SELECT q.id, q.disciplina, q.peso, q.gabarito, r.resposta, COALESCE(r.chute, 0) AS chute
                          FROM simulado_questoes q LEFT JOIN simulado_respostas r ON r.questao_id = q.id AND r.tentativa_id = ?
                          WHERE q.simulado_id = ? ORDER BY q.numero""", (tid, t["simulado_id"])).fetchall()
    discs, total, corretas = {}, 0.0, {}
    for r in rows:
        ok = r["resposta"] is not None and r["resposta"] == r["gabarito"]
        corretas[r["id"]] = ok
        d = discs.setdefault(r["disciplina"], {"disciplina": r["disciplina"], "questoes": 0, "acertos": 0, "chutes_certos": 0,
                                               "em_branco": 0, "pontos": 0.0, "max": 0.0})
        d["questoes"] += 1
        d["max"] += r["peso"]
        d["em_branco"] += r["resposta"] is None
        if ok:
            d["acertos"] += 1
            d["chutes_certos"] += r["chute"]
            d["pontos"] += r["peso"]
    for d in discs.values():
        d["minimo"] = regras["disciplinas"].get(d["disciplina"], {}).get("minimo", 0)
        d["eliminado"] = d["pontos"] < d["minimo"]
        total += d["pontos"]
    eliminado = total < regras["minimo_total"] or any(d["eliminado"] for d in discs.values())
    resumo = {"pontos": total, "max": regras["total"], "minimo_total": regras["minimo_total"], "eliminado": eliminado,
              "acertos": sum(d["acertos"] for d in discs.values()), "questoes": len(rows)}
    return {"disciplinas": list(discs.values()), "resumo": resumo, "corretas": corretas}


def sim_prova(p):
    tid = int(p["tentativa"])
    with conectar() as con:
        t = con.execute("SELECT * FROM simulado_tentativas WHERE id = ?", (tid,)).fetchone()
        s = con.execute("SELECT * FROM simulados WHERE id = ?", (t["simulado_id"],)).fetchone()
        entregue = t["entregue_em"] is not None
        resps = {r["questao_id"]: r for r in con.execute("SELECT * FROM simulado_respostas WHERE tentativa_id = ?", (tid,))}
        questoes = []
        for q in con.execute("SELECT * FROM simulado_questoes WHERE simulado_id = ? ORDER BY numero", (s["id"],)):
            item = {k: q[k] for k in ("id", "numero", "disciplina", "peso", "texto", "enunciado")}
            item["alternativas"] = json.loads(q["alternativas"])
            r = resps.get(q["id"])
            item["resposta"], item["chute"] = (r["resposta"], bool(r["chute"])) if r else (None, False)
            if entregue:  # gabarito e comentário só aparecem depois de entregar
                item.update(gabarito=q["gabarito"], comentario=q["comentario"], assunto=q["assunto"], base=q["base"])
            questoes.append(item)
        out = {"tentativa": dict(t), "simulado": {k: s[k] for k in ("id", "codigo", "nome", "descricao", "duracao_min")},
               "textos": json.loads(s["textos"] or "{}"), "questoes": questoes}
        if entregue:
            res = sim_resultado(con, tid)
            out["resultado"] = {"disciplinas": res["disciplinas"], "resumo": res["resumo"]}
    return out


def sim_marcar(b):
    tid = int(b["tentativa_id"])
    with conectar() as con:
        if con.execute("SELECT entregue_em FROM simulado_tentativas WHERE id = ?", (tid,)).fetchone()[0]:
            raise ValueError("este simulado já foi entregue")
        con.execute("""INSERT INTO simulado_respostas (tentativa_id, questao_id, resposta, chute, respondida_em) VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT (tentativa_id, questao_id) DO UPDATE SET resposta = excluded.resposta, chute = excluded.chute,
                       respondida_em = excluded.respondida_em""",
                    (tid, int(b["questao_id"]), b.get("resposta") or None, 1 if b.get("chute") else 0, agora()))
    return {"ok": True}


def sim_entregar(b):
    with conectar() as con:
        con.execute("UPDATE simulado_tentativas SET entregue_em = ? WHERE id = ? AND entregue_em IS NULL", (agora(), int(b["tentativa_id"])))
    return {"ok": True}


GET_ROUTES = {"/api/proxima": proxima, "/api/filtros": lambda p: filtros(),
              "/api/stats": lambda p: stats(), "/api/caderno": lambda p: caderno(),
              "/api/sim/lista": lambda p: sim_lista(), "/api/sim/prova": sim_prova}
POST_ROUTES = {"/api/responder": responder, "/api/marcar_chute": marcar_chute,
               "/api/classificar": classificar, "/api/contestar": contestar,
               "/api/sim/iniciar": sim_iniciar, "/api/sim/marcar": sim_marcar, "/api/sim/entregar": sim_entregar}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, fn, arg):
        try:
            self._send(200, json.dumps(fn(arg), ensure_ascii=False), "application/json; charset=utf-8")
        except Exception as e:  # erro de uso local: devolve a mensagem para a página mostrar
            self._send(400, json.dumps({"erro": str(e)}, ensure_ascii=False), "application/json; charset=utf-8")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path in GET_ROUTES:
            return self._json(GET_ROUTES[u.path], {k: v[0] for k, v in parse_qs(u.query).items()})
        self._send(404, "não encontrado", "text/plain; charset=utf-8")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path not in POST_ROUTES:
            return self._send(404, "não encontrado", "text/plain; charset=utf-8")
        n = int(self.headers.get("Content-Length") or 0)
        self._json(POST_ROUTES[u.path], json.loads(self.rfile.read(n) or b"{}"))


PAGE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Banco de Questões</title>
<style>
:root { --bg:#0e1117; --card:#161b24; --line:#2a3140; --text:#e6e8ec; --muted:#9aa3b2;
        --accent:#6ea8fe; --ok:#2fb36d; --ok-bg:#12301f; --bad:#e5534b; --bad-bg:#3a1717; --warn:#d9a441; }
@media (prefers-color-scheme: light) {
  :root { --bg:#f5f6f8; --card:#ffffff; --line:#d9dde4; --text:#1b1f27; --muted:#5d6675;
          --accent:#2463d6; --ok:#1d8a52; --ok-bg:#e3f5ea; --bad:#c43c35; --bad-bg:#fbe6e5; --warn:#a8741a; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:16px/1.55 system-ui, sans-serif; }
header { display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between;
         padding:14px 20px; border-bottom:1px solid var(--line); }
header h1 { font-size:18px; margin:0; }
#resumo { color:var(--muted); font-size:14px; }
nav button, .btn { background:transparent; color:var(--text); border:1px solid var(--line); border-radius:8px;
                   padding:7px 12px; cursor:pointer; font:inherit; font-size:14px; }
nav button.ativo, .btn.primario { background:var(--accent); border-color:var(--accent); color:#fff; }
main { max-width:860px; margin:0 auto; padding:20px 16px 60px; }
.filtros { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:18px; }
select { background:var(--card); color:var(--text); border:1px solid var(--line); border-radius:8px; padding:7px 10px; font:inherit; font-size:14px; max-width:100%; }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px; }
.meta { font:12px/1.4 ui-monospace, monospace; color:var(--muted); letter-spacing:.03em; margin-bottom:12px; text-transform:uppercase; }
.enunciado { white-space:pre-wrap; font-size:17px; margin-bottom:16px; }
.alt { display:flex; gap:12px; width:100%; text-align:left; align-items:flex-start; background:transparent; color:var(--text);
       border:1px solid var(--line); border-radius:10px; padding:11px 14px; margin-bottom:9px; cursor:pointer; font:inherit; white-space:pre-wrap; }
.alt:hover:not(:disabled) { border-color:var(--accent); }
.alt .letra { flex:none; width:26px; height:26px; border-radius:6px; display:grid; place-items:center;
              background:var(--line); font:600 13px ui-monospace, monospace; }
.alt.certa { background:var(--ok-bg); border-color:var(--ok); } .alt.certa .letra { background:var(--ok); color:#fff; }
.alt.errada { background:var(--bad-bg); border-color:var(--bad); } .alt.errada .letra { background:var(--bad); color:#fff; }
.alt:disabled { cursor:default; }
.alt.selecionada { border-color:var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.btn:disabled { opacity:.45; cursor:default; }
.acoes-resposta { display:flex; justify-content:space-between; gap:8px; margin:4px 0 14px; }
.controles { display:flex; flex-wrap:wrap; gap:16px; align-items:center; color:var(--muted); font-size:14px; margin-top:6px; }
.veredito { font-weight:600; margin:16px 0 6px; } .veredito.ok { color:var(--ok); } .veredito.bad { color:var(--bad); }
.chute-pos { display:inline-flex; align-items:center; gap:6px; font-size:14px; color:var(--muted); }
.comentario { white-space:pre-wrap; color:var(--text); border-top:1px dashed var(--line); padding-top:10px; margin-top:8px; }
.rotulo { font:600 12px ui-monospace, monospace; color:var(--accent); letter-spacing:.06em; }
.aviso { color:var(--warn); font-size:13px; margin-top:6px; }
.tipos { display:flex; flex-wrap:wrap; gap:8px; margin:10px 0; }
.tipos button.sel { background:var(--accent); border-color:var(--accent); color:#fff; }
textarea { width:100%; min-height:64px; background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:8px; padding:8px; font:inherit; font-size:14px; }
.acoes { display:flex; justify-content:space-between; gap:8px; margin-top:14px; flex-wrap:wrap; }
.dica { color:var(--muted); font-size:13px; margin-top:14px; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th, td { text-align:left; padding:8px 6px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); font-weight:600; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
.p-bad { color:var(--bad); font-weight:600; } .p-warn { color:var(--warn); font-weight:600; } .p-ok { color:var(--ok); font-weight:600; }
.destaque { color:var(--accent); font-weight:700; }
.vazio { color:var(--muted); padding:30px 0; text-align:center; }
.scroll { overflow-x:auto; }
.sim-barra { position:sticky; top:0; z-index:2; display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between;
             background:var(--bg); border-bottom:1px solid var(--line); padding:10px 0; margin-bottom:16px; }
.sim-barra .tempo { font:600 18px ui-monospace, monospace; }
.sim-barra .tempo.acabando { color:var(--bad); }
.sim-disc { font-size:15px; letter-spacing:.06em; text-transform:uppercase; color:var(--accent); margin:28px 0 10px; }
.sim-texto { white-space:pre-wrap; background:var(--card); border:1px solid var(--line); border-left:3px solid var(--accent);
             border-radius:10px; padding:16px 18px; margin-bottom:16px; }
.sim-q { margin-bottom:14px; }
.sim-q .num { font:700 13px ui-monospace, monospace; color:var(--muted); margin-bottom:6px; }
.sim-lista .card { margin-bottom:14px; }
.sim-lista h2 { font-size:17px; margin:0 0 6px; }
.p-elim { color:var(--bad); font-weight:700; } .p-aprov { color:var(--ok); font-weight:700; }
</style>
</head>
<body>
<header>
  <h1>Banco de Questões</h1>
  <span id="resumo"></span>
  <nav>
    <button data-v="resolver" class="ativo">Resolver</button>
    <button data-v="stats">Estatísticas</button>
    <button data-v="caderno">Caderno de erros</button>
    <button data-v="simulado">Simulado</button>
  </nav>
</header>
<main>
  <section id="v-resolver">
    <div class="filtros">
      <select id="disc"><option value="">Todas as disciplinas</option></select>
      <select id="ass"><option value="">Todos os assuntos</option></select>
      <select id="modo">
        <option value="novas">Não respondidas</option>
        <option value="erradas">Erradas e chutadas</option>
        <option value="todas">Todas</option>
      </select>
      <button class="btn primario" id="iniciar">Começar</button>
    </div>
    <div id="card" class="card" hidden>
      <div class="meta" id="meta"></div>
      <div class="enunciado" id="enunciado"></div>
      <div id="alts"></div>
      <div class="acoes-resposta">
        <button class="btn" id="pular">Pular (P)</button>
        <button class="btn primario" id="confirmar" disabled>Confirmar (Enter)</button>
      </div>
      <div class="controles">
        <span id="timer">00:00</span>
        <span id="restam"></span>
      </div>
      <div id="resultado" hidden>
        <div class="veredito" id="veredito"></div>
        <label class="chute-pos"><input type="checkbox" id="chute-pos"> Foi chute (X)</label>
        <div class="aviso" id="fonte" hidden>Gabarito definido pelo Claude, não pelo QConcursos. Se discordar, use "Gabarito errado?".</div>
        <div class="comentario" id="comentario" hidden><div class="rotulo">POR QUÊ</div><div id="comentario-txt"></div></div>
        <div id="classificar" hidden>
          <div class="rotulo" style="margin-top:14px">TIPO DE ERRO</div>
          <div class="tipos">
            <button class="btn" data-t="A">A · não sabia</button>
            <button class="btn" data-t="B">B · confundi</button>
            <button class="btn" data-t="C">C · desatenção</button>
            <button class="btn" data-t="D">D · interpretação</button>
          </div>
          <textarea id="nota" placeholder="Regra a lembrar (vai para o caderno de erros)"></textarea>
        </div>
        <div class="acoes">
          <button class="btn" id="contestar">Gabarito errado?</button>
          <button class="btn primario" id="proxima">Próxima (Enter)</button>
        </div>
      </div>
      <div class="dica">Atalhos: letra da alternativa seleciona, Enter confirma · P pula a questão · depois de confirmar, X marca que foi chute, A/B/C/D classifica o erro e Enter vai para a próxima.</div>
    </div>
    <div id="vazio" class="vazio" hidden></div>
  </section>
  <section id="v-stats" hidden><div class="scroll"><table id="t-stats"></table></div>
    <p class="dica">Chute certo não conta como acerto. Cores pela regra do plano: abaixo de 70% volta com teoria; de 70% a 85% só questões; acima de 85% questões mais difíceis.</p></section>
  <section id="v-caderno" hidden><div class="scroll"><table id="t-caderno"></table></div></section>
  <section id="v-simulado" hidden>
    <div id="sim-lista" class="sim-lista"></div>
    <div id="sim-prova" hidden>
      <div class="sim-barra">
        <strong id="sim-nome"></strong>
        <span class="tempo" id="sim-tempo"></span>
        <span id="sim-cont" class="dica" style="margin:0"></span>
        <span><button class="btn" id="sim-voltar">Voltar</button> <button class="btn primario" id="sim-entregar">Entregar</button></span>
      </div>
      <div id="sim-resultado"></div>
      <div id="sim-questoes"></div>
    </div>
  </section>
</main>
<script>
const $ = s => document.querySelector(s);
const S = { q:null, respId:null, sessao:[], t0:0, respondida:false, tipo:null, assuntos:[], timer:null, selecionada:null };

async function api(path, body) {
  const r = await fetch(path, body ? { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) } : {});
  const j = await r.json();
  if (!r.ok) throw new Error(j.erro || r.status);
  return j;
}
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) k === 'class' ? e.className = v : e.setAttribute(k, v);
  for (const k of kids) e.append(k);
  return e;
}
function renderRico(el, texto) {
  // O enunciado usa **palavra** para marcar o que estava grifado/em negrito na prova original.
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  el.innerHTML = esc(texto || '').replace(/\*\*(.+?)\*\*/g, '<b class="destaque">$1</b>');
}
function pct(a, t) { return t ? Math.round(100 * a / t) : null; }
function classePct(p) { return p === null ? '' : p < 70 ? 'p-bad' : p < 85 ? 'p-warn' : 'p-ok'; }

async function carregarFiltros() {
  const f = await api('/api/filtros');
  S.assuntos = f.assuntos;
  const t = f.total, p = pct(t.acertos, t.tentativas);
  $('#resumo').textContent = `${t.questoes} questões · ${t.respondidas} respondidas` + (p === null ? '' : ` · ${p}% de acerto`);
  const disc = $('#disc'), atual = disc.value;
  disc.length = 1;
  [...new Set(f.assuntos.map(a => a.disciplina))].forEach(d => disc.append(el('option', { value:d }, d)));
  disc.value = atual; preencherAssuntos();
}
function preencherAssuntos() {
  const ass = $('#ass'), atual = ass.value, d = $('#disc').value;
  ass.length = 1;
  S.assuntos.filter(a => !d || a.disciplina === d).forEach(a => ass.append(el('option', { value:a.assunto }, `${a.assunto} (${a.n})`)));
  ass.value = [...ass.options].some(o => o.value === atual) ? atual : '';
}

async function proxima() {
  const qs = new URLSearchParams({ disc:$('#disc').value, ass:$('#ass').value, modo:$('#modo').value, excluir:S.sessao.join(',') });
  const r = await api('/api/proxima?' + qs);
  clearInterval(S.timer);
  if (!r.questao) {
    $('#card').hidden = true; $('#vazio').hidden = false;
    $('#vazio').textContent = S.sessao.length ? `Fim deste filtro: você respondeu ${S.sessao.length} questões nesta sessão.` : 'Nenhuma questão neste filtro ainda.';
    return;
  }
  const q = S.q = r.questao;
  Object.assign(S, { respId:null, respondida:false, tipo:null, selecionada:null, resultado:null });
  $('#vazio').hidden = true; $('#card').hidden = false; $('#resultado').hidden = true;
  $('#nota').value = '';
  $('#pular').hidden = false; $('#confirmar').hidden = false; $('#confirmar').disabled = true;
  document.querySelectorAll('.tipos button').forEach(b => b.classList.remove('sel'));
  $('#meta').textContent = [q.codigo, q.banca, q.ano, q.orgao, q.disciplina + ' › ' + q.assunto].filter(Boolean).join(' · ')
    + (q.tentativas ? ` · já respondida ${q.tentativas}x (${q.acertos} acerto${q.acertos === 1 ? '' : 's'})` : '');
  renderRico($('#enunciado'), q.enunciado);
  const alts = $('#alts'); alts.replaceChildren();
  const opcoes = q.tipo === 'CE' ? { C:'Certo', E:'Errado' } : q.alternativas;
  for (const [letra, texto] of Object.entries(opcoes)) {
    const txt = el('span', {});
    renderRico(txt, texto);
    const b = el('button', { class:'alt', 'data-l':letra }, el('span', { class:'letra' }, letra), txt);
    b.onclick = () => selecionar(letra);
    alts.append(b);
  }
  $('#restam').textContent = `${r.restam} no filtro`;
  S.t0 = Date.now();
  S.timer = setInterval(() => {
    const s = Math.floor((Date.now() - S.t0) / 1000);
    $('#timer').textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
  }, 500);
  window.scrollTo({ top:0 });
}

function selecionar(letra) {
  if (S.respondida) return;
  S.selecionada = letra;
  document.querySelectorAll('.alt').forEach(b => b.classList.toggle('selecionada', b.dataset.l === letra));
  $('#confirmar').disabled = false;
}
function confirmar() {
  if (S.respondida || !S.selecionada) return;
  responder(S.selecionada);
}
function pular() {
  if (S.respondida || !S.q) return;
  clearInterval(S.timer);
  S.sessao.push(S.q.id);
  proxima();
}

function atualizarVeredito(chute) {
  const r = S.resultado;
  const v = $('#veredito');
  v.textContent = r.gabarito === 'X' ? 'Questão anulada.' : r.correta ? (chute ? `Acertou no chute — gabarito ${r.gabarito}. Conta como erro no caderno.` : `Acertou — gabarito ${r.gabarito}.`) : `Errou — gabarito ${r.gabarito}.`;
  v.className = 'veredito ' + (r.correta && !chute ? 'ok' : 'bad');
  $('#classificar').hidden = r.correta && !chute;
}

async function responder(letra) {
  if (S.respondida || !S.q) return;
  S.respondida = true; clearInterval(S.timer);
  $('#pular').hidden = true; $('#confirmar').hidden = true;
  const r = await api('/api/responder', { questao_id:S.q.id, resposta:letra, tempo_seg:Math.round((Date.now() - S.t0) / 1000) });
  S.respId = r.resposta_id; S.sessao.push(S.q.id);
  S.resultado = { correta:r.correta, gabarito:r.gabarito };
  document.querySelectorAll('.alt').forEach(b => {
    b.disabled = true;
    if (b.dataset.l === r.gabarito) b.classList.add('certa');
    else if (b.dataset.l === letra) b.classList.add('errada');
  });
  $('#chute-pos').checked = false;
  atualizarVeredito(false);
  $('#fonte').hidden = r.gabarito_fonte !== 'claude';
  $('#comentario').hidden = !r.comentario; renderRico($('#comentario-txt'), r.comentario);
  $('#resultado').hidden = false;
  carregarFiltros();
}

async function salvarEProxima() {
  if (!S.respondida) return;
  if (!$('#classificar').hidden && (S.tipo || $('#nota').value.trim()))
    await api('/api/classificar', { resposta_id:S.respId, tipo_erro:S.tipo, nota:$('#nota').value });
  proxima();
}
function escolherTipo(t) {
  S.tipo = S.tipo === t ? null : t;
  document.querySelectorAll('.tipos button').forEach(b => b.classList.toggle('sel', b.dataset.t === S.tipo));
}

async function mostrarStats() {
  const { linhas } = await api('/api/stats');
  const t = $('#t-stats'); t.replaceChildren();
  t.append(el('tr', {}, ...['Disciplina', 'Assunto'].map(h => el('th', {}, h)),
    ...['Questões', 'Respondidas', 'Tentativas', 'Acertos', 'Chutes', '% acerto'].map(h => el('th', { class:'num' }, h))));
  const tot = { questoes:0, respondidas:0, tentativas:0, acertos:0, chutes:0 };
  const linha = (a, b, x) => {
    const p = pct(x.acertos, x.tentativas);
    return el('tr', {}, el('td', {}, a), el('td', {}, b),
      ...['questoes', 'respondidas', 'tentativas', 'acertos', 'chutes'].map(k => el('td', { class:'num' }, String(x[k]))),
      el('td', { class:'num ' + classePct(p) }, p === null ? '—' : p + '%'));
  };
  for (const x of linhas) { for (const k in tot) tot[k] += x[k]; t.append(linha(x.disciplina, x.assunto, x)); }
  if (!linhas.length) t.append(el('tr', {}, el('td', { colspan:'8', class:'vazio' }, 'Sem questões ainda.')));
  else t.append(linha('Total', '', tot));
}
async function mostrarCaderno() {
  const { linhas } = await api('/api/caderno');
  const t = $('#t-caderno'); t.replaceChildren();
  t.append(el('tr', {}, ...['Quando', 'Assunto', 'Questão', 'Sua', 'Gab.', 'Tipo', 'Regra / nota'].map(h => el('th', {}, h))));
  for (const x of linhas) {
    const tdQ = el('td', {});
    renderRico(tdQ, (x.codigo ? x.codigo + ' — ' : '') + x.trecho + (x.trecho.length >= 220 ? '…' : ''));
    t.append(el('tr', {}, el('td', {}, x.respondida_em.slice(0, 16).replace('T', ' ')), el('td', {}, x.assunto), tdQ,
      el('td', {}, x.resposta + (x.chute ? ' (chute)' : '')), el('td', {}, x.gabarito), el('td', {}, x.tipo_erro || '—'), el('td', {}, x.nota || '')));
  }
  if (!linhas.length) t.append(el('tr', {}, el('td', { colspan:'7', class:'vazio' }, 'Nenhum erro registrado.')));
}

document.querySelectorAll('nav button').forEach(b => b.onclick = () => {
  document.querySelectorAll('nav button').forEach(x => x.classList.toggle('ativo', x === b));
  for (const v of ['resolver', 'stats', 'caderno', 'simulado']) $('#v-' + v).hidden = v !== b.dataset.v;
  if (b.dataset.v === 'stats') mostrarStats();
  if (b.dataset.v === 'caderno') mostrarCaderno();
  if (b.dataset.v === 'simulado') simLista();
});
$('#disc').onchange = preencherAssuntos;
$('#iniciar').onclick = () => { S.sessao = []; proxima(); };
$('#proxima').onclick = salvarEProxima;
$('#pular').onclick = pular;
$('#confirmar').onclick = confirmar;
$('#chute-pos').onchange = async () => {
  const chute = $('#chute-pos').checked;
  await api('/api/marcar_chute', { resposta_id:S.respId, chute });
  atualizarVeredito(chute);
  carregarFiltros();
};
document.querySelectorAll('.tipos button').forEach(b => b.onclick = () => escolherTipo(b.dataset.t));
$('#contestar').onclick = async () => {
  const obs = prompt('O que está errado no gabarito? (fica registrado para o Claude revisar)');
  if (obs !== null) { await api('/api/contestar', { questao_id:S.q.id, obs }); alert('Registrado.'); }
};
document.addEventListener('keydown', e => {
  if (['TEXTAREA', 'SELECT', 'INPUT'].includes(document.activeElement.tagName) && e.key !== 'Enter') return;
  if ($('#v-resolver').hidden || $('#card').hidden || e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key.toUpperCase();
  if (!S.respondida) {
    if (k === 'P') { pular(); return; }
    if (e.key === 'Enter') { e.preventDefault(); confirmar(); return; }
    if ([...document.querySelectorAll('.alt')].some(b => b.dataset.l === k)) selecionar(k);
  } else {
    if (k === 'X') { $('#chute-pos').checked = !$('#chute-pos').checked; $('#chute-pos').dispatchEvent(new Event('change')); return; }
    if (!$('#classificar').hidden && 'ABCD'.includes(k) && k.length === 1 && document.activeElement.tagName !== 'TEXTAREA') escolherTipo(k);
    if (e.key === 'Enter' && document.activeElement.tagName !== 'TEXTAREA') { e.preventDefault(); salvarEProxima(); }
  }
});
// ---------- Simulado (tabelas próprias; não mexe no banco de questões) ----------
const SIM = { prova:null, timer:null };
const fmtPts = n => String(Math.round(n * 100) / 100).replace('.', ',');
function fmtData(iso) { return iso.slice(0, 16).replace('T', ' '); }

async function simLista() {
  clearInterval(SIM.timer);
  $('#sim-prova').hidden = true; $('#sim-lista').hidden = false;
  const { simulados } = await api('/api/sim/lista');
  const box = $('#sim-lista'); box.replaceChildren();
  if (!simulados.length) { box.append(el('div', { class:'vazio' }, 'Nenhum simulado importado ainda (python3 importar_simulado.py simulados/arquivo.json).')); return; }
  for (const s of simulados) {
    const aberta = s.tentativas.find(t => !t.entregue_em);
    const iniciar = el('button', { class:'btn primario' }, aberta ? 'Continuar' : (s.tentativas.length ? 'Fazer de novo' : 'Começar'));
    iniciar.onclick = async () => {
      if (!aberta && !confirm(`Começar agora? O cronômetro de ${s.duracao_min / 60} h dispara ao abrir a prova.`)) return;
      const r = await api('/api/sim/iniciar', { simulado_id:s.id });
      simAbrir(r.tentativa_id);
    };
    const card = el('div', { class:'card' }, el('h2', {}, s.nome), el('p', { class:'dica', style:'margin-top:0' }, `${s.questoes} questões · ${s.descricao || ''}`));
    const feitas = s.tentativas.filter(t => t.entregue_em);
    if (feitas.length) {
      const t = el('table', {});
      t.append(el('tr', {}, ...['Entregue em', 'Acertos', 'Pontos', 'Situação', ''].map(h => el('th', {}, h))));
      for (const x of feitas) {
        const r = x.resultado, ver = el('button', { class:'btn' }, 'Ver correção');
        ver.onclick = () => simAbrir(x.id);
        t.append(el('tr', {}, el('td', {}, fmtData(x.entregue_em)), el('td', {}, `${r.acertos}/${r.questoes}`),
          el('td', {}, `${fmtPts(r.pontos)} / ${r.max}`), el('td', { class:r.eliminado ? 'p-elim' : 'p-aprov' }, r.eliminado ? 'Eliminado' : 'Classificável'), el('td', {}, ver)));
      }
      card.append(el('div', { class:'scroll' }, t));
    }
    card.append(el('div', { class:'acoes' }, el('span', {}), iniciar));
    box.append(card);
  }
}

async function simAbrir(tid) {
  const p = SIM.prova = await api('/api/sim/prova?tentativa=' + tid);
  const entregue = !!p.tentativa.entregue_em;
  $('#sim-lista').hidden = true; $('#sim-prova').hidden = false;
  $('#sim-nome').textContent = p.simulado.nome;
  $('#sim-entregar').hidden = entregue;
  clearInterval(SIM.timer);
  if (entregue) {
    const min = Math.round((new Date(p.tentativa.entregue_em) - new Date(p.tentativa.iniciada_em)) / 60000);
    $('#sim-tempo').textContent = `Tempo usado: ${Math.floor(min / 60)}h${String(min % 60).padStart(2, '0')}`;
    $('#sim-tempo').classList.remove('acabando');
  } else {
    const fim = new Date(p.tentativa.iniciada_em).getTime() + p.simulado.duracao_min * 60000;
    const tick = () => {
      const s = Math.round((fim - Date.now()) / 1000), a = Math.abs(s);
      const txt = `${Math.floor(a / 3600)}:${String(Math.floor(a % 3600 / 60)).padStart(2, '0')}:${String(a % 60).padStart(2, '0')}`;
      $('#sim-tempo').textContent = s >= 0 ? `Restam ${txt}` : `Tempo esgotado há ${txt}`;
      $('#sim-tempo').classList.toggle('acabando', s < 15 * 60);
    };
    tick(); SIM.timer = setInterval(tick, 1000);
  }
  simResultado(p);
  simRenderQuestoes(p, entregue);
  simContador();
  window.scrollTo({ top:0 });
}

function simResultado(p) {
  const box = $('#sim-resultado'); box.replaceChildren();
  if (!p.resultado) return;
  const r = p.resultado, t = el('table', {});
  t.append(el('tr', {}, el('th', {}, 'Disciplina'), ...['Acertos', 'Em branco', 'Chutes certos', 'Pontos', 'Mínimo'].map(h => el('th', { class:'num' }, h))));
  for (const d of r.disciplinas)
    t.append(el('tr', {}, el('td', {}, d.disciplina), el('td', { class:'num' }, `${d.acertos}/${d.questoes}`), el('td', { class:'num' }, String(d.em_branco)),
      el('td', { class:'num' }, String(d.chutes_certos)), el('td', { class:'num ' + (d.eliminado ? 'p-elim' : '') }, `${fmtPts(d.pontos)} / ${fmtPts(d.max)}`),
      el('td', { class:'num' }, fmtPts(d.minimo))));
  const s = r.resumo;
  t.append(el('tr', {}, el('td', {}, el('strong', {}, 'Objetiva')), el('td', { class:'num' }, `${s.acertos}/${s.questoes}`), el('td', {}), el('td', {}),
    el('td', { class:'num ' + (s.eliminado ? 'p-elim' : 'p-aprov') }, `${fmtPts(s.pontos)} / ${s.max}`), el('td', { class:'num' }, fmtPts(s.minimo_total))));
  const situacao = s.eliminado
    ? 'Eliminado: ficou abaixo do mínimo em pelo menos uma disciplina ou no total da objetiva.'
    : 'Passou dos mínimos. Lembre que a redação só é corrigida para os 15 primeiros da ampla concorrência, então o que conta é a posição.';
  box.append(el('div', { class:'card', style:'margin-bottom:18px' }, el('div', { class:'rotulo' }, 'RESULTADO'), el('div', { class:'scroll' }, t),
    el('p', { class:'dica' }, situacao + ' Chute certo conta ponto aqui, como na prova real, mas fica destacado para você revisar.')));
}

function simRenderQuestoes(p, entregue) {
  const box = $('#sim-questoes'); box.replaceChildren();
  let disc = null, texto = null;
  for (const q of p.questoes) {
    if (q.disciplina !== disc) { disc = q.disciplina; box.append(el('h2', { class:'sim-disc' }, disc + (q.peso > 1 ? ` · peso ${q.peso}` : ''))); }
    if (q.texto && q.texto !== texto) { texto = q.texto; const tx = el('div', { class:'sim-texto' }); renderRico(tx, p.textos[q.texto]); box.append(tx); }
    const enun = el('div', { class:'enunciado' }); renderRico(enun, q.enunciado);
    const card = el('div', { class:'card sim-q' }, el('div', { class:'num' }, `QUESTÃO ${String(q.numero).padStart(2, '0')}`), enun);
    const alts = el('div', {});
    for (const [letra, txt] of Object.entries(q.alternativas)) {
      const span = el('span', {}); renderRico(span, txt);
      const b = el('button', { class:'alt', 'data-l':letra }, el('span', { class:'letra' }, letra), span);
      if (entregue) {
        b.disabled = true;
        if (letra === q.gabarito) b.classList.add('certa'); else if (letra === q.resposta) b.classList.add('errada');
      } else {
        b.classList.toggle('selecionada', letra === q.resposta);
        b.onclick = () => simMarcar(q, q.resposta === letra ? null : letra, alts);
      }
      alts.append(b);
    }
    card.append(alts);
    if (entregue) {
      const ok = q.resposta === q.gabarito;
      card.append(el('div', { class:'veredito ' + (ok && !q.chute ? 'ok' : 'bad') },
        q.resposta == null ? `Em branco — gabarito ${q.gabarito}.` : ok ? (q.chute ? `Acertou no chute — gabarito ${q.gabarito}.` : 'Acertou.') : `Errou — você marcou ${q.resposta}, gabarito ${q.gabarito}.`));
      const com = el('div', {}); renderRico(com, q.comentario);
      card.append(el('div', { class:'comentario' }, el('div', { class:'rotulo' }, `${q.assunto.toUpperCase()} · MODELO: ${q.base}`), com));
    } else {
      const chk = el('input', { type:'checkbox' }); chk.checked = q.chute;
      chk.onchange = () => { q.chute = chk.checked; simSalvar(q); };
      card.append(el('label', { class:'chute-pos' }, chk, ' Chutei esta'));
    }
    box.append(card);
  }
}

async function simSalvar(q) {
  await api('/api/sim/marcar', { tentativa_id:SIM.prova.tentativa.id, questao_id:q.id, resposta:q.resposta, chute:q.chute });
}
async function simMarcar(q, letra, alts) {
  q.resposta = letra;
  alts.querySelectorAll('.alt').forEach(b => b.classList.toggle('selecionada', b.dataset.l === letra));
  simContador();
  await simSalvar(q);
}
function simContador() {
  const qs = SIM.prova.questoes, n = qs.filter(q => q.resposta).length;
  $('#sim-cont').textContent = `${n}/${qs.length} marcadas`;
}
$('#sim-voltar').onclick = simLista;
$('#sim-entregar').onclick = async () => {
  const brancos = SIM.prova.questoes.filter(q => !q.resposta).length;
  if (!confirm(brancos ? `Há ${brancos} questão(ões) em branco. Entregar mesmo assim?` : 'Entregar o simulado? Depois disso não dá para alterar as respostas.')) return;
  await api('/api/sim/entregar', { tentativa_id:SIM.prova.tentativa.id });
  simAbrir(SIM.prova.tentativa.id);
};

carregarFiltros();
if (location.hash === '#simulado') {  // link direto: abre a aba e continua a tentativa em andamento, se houver
  document.querySelector('nav button[data-v="simulado"]').click();
  api('/api/sim/lista').then(({ simulados }) => {
    const t = simulados.flatMap(s => s.tentativas).find(t => !t.entregue_em);
    if (t) simAbrir(t.id);
  });
}
</script>
</body>
</html>
"""


def main():
    conectar().close()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Banco de questões em {url}  (banco: {DB})  — Ctrl+C para sair")
    if "--sem-navegador" not in sys.argv:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
