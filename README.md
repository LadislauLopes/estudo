# Vaga SONDA — Desenvolvedor Full Stack Pleno (Java/PHP + Angular/React)

**Vaga:** [carrera.sonda.com · 1435869500](https://carrera.sonda.com/job/Assis-Brasil-Desenvolvedor-Full-Stack-Pleno-JavaPHP-%2B-AngularReact-Acre/1435869500/)  
**Local:** Via Verde, Rio Branco/AC — 100% presencial, 07h às 16h, segunda a sexta  
**Esta pasta:** o plano para sair de "tenho os requisitos no papel" para "consigo programar e explicar isso numa entrevista".

| Arquivo | Para que serve |
|---|---|
| `README.md` | Análise da vaga, escolha da stack e cronograma |
| `ponte-python.md` | Você já programa em Python: a mesma coisa escrita em Java, TypeScript e PHP |
| `projeto-guiado.md` | O projeto que você vai construir — um mini sistema de consulta processual, em 8 etapas |
| `entrevista.md` | Perguntas técnicas prováveis, com a resposta que um pleno daria |
| `vagas-stefanini.md` | Vagas remotas da Stefanini que combinam com o seu perfil, com links e prazos (pesquisa de 08/10/2026) |

---

## 1. O que a vaga pede, de verdade

| Requisito | Tipo | Leitura |
|---|---|---|
| Superior em TI | obrigatório | Você tem |
| Java, PHP, JavaScript **ou** TypeScript | obrigatório | É **"ou"**: basta dominar um back-end. Não tente aprender os quatro |
| Angular **ou** React | obrigatório | Idem: um framework |
| APIs REST (desenvolver e consumir) | obrigatório | Back e front conversando — é o centro do projeto guiado |
| SQL e banco relacional | obrigatório | Você já usa SQLite no banco de questões; falta JOIN, índice, transação, paginação |
| Área judicial | desejável | Diferencial forte — ver seção 3 |
| SOA, padrões de projeto, SOLID | desejável | Teoria já está no plano do concurso |
| Git | desejável | Você já usa. Falta branch, PR, rebase x merge |
| Testes automatizados, CI/CD | desejável | JUnit + GitHub Actions no projeto |

**Conclusão:** a vaga não exige saber tudo. Exige que você mostre **um back-end + um front-end + REST + SQL** funcionando juntos, e que você saiba explicar as decisões. Um projeto pequeno, completo e no GitHub vale mais que dez cursos pela metade.

## 2. Escolha da stack: **Java (Spring Boot) + Angular**

| Critério | Java + Angular | PHP + React |
|---|---|---|
| Sistemas judiciais | PJe (CNJ) e a maioria dos sistemas de tribunal são Java | Menos comum no Judiciário |
| Sobreposição com o concurso | Java, POO, TypeScript e Angular já estão no `plano-estudo-v3.md` (branch `concurso`) | PHP só aparece como leitura |
| Curva para quem vem de Python | Java é mais verboso, mas o Spring resolve muito sozinho | PHP é mais parecido com Python; React é mais "solto" |
| Mercado de órgãos públicos / grandes integradoras | Muito forte | Forte |

Fique com **Java + Angular**. Se na entrevista perguntarem de PHP ou React, `ponte-python.md` e `entrevista.md` dão o suficiente para responder com conceito e mostrar que você sabe as diferenças. Trocar de stack no meio do caminho é o erro mais caro aqui.

## 3. O diferencial: área judicial

A vaga é em Via Verde, onde fica a sede do TJAC — é muito provável que o cliente seja o Tribunal de Justiça do Acre (confirme na entrevista, com naturalidade: "o projeto é para o Tribunal?"). Saber o vocabulário coloca você à frente de quem só sabe código:

- **Número único CNJ** (Resolução CNJ 65/2008): `NNNNNNN-DD.AAAA.J.TR.OOOO` — sequencial, dígito verificador, ano, segmento da Justiça (8 = Estadual), tribunal (01 = TJAC), unidade de origem. O DV é calculado por módulo 97. **Você vai implementar isso no projeto.**
- **Tabelas Processuais Unificadas (TPU)** do CNJ: classes, assuntos e movimentos padronizados.
- **PJe** (Processo Judicial eletrônico, Java), **MNI** (Modelo Nacional de Interoperabilidade — web services entre sistemas de tribunais), **DataJud** (base nacional de metadados processuais, tem API pública).
- Conceitos: processo, partes (autor/réu), classe, assunto, vara/unidade, distribuição, movimentação, sigilo/segredo de justiça.
- **LGPD** em dados processuais: dados de partes são pessoais; processos sob segredo de justiça não aparecem em consulta pública.

## 4. Como conciliar com o concurso (22/11)

O concurso continua sendo a prioridade até 22/11. A boa notícia é que os dois estudos se alimentam:

| No plano do concurso você estuda... | ...e na vaga você **pratica** |
|---|---|
| Java (saída de código, coleções, exceções) | Escrever a API em Spring Boot |
| POO, SOLID, Patterns | Camadas controller / service / repository, injeção de dependência |
| TypeScript e frameworks front-end | O front em Angular |
| SQL e banco de dados | Modelagem com JPA, migrations, consultas com JOIN |
| APIs, HTTP, REST | Desenhar e consumir os endpoints |

**Ritmo sugerido:** 1 h por dia, 6 dias por semana, **em cima** do plano do concurso, de preferência no dia em que o tema correspondente cair lá. Quando o concurso apertar (as duas semanas finais), pause o projeto e mantenha só 20 min de `entrevista.md`.

## 5. Cronograma — 6 semanas

Cada etapa está detalhada em `projeto-guiado.md`. Marque conforme avança.

**Semana 1 — Ambiente e Java do zero até "rodar"**
- [ ] Instalar JDK 21, Maven, Node 22 e Docker (etapa 0)
- [ ] Ler `ponte-python.md` seções 1 a 4, digitando cada exemplo
- [ ] Etapa 1: projeto Spring Boot no ar, `GET /api/saude` respondendo

**Semana 2 — API REST com banco**
- [ ] Etapa 2: entidade `Processo`, PostgreSQL no Docker, repository, CRUD
- [ ] Etapa 3: validação do número CNJ (dígito verificador), erros HTTP corretos, paginação

**Semana 3 — Relacionamentos, SQL e testes**
- [ ] Etapa 4: movimentações (1:N), consulta com filtro, DTOs
- [ ] Etapa 5: testes com JUnit 5 e MockMvc

**Semana 4 — Angular**
- [ ] Ler `ponte-python.md` seção 5 (TypeScript)
- [ ] Etapa 6: front Angular — lista paginada, detalhe, formulário consumindo a API

**Semana 5 — Profissionalizar**
- [ ] Etapa 7: Git com branches e PR, GitHub Actions rodando os testes, Docker Compose subindo tudo
- [ ] README do projeto com print e instruções — é o que o recrutador vai abrir

**Semana 6 — Entrevista**
- [ ] Etapa 8 (bônus PHP): reescrever o `GET /processos` em PHP puro, só para conseguir falar da diferença
- [ ] `entrevista.md` inteiro, respondendo em voz alta, sem olhar
- [ ] Ensaiar a apresentação do projeto em 3 minutos

**Se a entrevista for marcada antes:** faça `entrevista.md` + etapas 1 a 3. Um CRUD com validação CNJ funcionando já é algo concreto para mostrar e explicar.
