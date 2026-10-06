# Projeto guiado — Consulta Processual (Spring Boot + Angular + PostgreSQL)

Um sistema pequeno, com cara de Judiciário, que cobre **todos** os requisitos obrigatórios da vaga: API REST em Java, banco relacional com SQL, front em Angular consumindo a API. No fim, ele vai para o seu GitHub e vira o assunto da entrevista.

**Onde criar:** num repositório **separado**, fora desta pasta de estudo (ex.: `~/Documents/consulta-processual`), para ficar limpo como portfólio. Aqui ficam só as anotações.

**Regra de ouro:** os trechos de código abaixo destravam você; as partes marcadas com ✍️ **você escreve sozinho**. É ali que o aprendizado acontece.

```
consulta-processual/
├── api/          ← Spring Boot (Java 21)
├── web/          ← Angular
└── compose.yaml  ← PostgreSQL (e depois tudo)
```

---

## Etapa 0 — Ambiente

Hoje sua máquina tem Node 18 e Docker, mas não tem Java, Maven nem npm.

```bash
# Java 21 e Maven
sudo apt install openjdk-21-jdk maven
java -version            # deve mostrar 21

# Node 22 via nvm (o Node 18 do apt é velho para o Angular atual e veio sem npm)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
# feche e abra o terminal
nvm install 22
npm install -g @angular/cli
ng version
```

**IDE:** IntelliJ IDEA Community (melhor para Java) ou VS Code com o "Extension Pack for Java". Para Angular, VS Code com "Angular Language Service".

## Etapa 1 — Spring Boot no ar

```bash
mkdir -p ~/Documents/consulta-processual && cd ~/Documents/consulta-processual
git init

curl https://start.spring.io/starter.zip \
  -d type=maven-project -d language=java -d javaVersion=21 \
  -d groupId=br.estudo -d artifactId=api -d name=api \
  -d packageName=br.estudo.processos \
  -d dependencies=web,data-jpa,postgresql,validation,flyway,devtools \
  -o api.zip && unzip api.zip -d api && rm api.zip
```

Crie `api/src/main/java/br/estudo/processos/SaudeController.java`:

```java
package br.estudo.processos;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SaudeController {

    @GetMapping("/api/saude")
    public Map<String, String> saude() {
        return Map.of("status", "ok");
    }
}
```

O projeto ainda não sobe porque pediu PostgreSQL. Crie `compose.yaml` na raiz:

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: processos
      POSTGRES_USER: processos
      POSTGRES_PASSWORD: processos
    ports:
      - "5432:5432"
    volumes:
      - dados:/var/lib/postgresql/data
volumes:
  dados:
```

E `api/src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/processos
spring.datasource.username=processos
spring.datasource.password=processos
# quem cria as tabelas é o Flyway; o Hibernate só confere se a entidade bate com o banco
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

```bash
docker compose up -d
cd api && ./mvnw spring-boot:run
curl localhost:8080/api/saude      # {"status":"ok"}
```

**Entenda antes de seguir** (vai cair na entrevista):
- O que `@RestController` faz e por que o `Map` virou JSON sozinho (Jackson).
- O que é o `pom.xml`, o que é uma dependência "starter".
- Por que `ddl-auto=validate` e não `update` em produção.

✅ Commit: `git add . && git commit -m "Projeto Spring Boot com endpoint de saúde"`

## Etapa 2 — Entidade, banco e CRUD

### Migration (o SCHEMA do seu app.py, versionado)

`api/src/main/resources/db/migration/V1__cria_processo.sql`:

```sql
CREATE TABLE processo (
    id                 BIGSERIAL PRIMARY KEY,
    numero             VARCHAR(25)  NOT NULL UNIQUE,   -- formato CNJ com máscara
    classe             VARCHAR(100) NOT NULL,          -- ex.: Procedimento Comum Cível
    assunto            VARCHAR(150) NOT NULL,
    vara               VARCHAR(100) NOT NULL,
    data_distribuicao  DATE         NOT NULL,
    situacao           VARCHAR(20)  NOT NULL,          -- ATIVO, SUSPENSO, ARQUIVADO
    segredo_justica    BOOLEAN      NOT NULL DEFAULT FALSE
);
```

### Camadas

```
controller  → recebe HTTP, valida entrada, devolve status
service     → regra de negócio (ex.: não pode arquivar processo já arquivado)
repository  → acesso ao banco
entity      → espelha a tabela
dto         → o que entra e sai pela API (nunca exponha a entidade direto)
```

Isso é **SRP** do SOLID na prática, e a injeção pelo construtor é **DIP**. Guarde essa frase para a entrevista.

`Processo.java` (pacote `processo`):

```java
@Entity
public class Processo {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String numero;

    private String classe;
    private String assunto;
    private String vara;
    private LocalDate dataDistribuicao;   // vira data_distribuicao automaticamente

    @Enumerated(EnumType.STRING)          // grava "ATIVO", não 0
    private Situacao situacao;

    private boolean segredoJustica;

    protected Processo() {}               // o JPA exige construtor vazio

    // ✍️ construtor com os campos, getters e os setters que fizerem sentido
}
```

`ProcessoRepository.java`:

```java
public interface ProcessoRepository extends JpaRepository<Processo, Long> {
    Optional<Processo> findByNumero(String numero);   // o Spring gera o SQL pelo nome do método
}
```

DTOs como `record`:

```java
public record ProcessoRequest(
        @NotBlank String numero,
        @NotBlank String classe,
        @NotBlank String assunto,
        @NotBlank String vara,
        @NotNull @PastOrPresent LocalDate dataDistribuicao,
        boolean segredoJustica) {}

public record ProcessoResponse(Long id, String numero, String classe, String assunto,
                               String vara, LocalDate dataDistribuicao, Situacao situacao) {
    public static ProcessoResponse de(Processo p) {
        return new ProcessoResponse(p.getId(), p.getNumero(), p.getClasse(), p.getAssunto(),
                p.getVara(), p.getDataDistribuicao(), p.getSituacao());
    }
}
```

Controller:

```java
@RestController
@RequestMapping("/api/processos")
public class ProcessoController {

    private final ProcessoService service;

    public ProcessoController(ProcessoService service) {   // injeção pelo construtor
        this.service = service;
    }

    @GetMapping("/{id}")
    public ProcessoResponse buscar(@PathVariable Long id) {
        return service.buscar(id);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProcessoResponse criar(@RequestBody @Valid ProcessoRequest req) {
        return service.criar(req);
    }
}
```

✍️ **Você escreve:** o `ProcessoService` (`@Service`), o `PUT /{id}`, o `DELETE /{id}` (responde 204) e o `PATCH /{id}/arquivar` com a regra "não pode arquivar o que já está arquivado".

Teste com `curl` ou com o arquivo `.http` do IntelliJ/VS Code (extensão REST Client):

```bash
curl -i -X POST localhost:8080/api/processos -H 'Content-Type: application/json' -d '{
  "numero": "0001234-39.2025.8.01.0001",
  "classe": "Procedimento Comum Cível",
  "assunto": "Indenização por Dano Moral",
  "vara": "1ª Vara Cível de Rio Branco",
  "dataDistribuicao": "2025-03-10",
  "segredoJustica": false
}'
```

✅ Commit.

## Etapa 3 — Número CNJ, erros e paginação

### 3.1 Validar o número CNJ (o diferencial do projeto)

Formato `NNNNNNN-DD.AAAA.J.TR.OOOO`. O dígito `DD` segue o módulo 97 (ISO 7064). A regra de conferência é:

> Junte os dígitos na ordem **N A J TR O DD** (o DV vai para o final). O número é válido se esse inteiro **mod 97 == 1**.

Exemplo válido: `0001234-39.2025.8.01.0001` (TJAC = J 8, TR 01).

```java
public final class NumeroCnj {

    private static final Pattern FORMATO =
            Pattern.compile("\\d{7}-\\d{2}\\.\\d{4}\\.\\d\\.\\d{2}\\.\\d{4}");

    private NumeroCnj() {}

    public static boolean valido(String numero) {
        if (numero == null || !FORMATO.matcher(numero).matches()) {
            return false;
        }
        String d = numero.replaceAll("\\D", "");          // só dígitos: NNNNNNN DD AAAA J TR OOOO
        String reordenado = d.substring(0, 7) + d.substring(9) + d.substring(7, 9);
        // 20 dígitos não cabem num long → BigInteger
        return new BigInteger(reordenado).mod(BigInteger.valueOf(97)).intValue() == 1;
    }
}
```

✍️ **Você escreve:**
1. `static int calcularDv(String sequencial, String ano, String j, String tr, String origem)` → `98 - (N A J TR O "00") mod 97`. Confira: para `0001234`, `2025`, `8`, `01`, `0001` o resultado é **39**.
2. Uma anotação de Bean Validation `@NumeroCnjValido` (interface `@Constraint` + classe `ConstraintValidator`) e use no `ProcessoRequest`. Pesquise "custom constraint Spring Boot".

### 3.2 Erros com status HTTP certo

```java
@RestControllerAdvice
public class TratadorDeErros {

    @ExceptionHandler(ProcessoNaoEncontradoException.class)
    public ProblemDetail naoEncontrado(ProcessoNaoEncontradoException e) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, e.getMessage());
    }
}
```

✍️ Trate também: número duplicado → **409 Conflict**; regra de negócio violada (arquivar duas vezes) → **422**; `MethodArgumentNotValidException` → **400** com a lista de campos inválidos.

### 3.3 Paginação

```java
@GetMapping
public Page<ProcessoResponse> listar(@PageableDefault(size = 20, sort = "dataDistribuicao",
                                     direction = Sort.Direction.DESC) Pageable pageable) {
    return service.listar(pageable);
}
```

Na classe principal, adicione `@EnableSpringDataWebSupport(pageSerializationMode = PageSerializationMode.VIA_DTO)` para o JSON da página ficar estável.

`GET /api/processos?page=0&size=10&sort=numero,asc`

**Regra judicial:** processos com `segredoJustica = true` **não** aparecem na listagem pública. ✍️ Implemente no repository (`findBySegredoJusticaFalse(Pageable)`).

✅ Commit.

## Etapa 4 — Movimentações (1:N) e consultas

`V2__cria_movimentacao.sql`:

```sql
CREATE TABLE movimentacao (
    id           BIGSERIAL PRIMARY KEY,
    processo_id  BIGINT       NOT NULL REFERENCES processo(id) ON DELETE CASCADE,
    data_hora    TIMESTAMP    NOT NULL,
    descricao    VARCHAR(255) NOT NULL
);
CREATE INDEX idx_movimentacao_processo ON movimentacao(processo_id);
```

```java
@Entity
public class Movimentacao {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "processo_id")
    private Processo processo;

    private LocalDateTime dataHora;
    private String descricao;
}
```

✍️ **Você escreve:**
- `GET /api/processos/{id}/movimentacoes` (ordenado da mais recente para a mais antiga) e `POST` para lançar uma nova.
- Filtro: `GET /api/processos?vara=...&situacao=ATIVO&texto=dano` — tente primeiro com `@Query` em JPQL, depois escreva o **SQL puro** equivalente e rode no `psql`:
  ```bash
  docker compose exec db psql -U processos
  ```
- Uma consulta com `JOIN` + `GROUP BY`: quantidade de movimentações por processo, só dos que têm mais de 3 (`HAVING`).

**Leia sobre o problema N+1** (listar 20 processos e o Hibernate fazer 21 SELECTs). Ative `show-sql`, provoque o problema, depois resolva com `JOIN FETCH` ou `@EntityGraph`. É pergunta clássica de pleno.

✅ Commit.

## Etapa 5 — Testes

O Initializr já incluiu `spring-boot-starter-test` (JUnit 5, Mockito, AssertJ).

Teste unitário puro — rápido, sem Spring:

```java
class NumeroCnjTest {

    @Test
    void aceitaNumeroComDigitoCorreto() {
        assertThat(NumeroCnj.valido("0001234-39.2025.8.01.0001")).isTrue();
    }

    @Test
    void rejeitaDigitoErrado() {
        assertThat(NumeroCnj.valido("0001234-40.2025.8.01.0001")).isFalse();
    }

    @ParameterizedTest
    @ValueSource(strings = {"", "123", "0001234392025801000 1", "0001234-39.2025.8.1.0001"})
    void rejeitaFormatoInvalido(String numero) {
        assertThat(NumeroCnj.valido(numero)).isFalse();
    }
}
```

Teste do controller — só a camada web, com o service simulado:

```java
@WebMvcTest(ProcessoController.class)
class ProcessoControllerTest {

    @Autowired MockMvc mvc;
    @MockitoBean ProcessoService service;

    @Test
    void retorna404QuandoNaoExiste() throws Exception {
        when(service.buscar(99L)).thenThrow(new ProcessoNaoEncontradoException(99L));

        mvc.perform(get("/api/processos/99"))
           .andExpect(status().isNotFound());
    }
}
```

✍️ **Você escreve:** teste do `calcularDv`; teste de `POST` com corpo inválido → 400; teste do service com Mockito (arquivar duas vezes lança exceção).

```bash
./mvnw test
```

Bônus: teste de integração com **Testcontainers** (sobe um PostgreSQL de verdade no Docker só para o teste).

✅ Commit.

## Etapa 6 — Front-end Angular

```bash
cd ~/Documents/consulta-processual
ng new web --routing --style=scss --ssr=false
cd web
ng generate interface processos/processo
ng generate service processos/processo
ng generate component processos/lista
ng generate component processos/detalhe
ng generate component processos/formulario
```

**Proxy** para o `ng serve` (porta 4200) falar com a API (8080) sem CORS — `web/proxy.conf.json`:

```json
{ "/api": { "target": "http://localhost:8080", "secure": false } }
```

No `angular.json`, em `serve` → `options`, adicione `"proxyConfig": "proxy.conf.json"`.

Em `app.config.ts`, registre o HttpClient: `providers: [..., provideHttpClient()]`.

O service:

```typescript
@Injectable({ providedIn: 'root' })
export class ProcessoService {
  private http = inject(HttpClient);

  listar(page = 0, size = 10): Observable<Pagina<Processo>> {
    return this.http.get<Pagina<Processo>>('/api/processos', { params: { page, size } });
  }

  buscar(id: number): Observable<Processo> {
    return this.http.get<Processo>(`/api/processos/${id}`);
  }
}
```

O componente de lista (sintaxe de controle de fluxo nova do Angular, `@for` / `@if`):

```typescript
@Component({
  selector: 'app-lista',
  imports: [RouterLink, DatePipe],
  template: `
    <h1>Processos</h1>
    @if (carregando()) {
      <p>Carregando…</p>
    } @else {
      <table>
        <tr><th>Número</th><th>Classe</th><th>Vara</th><th>Distribuição</th></tr>
        @for (p of processos(); track p.id) {
          <tr>
            <td><a [routerLink]="['/processos', p.id]">{{ p.numero }}</a></td>
            <td>{{ p.classe }}</td>
            <td>{{ p.vara }}</td>
            <td>{{ p.dataDistribuicao | date: 'dd/MM/yyyy' }}</td>
          </tr>
        } @empty {
          <tr><td colspan="4">Nenhum processo.</td></tr>
        }
      </table>
    }
  `,
})
export class Lista implements OnInit {
  private service = inject(ProcessoService);
  processos = signal<Processo[]>([]);
  carregando = signal(true);

  ngOnInit() {
    this.service.listar().subscribe(pagina => {
      this.processos.set(pagina.content);
      this.carregando.set(false);
    });
  }
}
```

(Nas versões mais novas do Angular os arquivos gerados se chamam `lista.ts` e a classe `Lista`; nas anteriores, `lista.component.ts` e `ListaComponent`. Use o que o `ng generate` criar.)

✍️ **Você escreve:**
- As rotas em `app.routes.ts`: `/processos`, `/processos/novo`, `/processos/:id`.
- O detalhe, mostrando o processo e a lista de movimentações.
- O formulário com **Reactive Forms** (`FormGroup`, `Validators.required`, um validador de padrão para o número CNJ) e exibição dos erros 400/409 que a API devolve.
- Botões de paginação (anterior / próxima).

**Entenda:** componente, template, binding (`{{ }}`, `[prop]`, `(evento)`, `[(ngModel)]`), service + injeção de dependência, Observable/subscribe, signals, rotas. Essa é a lista que o entrevistador vai percorrer.

✅ Commit.

## Etapa 7 — Git, CI e Docker

**Git como num time:**
```bash
git switch -c feature/filtro-por-vara
# ... trabalha, commita
git push -u origin feature/filtro-por-vara
# abre Pull Request no GitHub, revisa, faz merge
```
Pratique pelo menos uma vez: resolver um conflito de merge e fazer um `git rebase main`.

**CI — `.github/workflows/ci.yml`:**

```yaml
name: CI
on: [push, pull_request]
jobs:
  api:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: api } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: 21, cache: maven }
      - run: ./mvnw -B test
  web:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: web } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm, cache-dependency-path: web/package-lock.json }
      - run: npm ci
      - run: npx ng build
```

✍️ **Você escreve:** um `Dockerfile` para a API (multi-stage: estágio com Maven compila, estágio com JRE roda o `.jar`) e acrescenta o serviço `api` no `compose.yaml`.

**README do projeto:** o que é, print da tela, como rodar (`docker compose up`), decisões técnicas (por que DTO, por que Flyway, como valida o CNJ). O recrutador lê isso antes do código.

## Etapa 8 — Bônus: o mesmo endpoint em PHP

Só para você conseguir dizer "já fiz em PHP também e sei a diferença". Num diretório `php/`:

```php
<?php
// php/index.php — rode com: php -S localhost:8000 index.php
// (instale: sudo apt install php-cli php-pgsql)
header('Content-Type: application/json; charset=utf-8');

$pdo = new PDO('pgsql:host=localhost;dbname=processos', 'processos', 'processos', [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
]);

if ($_SERVER['REQUEST_METHOD'] === 'GET' && preg_match('#^/api/processos/(\d+)$#', $_SERVER['REQUEST_URI'], $m)) {
    $stmt = $pdo->prepare('SELECT * FROM processo WHERE id = :id AND NOT segredo_justica');
    $stmt->execute(['id' => (int) $m[1]]);       // prepared statement = proteção contra SQL injection
    $processo = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$processo) {
        http_response_code(404);
        echo json_encode(['erro' => 'Processo não encontrado']);
        return;
    }
    echo json_encode($processo);
    return;
}

http_response_code(404);
```

Compare com o Spring: aqui você fez à mão o roteamento, a conversão para JSON e o tratamento de erro — é o que o seu `app.py` faz em Python. Em projeto PHP real, isso fica com **Laravel** (rotas, Eloquent ORM, migrations, validação) — o equivalente do Spring Boot no mundo PHP.
