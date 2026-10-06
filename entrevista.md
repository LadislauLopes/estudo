# Entrevista técnica — perguntas prováveis

Como usar: leia a pergunta, **responda em voz alta** sem olhar, depois confira. Uma resposta de pleno tem três partes: **o conceito em uma frase, um exemplo do seu projeto, um cuidado/trade-off.** Marque `[x]` quando conseguir responder bem duas vezes seguidas.

---

## 1. Sobre você e o projeto

- [ ] **"Me fala do seu projeto."** — Ensaie em 3 minutos: o problema (consulta processual), a stack (Spring Boot, PostgreSQL, Angular), uma decisão técnica (validação do número CNJ por módulo 97 na API, com teste), uma dificuldade (problema N+1, como resolveu), o que faria a seguir.
- [ ] **"Por que Java e não PHP?"** — Ecossistema maduro em sistemas corporativos e judiciais (PJe é Java), tipagem estática ajuda em sistemas grandes, Spring resolve injeção de dependência, segurança e transações. Sem desmerecer PHP: com Laravel, o desenvolvimento é muito produtivo, e você já fez um endpoint em PHP para comparar.
- [ ] **"Você tem experiência profissional com essas tecnologias?"** — Seja honesto: fale do que você construiu, dos testes que escreveu e de como aprende rápido (o banco de questões em Python que você fez para o concurso é um exemplo real de sistema seu, com banco e servidor HTTP).

## 2. Java

- [ ] **`==` x `equals()`** — `==` compara referência (mesmo objeto na memória); `equals()` compara conteúdo. Para `String`, sempre `equals()`.
- [ ] **Por que String é imutável?** — Segurança, pode ser compartilhada (string pool), é thread-safe, o hash pode ficar em cache. Para concatenar em laço, use `StringBuilder`.
- [ ] **ArrayList x LinkedList** — ArrayList: acesso por índice O(1), inserir no meio O(n). LinkedList: inserir/remover nas pontas O(1), acesso O(n). Na prática, quase sempre ArrayList.
- [ ] **HashMap: como funciona?** — Calcula o `hashCode()` da chave, vai para um bucket; colisões viram lista (e árvore a partir de 8 elementos). Se sobrescrever `equals`, **tem** que sobrescrever `hashCode`.
- [ ] **Checked x unchecked exception** — Checked o compilador obriga a tratar (`IOException`); unchecked herda de `RuntimeException` e não obriga. Em Spring, regra de negócio costuma ser unchecked, tratada num `@RestControllerAdvice`.
- [ ] **O que é `Optional`?** — Um contêiner que deixa explícito que o valor pode não existir, evitando `NullPointerException`. `findById` retorna `Optional`; uso `orElseThrow(...)`.
- [ ] **Streams** — Processamento declarativo de coleções: `filter`, `map`, `collect`/`toList`. É lazy: nada roda até a operação terminal.
- [ ] **`record`** — Classe imutável de dados, com construtor, getters, `equals`, `hashCode` e `toString` gerados. Uso para DTOs.
- [ ] **Interface x classe abstrata** — Interface define contrato, uma classe implementa várias. Classe abstrata pode ter estado e construtor, mas só se herda de uma.

## 3. Spring Boot e JPA

- [ ] **Injeção de dependência / IoC** — Em vez de a classe criar o que usa (`new`), o Spring cria e entrega. Uso injeção pelo construtor: deixa a dependência explícita, permite `final` e facilita teste com mock.
- [ ] **`@Component`, `@Service`, `@Repository`, `@Controller`** — Todos registram um bean; os nomes indicam a camada. `@Repository` ainda traduz exceções do banco.
- [ ] **`@RestController` x `@Controller`** — `@RestController` = `@Controller` + `@ResponseBody`: o retorno vira JSON, não o nome de uma view.
- [ ] **`@Transactional`** — Abre transação no início do método e faz commit no fim, ou rollback se sair `RuntimeException`. Fica no service, não no controller. Pegadinha: chamar um método `@Transactional` da mesma classe não passa pelo proxy e a anotação não vale.
- [ ] **Por que não expor a entidade direto na API?** — Acopla o banco ao contrato da API, pode vazar campos (ex.: segredo de justiça), pode causar loop de serialização em relacionamentos e `LazyInitializationException`. Por isso DTO.
- [ ] **Problema N+1** — Uma consulta para a lista + uma para cada item ao acessar um relacionamento LAZY. Resolvo com `JOIN FETCH`, `@EntityGraph` ou projeção em DTO.
- [ ] **LAZY x EAGER** — LAZY só carrega quando acessa; EAGER carrega junto sempre. Padrão: `@ManyToOne` é EAGER, `@OneToMany` é LAZY. Boa prática: deixar tudo LAZY e buscar junto só quando precisa.
- [ ] **Flyway / migrations** — Scripts SQL versionados (`V1__...`, `V2__...`) aplicados em ordem; o banco de cada ambiente fica igual ao do código. Por isso `ddl-auto=validate`.

## 4. REST e HTTP

- [ ] **O que torna uma API REST?** — Recursos identificados por URL (`/processos/10`), verbos HTTP com significado, sem estado entre requisições (stateless), representações (JSON), códigos de status corretos.
- [ ] **Verbos** — GET lê; POST cria; PUT substitui inteiro; PATCH altera parte; DELETE remove. **Idempotentes:** GET, PUT, DELETE (repetir dá o mesmo resultado). POST não é.
- [ ] **Status que você usou** — 200 OK, 201 Created (POST), 204 No Content (DELETE), 400 dados inválidos, 401 não autenticado, 403 sem permissão, 404 não encontrado, 409 conflito (número duplicado), 422 regra de negócio, 500 erro do servidor.
- [ ] **Autenticação em API** — Stateless com **JWT**: o login devolve um token assinado, o cliente manda em `Authorization: Bearer ...`, o servidor valida a assinatura sem consultar sessão. Em órgãos públicos é comum OAuth2/OpenID Connect com Keycloak (o PJe usa) ou login gov.br.
- [ ] **CORS** — O navegador bloqueia uma página de uma origem chamar API de outra origem, a menos que a API autorize com cabeçalhos `Access-Control-Allow-*`. No Spring: `@CrossOrigin` ou configuração global. No desenvolvimento, você usou proxy do Angular.
- [ ] **Paginação** — Nunca devolver a tabela inteira. `?page=0&size=20&sort=campo,desc`; o banco faz `LIMIT/OFFSET`.
- [ ] **Versionamento de API** — `/api/v1/...` ou cabeçalho; permite evoluir sem quebrar quem já consome.

## 5. SQL e banco de dados

- [ ] **INNER x LEFT JOIN** — INNER traz só o que casa nas duas tabelas; LEFT traz tudo da esquerda, com NULL onde não casou (ex.: processos **sem** movimentação).
- [ ] **WHERE x HAVING** — WHERE filtra linhas antes do agrupamento; HAVING filtra grupos depois do `GROUP BY`.
- [ ] **Índice** — Estrutura (árvore B) que acelera busca; custa espaço e deixa INSERT/UPDATE mais lentos. Crio em colunas de filtro e de JOIN (`processo_id`, `numero`).
- [ ] **Transação e ACID** — Atomicidade, Consistência, Isolamento, Durabilidade. Exemplo: arquivar processo e lançar movimentação de arquivamento — ou as duas acontecem, ou nenhuma.
- [ ] **Normalização** — Evitar redundância: 1FN (valores atômicos), 2FN (sem dependência parcial da chave), 3FN (sem dependência transitiva). Ex.: vara virar tabela própria em vez de texto repetido.
- [ ] **SQL injection** — Concatenar entrada do usuário no SQL permite injetar comandos. Proteção: prepared statements / parâmetros (`:id`), que JPA e PDO já fazem.
- [ ] **Escreva no quadro:** "os 5 processos com mais movimentações em 2025, por vara". (Treine: `JOIN`, `WHERE`, `GROUP BY`, `ORDER BY ... DESC`, `LIMIT 5`.)

## 6. Angular

- [ ] **Componente** — Classe TypeScript + template HTML + estilo; unidade da interface. Hoje são standalone (sem NgModule).
- [ ] **Bindings** — `{{ valor }}` interpolação; `[prop]="x"` property binding (componente → template); `(click)="f()"` event binding (template → componente); `[(ngModel)]` two-way.
- [ ] **Service e DI** — Lógica e acesso a dados ficam em `@Injectable` services, injetados nos componentes (`inject()` ou construtor). `providedIn: 'root'` = uma instância para o app todo.
- [ ] **Observable x Promise** — Observable pode emitir vários valores, é lazy (só roda com `subscribe`) e cancelável; Promise emite um e já começa. HttpClient devolve Observable. Cuidado com subscription que não é encerrada (vazamento de memória) — `async` pipe ou `takeUntilDestroyed` resolvem.
- [ ] **Signals** — Valores reativos (`signal()`, `computed()`, `effect()`): quando mudam, o Angular atualiza só o que depende deles. É a direção atual do framework.
- [ ] **Ciclo de vida** — `ngOnInit` (buscar dados iniciais), `ngOnChanges` (input mudou), `ngOnDestroy` (limpar).
- [ ] **Template-driven x Reactive Forms** — Reactive: o formulário é definido no TypeScript (`FormGroup`, validadores), mais testável e melhor para formulários complexos. Template-driven: com `ngModel` no HTML, simples.
- [ ] **Comunicação entre componentes** — Pai → filho por `@Input`/`input()`; filho → pai por `@Output`/`output()`; irmãos por um service compartilhado.
- [ ] **Interceptor** — Intercepta toda requisição do HttpClient: incluir token JWT, tratar 401 globalmente, mostrar loading.

## 7. React (se perguntarem)

- [ ] **Angular x React** — Angular é framework completo e opinativo (rotas, HTTP, formulários, DI inclusos, TypeScript obrigatório). React é biblioteca de UI: você escolhe roteador, estado, etc. React usa JSX e fluxo unidirecional; Angular, templates HTML com bindings.
- [ ] **Hooks** — `useState` (estado local), `useEffect` (efeitos colaterais, como buscar dados; o array de dependências controla quando roda), `useMemo`/`useCallback` (memorização).
- [ ] **Props x state** — Props vêm do pai, são somente leitura; state é do componente, mudar dispara nova renderização.
- [ ] **Virtual DOM** — Representação em memória; React compara a versão nova com a antiga (reconciliação) e aplica no DOM só a diferença.

## 8. PHP (se perguntarem)

- [ ] **PHP moderno** — PHP 8: tipos em parâmetros e retorno, `match`, enums, promoção de propriedade no construtor, JIT. Composer gerencia dependências; PSR-4 para autoload.
- [ ] **Laravel** — Framework MVC: rotas, Eloquent (ORM, Active Record), migrations, validação, filas. Equivalente ao Spring Boot no ecossistema PHP.
- [ ] **Como cada requisição roda** — No modelo clássico (PHP-FPM), cada requisição começa do zero e não guarda estado na memória entre requisições; no Java, a aplicação fica de pé o tempo todo.

## 9. Engenharia

- [ ] **SOLID com exemplo do projeto** — S: controller só cuida de HTTP, service de regra. O: novo tipo de notificação = nova classe que implementa `Notificador`, sem mexer nas outras. L: qualquer `Notificador` pode substituir outro. I: interfaces pequenas. D: service depende de `ProcessoRepository` (abstração), injetada pelo Spring.
- [ ] **Padrões de projeto que você usou** — Repository, DTO, Strategy (notificadores), Singleton (beans do Spring são singleton por padrão), Builder, Observer (Observable do RxJS).
- [ ] **Pirâmide de testes** — Muitos unitários (rápidos, `NumeroCnjTest`), alguns de integração (`@WebMvcTest`, Testcontainers), poucos ponta a ponta. Mock isola a unidade testada.
- [ ] **CI/CD** — CI: todo push compila e roda testes automaticamente (seu GitHub Actions). CD: o que passou é entregue em homologação/produção automaticamente.
- [ ] **Merge x rebase** — Merge preserva o histórico e cria commit de merge; rebase reaplica seus commits em cima da main, histórico linear. Nunca rebase em branch compartilhada já publicada.
- [ ] **Arquitetura orientada a serviços / microsserviços** — Sistema dividido em serviços que se comunicam por API (REST, filas). Ganha deploy e escala independentes; paga com complexidade de rede, consistência e monitoramento. Monólito bem modularizado costuma ser o começo certo.
- [ ] **"Como você investigaria um bug em produção que você não consegue reproduzir?"** — Logs e correlação por ID de requisição, reproduzir com os dados do caso (respeitando LGPD), escrever um teste que falha, corrigir, o teste passa, deploy.

## 10. Área judicial

- [ ] Explique a estrutura do número único CNJ e como o DV é verificado.
- [ ] O que é a TPU (classes, assuntos, movimentos padronizados pelo CNJ) e por que isso importa para integração e estatística (DataJud).
- [ ] O que é segredo de justiça e como você garantiria na API que esses processos não vazam (filtro no repository + teste automatizado + checagem de permissão).
- [ ] O que é o PJe e o MNI (interoperabilidade entre sistemas de tribunais via web services).

## 11. Perguntas para você fazer ao final

- O projeto é para qual cliente/órgão? Sistema novo ou sustentação de um existente?
- Qual a stack exata (versão do Java, Angular ou React) e como é o fluxo de deploy?
- Como o time é organizado — Scrum, Kanban? Tem code review?
- O que diferencia um pleno que se destaca nesse time nos primeiros 3 meses?
