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


GET_ROUTES = {"/api/proxima": proxima, "/api/filtros": lambda p: filtros(),
              "/api/stats": lambda p: stats(), "/api/caderno": lambda p: caderno()}
POST_ROUTES = {"/api/responder": responder, "/api/classificar": classificar, "/api/contestar": contestar}


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
.controles { display:flex; flex-wrap:wrap; gap:16px; align-items:center; color:var(--muted); font-size:14px; margin-top:6px; }
.veredito { font-weight:600; margin:16px 0 6px; } .veredito.ok { color:var(--ok); } .veredito.bad { color:var(--bad); }
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
      <div class="controles">
        <label><input type="checkbox" id="chute"> Chutei (X)</label>
        <span id="timer">00:00</span>
        <span id="restam"></span>
      </div>
      <div id="resultado" hidden>
        <div class="veredito" id="veredito"></div>
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
      <div class="dica">Atalhos: letra da alternativa para responder · X marca chute · depois de responder, A/B/C/D classifica o erro e Enter vai para a próxima.</div>
    </div>
    <div id="vazio" class="vazio" hidden></div>
  </section>
  <section id="v-stats" hidden><div class="scroll"><table id="t-stats"></table></div>
    <p class="dica">Chute certo não conta como acerto. Cores pela regra do plano: abaixo de 70% volta com teoria; de 70% a 85% só questões; acima de 85% questões mais difíceis.</p></section>
  <section id="v-caderno" hidden><div class="scroll"><table id="t-caderno"></table></div></section>
</main>
<script>
const $ = s => document.querySelector(s);
const S = { q:null, respId:null, sessao:[], t0:0, respondida:false, tipo:null, assuntos:[], timer:null };

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
  Object.assign(S, { respId:null, respondida:false, tipo:null });
  $('#vazio').hidden = true; $('#card').hidden = false; $('#resultado').hidden = true;
  $('#chute').checked = false; $('#nota').value = '';
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
    b.onclick = () => responder(letra);
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

async function responder(letra) {
  if (S.respondida || !S.q) return;
  S.respondida = true; clearInterval(S.timer);
  const chute = $('#chute').checked;
  const r = await api('/api/responder', { questao_id:S.q.id, resposta:letra, chute, tempo_seg:Math.round((Date.now() - S.t0) / 1000) });
  S.respId = r.resposta_id; S.sessao.push(S.q.id);
  document.querySelectorAll('.alt').forEach(b => {
    b.disabled = true;
    if (b.dataset.l === r.gabarito) b.classList.add('certa');
    else if (b.dataset.l === letra) b.classList.add('errada');
  });
  const v = $('#veredito');
  v.textContent = r.gabarito === 'X' ? 'Questão anulada.' : r.correta ? (chute ? `Acertou no chute — gabarito ${r.gabarito}. Conta como erro no caderno.` : `Acertou — gabarito ${r.gabarito}.`) : `Errou — gabarito ${r.gabarito}.`;
  v.className = 'veredito ' + (r.correta && !chute ? 'ok' : 'bad');
  $('#fonte').hidden = r.gabarito_fonte !== 'claude';
  $('#comentario').hidden = !r.comentario; renderRico($('#comentario-txt'), r.comentario);
  $('#classificar').hidden = r.correta && !chute;
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
  for (const v of ['resolver', 'stats', 'caderno']) $('#v-' + v).hidden = v !== b.dataset.v;
  if (b.dataset.v === 'stats') mostrarStats();
  if (b.dataset.v === 'caderno') mostrarCaderno();
});
$('#disc').onchange = preencherAssuntos;
$('#iniciar').onclick = () => { S.sessao = []; proxima(); };
$('#proxima').onclick = salvarEProxima;
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
    if (k === 'X') { $('#chute').checked = !$('#chute').checked; return; }
    if ([...document.querySelectorAll('.alt')].some(b => b.dataset.l === k)) responder(k);
  } else {
    if (!$('#classificar').hidden && 'ABCD'.includes(k) && k.length === 1 && document.activeElement.tagName !== 'TEXTAREA') escolherTipo(k);
    if (e.key === 'Enter' && document.activeElement.tagName !== 'TEXTAREA') { e.preventDefault(); salvarEProxima(); }
  }
});
carregarFiltros();
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
