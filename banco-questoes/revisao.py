#!/usr/bin/env python3
"""Revisão do simulado: explica, do zero, cada questão que você errou, deixou em branco ou chutou.

Uso:  python3 revisao.py        → abre em http://localhost:8766

As explicações são escritas em simulados/explicacoes/<CODIGO DO SIMULADO>/qNN.json e copiadas
para a tabela simulado_explicacoes de questoes.sqlite toda vez que o app abre. O progresso
(o que você refez e o que marcou como entendido) fica em simulado_revisao.
"""
import json
import os
import sys
import webbrowser
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import app
from app import BASE, agora, conectar

PORT = int(os.environ.get("RPORT", 8766))
EXPLICACOES = BASE / "simulados" / "explicacoes"

SCHEMA = """
CREATE TABLE IF NOT EXISTS simulado_explicacoes (
    questao_id    INTEGER PRIMARY KEY REFERENCES simulado_questoes (id) ON DELETE CASCADE,
    conteudo      TEXT NOT NULL,              -- JSON: titulo, ideia, do_zero, passo_a_passo, alternativas, seu_erro, macete, treino
    atualizada_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS simulado_revisao (
    questao_id    INTEGER PRIMARY KEY REFERENCES simulado_questoes (id) ON DELETE CASCADE,
    refeita       TEXT,                       -- letra marcada ao refazer a questão na revisão
    entendi       INTEGER NOT NULL DEFAULT 0,
    atualizada_em TEXT NOT NULL
);
"""

# Última tentativa entregue de cada simulado: é dela que saem os erros e chutes a revisar.
ULTIMAS = """SELECT MAX(id) AS id, simulado_id FROM simulado_tentativas
             WHERE entregue_em IS NOT NULL GROUP BY simulado_id"""


def conectar_rev():
    con = conectar()
    con.executescript(SCHEMA)
    return con


def importar_explicacoes():
    n = 0
    with conectar_rev() as con:
        for pasta in sorted(p for p in EXPLICACOES.glob("*") if p.is_dir()):
            sim = con.execute("SELECT id FROM simulados WHERE codigo = ?", (pasta.name,)).fetchone()
            if not sim:
                print(f"aviso: simulado {pasta.name} não importado; explicações ignoradas")
                continue
            for arq in sorted(pasta.glob("q*.json")):
                e = json.loads(arq.read_text(encoding="utf-8"))
                q = con.execute("SELECT id FROM simulado_questoes WHERE simulado_id = ? AND numero = ?",
                                (sim["id"], e["numero"])).fetchone()
                if not q:
                    raise ValueError(f"{arq}: questão {e['numero']} não existe em {pasta.name}")
                con.execute("""INSERT INTO simulado_explicacoes (questao_id, conteudo, atualizada_em) VALUES (?, ?, ?)
                               ON CONFLICT (questao_id) DO UPDATE SET conteudo = excluded.conteudo, atualizada_em = excluded.atualizada_em
                               WHERE conteudo <> excluded.conteudo""",
                            (q["id"], json.dumps(e, ensure_ascii=False), agora()))
                n += 1
    return n


def situacao(resposta, gabarito, chute):
    if resposta is None:
        return "branco"
    if resposta != gabarito:
        return "errou"
    return "chute" if chute else None


def lista(p):
    with conectar_rev() as con:
        rows = con.execute(f"""
            SELECT s.codigo, s.nome, t.id AS tentativa_id, q.id, q.numero, q.disciplina, q.assunto, q.gabarito,
                   r.resposta, COALESCE(r.chute, 0) AS chute, e.conteudo, v.entendi, v.refeita
            FROM ({ULTIMAS}) t JOIN simulados s ON s.id = t.simulado_id
            JOIN simulado_questoes q ON q.simulado_id = s.id
            LEFT JOIN simulado_respostas r ON r.questao_id = q.id AND r.tentativa_id = t.id
            LEFT JOIN simulado_explicacoes e ON e.questao_id = q.id
            LEFT JOIN simulado_revisao v ON v.questao_id = q.id
            ORDER BY s.id, q.numero""").fetchall()
    sims = {}
    for r in rows:
        sit = situacao(r["resposta"], r["gabarito"], r["chute"])
        if not sit:
            continue
        s = sims.setdefault(r["codigo"], {"codigo": r["codigo"], "nome": r["nome"], "tentativa_id": r["tentativa_id"], "questoes": []})
        s["questoes"].append({"id": r["id"], "numero": r["numero"], "disciplina": r["disciplina"], "assunto": r["assunto"],
                              "situacao": sit, "entendi": bool(r["entendi"]), "refeita": r["refeita"],
                              "acertou_refazendo": r["refeita"] == r["gabarito"] if r["refeita"] else None,
                              "titulo": json.loads(r["conteudo"])["titulo"] if r["conteudo"] else None})
    return {"simulados": list(sims.values())}


def questao(p):
    qid, tid = int(p["id"]), int(p["tentativa"])
    with conectar_rev() as con:
        q = con.execute("SELECT * FROM simulado_questoes WHERE id = ?", (qid,)).fetchone()
        s = con.execute("SELECT textos FROM simulados WHERE id = ?", (q["simulado_id"],)).fetchone()
        r = con.execute("SELECT resposta, chute FROM simulado_respostas WHERE tentativa_id = ? AND questao_id = ?", (tid, qid)).fetchone()
        e = con.execute("SELECT conteudo FROM simulado_explicacoes WHERE questao_id = ?", (qid,)).fetchone()
        v = con.execute("SELECT refeita, entendi FROM simulado_revisao WHERE questao_id = ?", (qid,)).fetchone()
    resposta, chute = (r["resposta"], bool(r["chute"])) if r else (None, False)
    out = {k: q[k] for k in ("id", "numero", "disciplina", "assunto", "enunciado", "gabarito", "comentario")}
    out.update(alternativas=json.loads(q["alternativas"]), texto=json.loads(s["textos"] or "{}").get(q["texto"]) if q["texto"] else None,
               resposta=resposta, chute=chute, situacao=situacao(resposta, q["gabarito"], chute),
               explicacao=json.loads(e["conteudo"]) if e else None,
               refeita=v["refeita"] if v else None, entendi=bool(v["entendi"]) if v else False)
    return out


def salvar(qid, **campos):
    with conectar_rev() as con:
        con.execute("INSERT INTO simulado_revisao (questao_id, atualizada_em) VALUES (?, ?) ON CONFLICT (questao_id) DO NOTHING", (qid, agora()))
        for k, v in campos.items():  # k vem só das chamadas abaixo, nunca do navegador
            con.execute(f"UPDATE simulado_revisao SET {k} = ?, atualizada_em = ? WHERE questao_id = ?", (v, agora(), qid))


def refazer(b):
    salvar(int(b["questao_id"]), refeita=b["resposta"])
    return {"ok": True}


def entendi(b):
    salvar(int(b["questao_id"]), entendi=1 if b.get("entendi") else 0)
    return {"ok": True}


GET_ROUTES = {"/api/lista": lista, "/api/questao": questao}
POST_ROUTES = {"/api/refazer": refazer, "/api/entendi": entendi}


class Handler(app.Handler):
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
<title>Revisão do Simulado</title>
<style>
:root { --bg:#0e1117; --card:#161b24; --line:#2a3140; --text:#e6e8ec; --muted:#9aa3b2; --accent:#6ea8fe; --accent-bg:#17243a;
        --ok:#2fb36d; --ok-bg:#12301f; --bad:#e5534b; --bad-bg:#3a1717; --warn:#d9a441; --warn-bg:#33280f; --code:#0b0e14; }
@media (prefers-color-scheme: light) {
  :root { --bg:#f5f6f8; --card:#ffffff; --line:#d9dde4; --text:#1b1f27; --muted:#5d6675; --accent:#2463d6; --accent-bg:#e8effc;
          --ok:#1d8a52; --ok-bg:#e3f5ea; --bad:#c43c35; --bad-bg:#fbe6e5; --warn:#94650f; --warn-bg:#fbf1dc; --code:#f0f2f5; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:17px/1.65 system-ui, sans-serif; }
header { display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid var(--line); }
header h1 { font-size:18px; margin:0; cursor:pointer; }
main { max-width:820px; margin:0 auto; padding:20px 16px 80px; }
.btn { background:transparent; color:var(--text); border:1px solid var(--line); border-radius:8px; padding:8px 14px; cursor:pointer; font:inherit; font-size:15px; }
.btn.primario { background:var(--accent); border-color:var(--accent); color:#fff; }
.btn:disabled { opacity:.4; cursor:default; }
.barra { height:8px; background:var(--line); border-radius:99px; overflow:hidden; }
.barra > div { height:100%; background:var(--ok); transition:width .3s; }
#progresso { min-width:220px; font-size:14px; color:var(--muted); }
.intro { color:var(--muted); margin:0 0 22px; }
.disc { font-size:14px; letter-spacing:.06em; text-transform:uppercase; color:var(--accent); margin:28px 0 10px; }
.item { display:flex; gap:14px; align-items:center; width:100%; text-align:left; background:var(--card); color:var(--text); border:1px solid var(--line);
        border-radius:12px; padding:12px 16px; margin-bottom:8px; cursor:pointer; font:inherit; }
.item:hover { border-color:var(--accent); }
.item .n { font:700 14px ui-monospace, monospace; color:var(--muted); flex:none; width:34px; }
.item .t { flex:1; }
.item .t small { display:block; color:var(--muted); font-size:13px; }
.tag { flex:none; font:600 12px ui-monospace, monospace; padding:3px 8px; border-radius:6px; text-transform:uppercase; letter-spacing:.04em; }
.tag.errou, .tag.branco { background:var(--bad-bg); color:var(--bad); } .tag.chute { background:var(--warn-bg); color:var(--warn); }
.check { flex:none; width:22px; text-align:center; color:var(--ok); font-weight:700; }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px 22px; margin-bottom:16px; }
.meta { font:12px/1.4 ui-monospace, monospace; color:var(--muted); letter-spacing:.03em; text-transform:uppercase; margin-bottom:10px; }
h2.titulo { font-size:24px; line-height:1.3; margin:4px 0 6px; }
.ideia { font-size:18px; color:var(--muted); margin:0 0 18px; }
.texto-apoio { white-space:pre-wrap; font-size:15px; max-height:260px; overflow:auto; border-left:3px solid var(--accent); padding-left:14px; color:var(--muted); }
details summary { cursor:pointer; color:var(--accent); font-size:15px; margin-bottom:8px; }
.enunciado { white-space:pre-wrap; margin-bottom:14px; }
.alt { display:flex; gap:12px; width:100%; text-align:left; align-items:flex-start; background:transparent; color:var(--text); border:1px solid var(--line);
       border-radius:10px; padding:10px 14px; margin-bottom:8px; cursor:pointer; font:inherit; white-space:pre-wrap; }
.alt:hover:not(:disabled) { border-color:var(--accent); }
.alt:disabled { cursor:default; }
.alt .letra { flex:none; width:26px; height:26px; border-radius:6px; display:grid; place-items:center; background:var(--line); font:600 13px ui-monospace, monospace; }
.alt.certa { background:var(--ok-bg); border-color:var(--ok); } .alt.certa .letra { background:var(--ok); color:#fff; }
.alt.errada { background:var(--bad-bg); border-color:var(--bad); } .alt.errada .letra { background:var(--bad); color:#fff; }
.alt .sua { margin-left:auto; flex:none; font-size:12px; color:var(--muted); align-self:center; }
.convite { background:var(--accent-bg); border-radius:10px; padding:12px 16px; margin-bottom:14px; }
.veredito { font-weight:700; margin:12px 0 0; } .veredito.ok { color:var(--ok); } .veredito.bad { color:var(--bad); }
.secao { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:6px 22px 14px; margin-bottom:16px; }
.secao h3 { display:flex; gap:10px; align-items:center; font-size:19px; margin:16px 0 8px; }
.secao h3 .num { flex:none; width:28px; height:28px; border-radius:50%; background:var(--accent); color:#fff; display:grid; place-items:center; font-size:14px; }
.secao.erro { border-color:var(--bad); } .secao.erro h3 .num { background:var(--bad); }
.secao.macete { border-color:var(--ok); background:var(--ok-bg); } .secao.macete h3 .num { background:var(--ok); }
.rico p { margin:0 0 12px; }
.rico ul, .rico ol { margin:0 0 12px; padding-left:24px; } .rico li { margin-bottom:6px; }
.rico code { font:15px ui-monospace, monospace; background:var(--code); border:1px solid var(--line); border-radius:5px; padding:1px 5px; }
.rico pre { font:14px/1.5 ui-monospace, monospace; background:var(--code); border:1px solid var(--line); border-radius:10px; padding:12px 14px; overflow-x:auto; margin:0 0 12px; }
.rico pre code { background:none; border:0; padding:0; }
.rico blockquote { margin:0 0 12px; padding:10px 14px; border-left:4px solid var(--warn); background:var(--warn-bg); border-radius:0 10px 10px 0; }
.rico b { color:var(--accent); }
.secao.macete .rico b { color:var(--ok); }
.alt-exp { border-left:3px solid var(--line); padding:2px 0 2px 14px; margin-bottom:14px; }
.alt-exp.certa { border-color:var(--ok); } .alt-exp.marcada { border-color:var(--bad); }
.alt-exp .cab { font-weight:700; margin-bottom:4px; }
.alt-exp.certa .cab { color:var(--ok); } .alt-exp.marcada .cab { color:var(--bad); }
.treino { border:1px dashed var(--line); border-radius:12px; padding:14px 16px; margin-bottom:12px; }
.treino .fb { margin-top:8px; }
.rodape { display:flex; flex-wrap:wrap; gap:10px; justify-content:space-between; align-items:center; margin-top:22px; }
.entendi { display:inline-flex; gap:8px; align-items:center; font-weight:600; cursor:pointer; }
.entendi input { width:20px; height:20px; }
.vazio { color:var(--muted); text-align:center; padding:40px 0; }
</style>
</head>
<body>
<header>
  <h1 id="home">Revisão do Simulado</h1>
  <div id="progresso"><div id="prog-txt"></div><div class="barra"><div id="prog-barra" style="width:0"></div></div></div>
</header>
<main>
  <section id="v-lista"></section>
  <section id="v-questao" hidden></section>
</main>
<script>
const $ = s => document.querySelector(s);
const R = { lista:[], tentativa:{}, atual:null };
const ROTULO = { errou:'Errei', branco:'Em branco', chute:'Chutei' };

async function api(path, body) {
  const r = await fetch(path, body ? { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) } : {});
  const j = await r.json();
  if (!r.ok) throw new Error(j.erro || r.status);
  return j;
}
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) k === 'class' ? e.className = v : e.setAttribute(k, v);
  for (const k of kids) if (k != null) e.append(k);
  return e;
}
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
function inline(s) {
  return esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
}
// Formato das explicações: parágrafos separados por linha em branco; "- " lista; "1. " lista numerada;
// "> " caixa de alerta; ``` bloco de código; **negrito** e `código` dentro do texto.
function rico(texto) {
  const box = el('div', { class:'rico' });
  const blocos = [];
  let buf = [], emCodigo = false;
  for (const linha of (texto || '').split('\n')) {
    if (linha.trim().startsWith('```')) {
      if (emCodigo) { blocos.push({ codigo:buf.join('\n') }); buf = []; emCodigo = false; }
      else { if (buf.length) blocos.push(buf); buf = []; emCodigo = true; }
    } else if (emCodigo) buf.push(linha);
    else if (!linha.trim()) { if (buf.length) blocos.push(buf); buf = []; }
    else buf.push(linha);
  }
  if (buf.length) blocos.push(emCodigo ? { codigo:buf.join('\n') } : buf);
  let html = '';
  for (const b of blocos) {
    if (b.codigo !== undefined) html += `<pre><code>${esc(b.codigo)}</code></pre>`;
    else if (b.every(l => /^- /.test(l))) html += '<ul>' + b.map(l => `<li>${inline(l.slice(2))}</li>`).join('') + '</ul>';
    else if (b.every(l => /^\d+\. /.test(l))) html += '<ol>' + b.map(l => `<li>${inline(l.replace(/^\d+\. /, ''))}</li>`).join('') + '</ol>';
    else if (b.every(l => /^> ?/.test(l))) html += `<blockquote>${b.map(l => inline(l.replace(/^> ?/, ''))).join('<br>')}</blockquote>`;
    else html += `<p>${b.map(inline).join('<br>')}</p>`;
  }
  box.innerHTML = html;
  return box;
}
function enunciadoRico(texto) {  // no enunciado, **x** marca o trecho grifado na prova
  const d = el('div', { class:'enunciado' });
  d.innerHTML = esc(texto || '').replace(/\*\*(.+?)\*\*/g, '<b style="color:var(--accent)">$1</b>');
  return d;
}

function todas() { return R.lista.flatMap(s => s.questoes.map(q => ({ ...q, tentativa_id:s.tentativa_id }))); }
function atualizarProgresso() {
  const qs = todas(), ok = qs.filter(q => q.entendi).length;
  $('#prog-txt').textContent = qs.length ? `${ok} de ${qs.length} entendidas` : '';
  $('#prog-barra').style.width = qs.length ? (100 * ok / qs.length) + '%' : 0;
}

async function carregarLista() {
  R.lista = (await api('/api/lista')).simulados;
  atualizarProgresso();
}

async function mostrarLista() {
  await carregarLista();
  $('#v-questao').hidden = true; $('#v-lista').hidden = false;
  const box = $('#v-lista'); box.replaceChildren();
  if (!R.lista.length) { box.append(el('div', { class:'vazio' }, 'Nenhum simulado entregue com erros ou chutes. 🎉')); return; }
  for (const s of R.lista) {
    const n = c => s.questoes.filter(q => q.situacao === c).length;
    box.append(el('h2', { style:'margin:0 0 6px' }, s.nome));
    box.append(el('p', { class:'intro' }, `${n('errou')} erradas, ${n('branco')} em branco e ${n('chute')} acertadas no chute. ` +
      'Chute certo também está aqui: na prova de verdade a sorte pode não se repetir. Abra uma questão, tente de novo e depois leia a explicação com calma.'));
    let disc = null;
    for (const q of s.questoes) {
      if (q.disciplina !== disc) { disc = q.disciplina; box.append(el('h3', { class:'disc' }, disc)); }
      const b = el('button', { class:'item' },
        el('span', { class:'check' }, q.entendi ? '✓' : ''),
        el('span', { class:'n' }, 'Q' + String(q.numero).padStart(2, '0')),
        el('span', { class:'t' }, q.titulo || q.assunto, el('small', {}, q.assunto)),
        el('span', { class:'tag ' + q.situacao }, ROTULO[q.situacao]));
      b.onclick = () => abrir(q.id, s.tentativa_id);
      box.append(b);
    }
  }
  window.scrollTo({ top:0 });
}

async function abrir(id, tentativa) {
  const q = R.atual = await api(`/api/questao?id=${id}&tentativa=${tentativa}`);
  q.tentativa_id = tentativa;
  $('#v-lista').hidden = true; $('#v-questao').hidden = false;
  const box = $('#v-questao'); box.replaceChildren();
  const e = q.explicacao;

  // 1. Cabeçalho
  const cab = el('div', {},
    el('div', { class:'meta' }, `Questão ${String(q.numero).padStart(2, '0')} · ${q.disciplina} · ${q.assunto}`),
    el('h2', { class:'titulo' }, e ? e.titulo : q.assunto));
  if (e && e.ideia) cab.append(el('p', { class:'ideia' }, e.ideia));
  box.append(cab);

  // 2. A questão: primeiro tenta de novo, só depois vê o gabarito
  const card = el('div', { class:'card' });
  if (q.texto) {
    const det = el('details', {}, el('summary', {}, 'Ver o texto de apoio'), el('div', { class:'texto-apoio' }, q.texto));
    card.append(det);
  }
  card.append(enunciadoRico(q.enunciado));
  const convite = el('div', { class:'convite' }, q.refeita
    ? 'Você já refez esta questão. A explicação está liberada logo abaixo.'
    : 'Antes de ler a explicação, tente de novo: clique na alternativa que você acha certa agora. Errar aqui não custa nada e ajuda a memória.');
  card.append(convite);
  const alts = el('div', {});
  const botoes = {};
  for (const [letra, txt] of Object.entries(q.alternativas)) {
    const span = el('span', {}); span.innerHTML = inline(txt);
    const b = botoes[letra] = el('button', { class:'alt' }, el('span', { class:'letra' }, letra), span);
    b.onclick = () => refazer(letra);
    alts.append(b);
  }
  card.append(alts);
  const pular = el('button', { class:'btn' }, 'Não sei, quero ver a explicação');
  pular.onclick = () => revelar(null);
  const veredito = el('div', { class:'veredito' });
  card.append(pular, veredito);
  box.append(card);

  const corpo = el('div', { hidden:'' });
  box.append(corpo);

  async function refazer(letra) {
    await api('/api/refazer', { questao_id:q.id, resposta:letra });
    q.refeita = letra;
    revelar(letra);
  }
  function revelar(letra) {
    pular.remove();
    for (const [l, b] of Object.entries(botoes)) {
      b.disabled = true;
      if (l === q.gabarito) b.classList.add('certa'); else if (l === letra) b.classList.add('errada');
      if (l === q.resposta) b.append(el('span', { class:'sua' }, 'sua resposta no simulado'));
    }
    const orig = q.resposta == null ? 'No simulado você deixou em branco.' : q.situacao === 'chute' ? `No simulado você marcou ${q.resposta} no chute e acertou.` : `No simulado você marcou ${q.resposta}.`;
    if (letra == null) { veredito.className = 'veredito'; veredito.textContent = `Gabarito: ${q.gabarito}. ${orig}`; }
    else if (letra === q.gabarito) { veredito.className = 'veredito ok'; veredito.textContent = `Agora acertou! Gabarito ${q.gabarito}. ${orig} Leia a explicação para ter certeza de que não foi sorte.`; }
    else { veredito.className = 'veredito bad'; veredito.textContent = `Ainda não: o gabarito é ${q.gabarito}. ${orig} Sem problema, a explicação abaixo é para isso.`; }
    convite.remove();
    corpo.hidden = false;
  }

  // 3. A explicação didática
  let n = 0;
  const secao = (titulo, conteudo, cls = '') => el('div', { class:'secao ' + cls }, el('h3', {}, el('span', { class:'num' }, String(++n)), titulo), conteudo);
  if (!e) {
    corpo.append(secao('Comentário', rico(q.comentario)));
  } else {
    corpo.append(secao('Do zero: o que você precisa saber', rico(e.do_zero)));
    corpo.append(secao('Resolvendo a questão passo a passo', rico(e.passo_a_passo)));
    const altBox = el('div', {});
    for (const [letra, txt] of Object.entries(e.alternativas)) {
      const cls = letra === q.gabarito ? 'certa' : letra === q.resposta ? 'marcada' : '';
      const rot = letra === q.gabarito ? 'CORRETA' : letra === q.resposta ? 'errada (foi a que você marcou)' : 'errada';
      altBox.append(el('div', { class:'alt-exp ' + cls }, el('div', { class:'cab' }, `${letra}) ${rot}`), rico(txt)));
    }
    corpo.append(secao('Alternativa por alternativa', altBox));
    corpo.append(secao(q.situacao === 'chute' ? 'Você acertou no chute: onde mora o perigo' : 'Onde você tropeçou', rico(e.seu_erro), 'erro'));
    corpo.append(secao('Para nunca mais esquecer', rico(e.macete), 'macete'));
    if (e.treino && e.treino.length) {
      const tBox = el('div', {}, rico('Questões novas, curtinhas, sobre o mesmo assunto. Responda para ver se a ideia ficou.'));
      e.treino.forEach((t, i) => tBox.append(treino(t, i)));
      corpo.append(secao('Treine agora', tBox));
    }
  }

  // 4. Rodapé: marcar como entendida e navegar
  const qs = todas(), idx = qs.findIndex(x => x.id === q.id);
  const chk = el('input', { type:'checkbox' }); chk.checked = q.entendi;
  chk.onchange = async () => { await api('/api/entendi', { questao_id:q.id, entendi:chk.checked }); await carregarLista(); };
  const ant = el('button', { class:'btn' }, '← Anterior'), prox = el('button', { class:'btn primario' }, 'Próxima →');
  ant.disabled = idx <= 0; prox.disabled = idx < 0 || idx >= qs.length - 1;
  ant.onclick = () => abrir(qs[idx - 1].id, qs[idx - 1].tentativa_id);
  prox.onclick = () => abrir(qs[idx + 1].id, qs[idx + 1].tentativa_id);
  const voltar = el('button', { class:'btn' }, 'Lista');
  voltar.onclick = mostrarLista;
  corpo.append(el('div', { class:'rodape' }, el('label', { class:'entendi' }, chk, 'Entendi esta questão'), el('span', {}, voltar, ' ', ant, ' ', prox)));

  if (q.refeita) revelar(null);
  window.scrollTo({ top:0 });
}

function treino(t, i) {
  const box = el('div', { class:'treino' }, el('div', { class:'meta' }, `Treino ${i + 1}`), rico(t.pergunta));
  const fb = el('div', { class:'fb' });
  const botoes = Object.entries(t.opcoes).map(([letra, txt]) => {
    const span = el('span', {}); span.innerHTML = inline(txt);
    const b = el('button', { class:'alt' }, el('span', { class:'letra' }, letra), span);
    b.onclick = () => {
      botoes.forEach(([l, x]) => { x.disabled = true; if (l === t.resposta) x.classList.add('certa'); else if (l === letra) x.classList.add('errada'); });
      fb.replaceChildren(el('div', { class:'veredito ' + (letra === t.resposta ? 'ok' : 'bad') }, letra === t.resposta ? 'Isso!' : `Não: a resposta é ${t.resposta}.`), rico(t.explicacao));
    };
    box.append(b);
    return [letra, b];
  });
  box.append(fb);
  return box;
}

$('#home').onclick = mostrarLista;
mostrarLista();
</script>
</body>
</html>
"""


def main():
    n = importar_explicacoes()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Revisão do simulado em {url}  ({n} explicações carregadas)  — Ctrl+C para sair")
    if "--sem-navegador" not in sys.argv:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
