#!/usr/bin/env python3
"""Importa questões de um arquivo JSON para questoes.sqlite (usado pelo Claude).

Uso: python3 importar.py arquivo.json

Formato: lista de objetos
  {"codigo": "Q2345678", "banca": "FGV", "ano": 2024, "orgao": "...", "cargo": "...",
   "disciplina": "Estruturas de Dados", "assunto": "Pilhas e filas",
   "tipo": "ME" | "CE", "enunciado": "...", "alternativas": {"A": "...", ...},
   "gabarito": "C", "gabarito_fonte": "qconcursos" | "oficial" | "claude", "comentario": "...",
   "resposta_anterior": {"resposta": "B", "data": "2026-09-22"}}   # opcional: já respondida no QConcursos

Questões com o mesmo código são atualizadas em vez de duplicadas.
"""
import json
import sys

from app import agora, conectar

CAMPOS = ("banca", "ano", "orgao", "cargo", "disciplina", "assunto", "tipo", "enunciado",
          "alternativas", "gabarito", "gabarito_fonte", "comentario")


def validar(q, i):
    for c in ("disciplina", "assunto", "tipo", "enunciado", "gabarito"):
        if not q.get(c):
            raise ValueError(f"questão {i}: falta '{c}'")
    if q["tipo"] == "ME":
        alts = q.get("alternativas") or {}
        if len(alts) < 2 or q["gabarito"] not in list(alts) + ["X"]:
            raise ValueError(f"questão {i}: gabarito '{q['gabarito']}' fora das alternativas {list(alts)}")
    elif q["gabarito"] not in ("C", "E", "X"):
        raise ValueError(f"questão {i}: certo/errado exige gabarito C, E ou X")


def main(caminho):
    dados = json.load(open(caminho, encoding="utf-8"))
    novas = atualizadas = respostas = 0
    with conectar() as con:
        for i, q in enumerate(dados, 1):
            validar(q, i)
            q.setdefault("gabarito_fonte", "qconcursos")
            valores = [json.dumps(q[c], ensure_ascii=False) if c == "alternativas" and q.get(c) else q.get(c) for c in CAMPOS]
            atual = con.execute("SELECT id FROM questoes WHERE codigo = ?", (q["codigo"],)).fetchone() if q.get("codigo") else None
            if atual:
                qid = atual["id"]
                con.execute(f"UPDATE questoes SET {', '.join(c + ' = ?' for c in CAMPOS)} WHERE id = ?", valores + [qid])
                atualizadas += 1
            else:
                qid = con.execute(f"INSERT INTO questoes (codigo, {', '.join(CAMPOS)}, criada_em) VALUES (?, {', '.join('?' * len(CAMPOS))}, ?)",
                                  [q.get("codigo")] + valores + [agora()]).lastrowid
                novas += 1
            ant = q.get("resposta_anterior")
            if ant:
                data = ant.get("data") or agora()[:10]
                ja = con.execute("SELECT 1 FROM respostas WHERE questao_id = ? AND origem = 'qconcursos' AND respondida_em = ?",
                                 (qid, data)).fetchone()
                if not ja:
                    resp = ant["resposta"].upper()
                    con.execute("INSERT INTO respostas (questao_id, respondida_em, resposta, correta, chute, origem) VALUES (?, ?, ?, ?, ?, 'qconcursos')",
                                (qid, data, resp, int(resp == q["gabarito"] or q["gabarito"] == "X"), int(bool(ant.get("chute")))))
                    respostas += 1
    print(f"{novas} novas · {atualizadas} atualizadas · {respostas} respostas anteriores registradas")


if __name__ == "__main__":
    main(sys.argv[1])
