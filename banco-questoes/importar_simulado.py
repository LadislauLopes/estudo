#!/usr/bin/env python3
"""Importa um simulado (JSON) para as tabelas simulados/simulado_questoes de questoes.sqlite.

Uso: python3 importar_simulado.py simulados/simulado-01.json

As questões do simulado ficam separadas do banco de questões: não aparecem em "Resolver"
nem nas estatísticas. Reimportar o mesmo código atualiza as questões pelo número,
sem apagar as tentativas já feitas.
"""
import json
import sys

from app import agora, conectar


def main(caminho):
    s = json.load(open(caminho, encoding="utf-8"))
    for q in s["questoes"]:
        if q["gabarito"] not in q["alternativas"]:
            raise ValueError(f"questão {q['numero']}: gabarito '{q['gabarito']}' fora das alternativas")
    with conectar() as con:
        campos = (s["nome"], s.get("descricao"), s.get("duracao_min", 240), json.dumps(s.get("textos") or {}, ensure_ascii=False),
                  json.dumps(s["regras"], ensure_ascii=False))
        atual = con.execute("SELECT id FROM simulados WHERE codigo = ?", (s["codigo"],)).fetchone()
        if atual:
            sid = atual["id"]
            con.execute("UPDATE simulados SET nome = ?, descricao = ?, duracao_min = ?, textos = ?, regras = ? WHERE id = ?", campos + (sid,))
        else:
            sid = con.execute("INSERT INTO simulados (codigo, nome, descricao, duracao_min, textos, regras, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (s["codigo"],) + campos + (agora(),)).lastrowid
        for q in s["questoes"]:
            con.execute("""INSERT INTO simulado_questoes (simulado_id, numero, disciplina, assunto, peso, texto, enunciado, alternativas, gabarito, comentario, base)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT (simulado_id, numero) DO UPDATE SET disciplina = excluded.disciplina, assunto = excluded.assunto,
                           peso = excluded.peso, texto = excluded.texto, enunciado = excluded.enunciado, alternativas = excluded.alternativas,
                           gabarito = excluded.gabarito, comentario = excluded.comentario, base = excluded.base""",
                        (sid, q["numero"], q["disciplina"], q["assunto"], q.get("peso", 1), q.get("texto"), q["enunciado"],
                         json.dumps(q["alternativas"], ensure_ascii=False), q["gabarito"], q.get("comentario"), q.get("base")))
    print(f"{s['codigo']}: {len(s['questoes'])} questões importadas (simulado id {sid})")


if __name__ == "__main__":
    main(sys.argv[1])
