# Ponte Python → Java · TypeScript · PHP

Você já escreveu o banco de questões em Python. Aqui está a **mesma ideia** nas linguagens da vaga, para aprender por comparação em vez de começar do zero. Digite os exemplos — não copie e cole.

Foco: **Java** (back-end da vaga) e **TypeScript** (Angular). PHP aparece só para você reconhecer e comparar.

---

## 1. Variáveis e tipos

```python
# Python — tipagem dinâmica
numero = "0001234-39.2025.8.01.0001"
ano = 2025
ativo = True
valor = 1500.50
```

```java
// Java — tipagem estática: o tipo vem antes do nome
String numero = "0001234-39.2025.8.01.0001";
int ano = 2025;               // primitivo
boolean ativo = true;         // minúsculo!
double valor = 1500.50;       // dinheiro de verdade: BigDecimal
var outro = "Java 10+ infere o tipo com var";  // ainda é String, só não escreveu
```

```typescript
// TypeScript — tipo depois do nome, e opcional quando dá para inferir
const numero: string = "0001234-39.2025.8.01.0001";
let ano = 2025;               // inferido como number (não existe int x double)
const ativo: boolean = true;
```

```php
<?php
// PHP — toda variável começa com $
$numero = "0001234-39.2025.8.01.0001";
$ano = 2025;
$ativo = true;
```

| Pegadinha | Python | Java | TS/JS | PHP |
|---|---|---|---|---|
| Nulo | `None` | `null` | `null` e `undefined` | `null` |
| Comparar texto | `==` | **`.equals()`** (`==` compara referência!) | `===` | `===` |
| Divisão inteira | `7 // 2` | `7 / 2` → 3 (se ambos int) | `Math.floor(7 / 2)` | `intdiv(7, 2)` |
| Concatenar | `f"{a} {b}"` | `a + " " + b` ou `"%s %s".formatted(a, b)` | `` `${a} ${b}` `` | `"$a $b"` ou `$a . " " . $b` |
| Fim de instrução | quebra de linha | `;` obrigatório | `;` opcional | `;` obrigatório |
| Blocos | indentação | `{ }` | `{ }` | `{ }` |

## 2. Coleções

```python
partes = ["Maria", "João"]
partes.append("Ana")
por_vara = {"1ª Cível": 120, "2ª Cível": 98}
ativos = [p for p in processos if p.ativo]
```

```java
List<String> partes = new ArrayList<>(List.of("Maria", "João"));
partes.add("Ana");
Map<String, Integer> porVara = new HashMap<>();
porVara.put("1ª Cível", 120);
porVara.get("1ª Cível");                // 120 — null se não existir (não dá KeyError)

// list comprehension → Stream
List<Processo> ativos = processos.stream()
        .filter(p -> p.isAtivo())
        .toList();

// map + soma
int total = porVara.values().stream().mapToInt(Integer::intValue).sum();
```

```typescript
const partes: string[] = ["Maria", "João"];
partes.push("Ana");
const porVara: Record<string, number> = { "1ª Cível": 120 };
const ativos = processos.filter(p => p.ativo);
const numeros = processos.map(p => p.numero);
```

```php
$partes = ["Maria", "João"];
$partes[] = "Ana";                      // append
$porVara = ["1ª Cível" => 120];         // array associativo = dict
$ativos = array_filter($processos, fn($p) => $p->ativo);
```

**Atenção em Java:** `List.of(...)` é **imutável** — `add` lança `UnsupportedOperationException`. Por isso o `new ArrayList<>(List.of(...))` acima.

## 3. Funções e controle de fluxo

```python
def calcular_dv(sequencial: int, ano: int) -> int:
    if sequencial <= 0:
        raise ValueError("sequencial inválido")
    for i in range(3):
        print(i)
    return 42
```

```java
// Em Java não existe função solta: tudo é método dentro de uma classe
public class Calculadora {
    public static int calcularDv(int sequencial, int ano) {
        if (sequencial <= 0) {
            throw new IllegalArgumentException("sequencial inválido");
        }
        for (int i = 0; i < 3; i++) {
            System.out.println(i);
        }
        return 42;
    }
}
```

```typescript
function calcularDv(sequencial: number, ano: number): number {
  if (sequencial <= 0) throw new Error("sequencial inválido");
  for (let i = 0; i < 3; i++) console.log(i);
  return 42;
}
const dobro = (x: number) => x * 2;   // arrow function = lambda
```

```php
function calcularDv(int $sequencial, int $ano): int {
    if ($sequencial <= 0) throw new InvalidArgumentException("sequencial inválido");
    for ($i = 0; $i < 3; $i++) echo $i;
    return 42;
}
```

### Exceções em Java: checked x unchecked

- **Checked** (`IOException`, `SQLException`): o compilador obriga a tratar (`try/catch`) ou declarar (`throws`).
- **Unchecked** (`RuntimeException` e filhas: `IllegalArgumentException`, `NullPointerException`): não obriga.
- No Spring, você costuma criar exceções unchecked (`ProcessoNaoEncontradoException extends RuntimeException`) e tratar todas num lugar só (`@RestControllerAdvice` — etapa 3).

## 4. Classes

```python
class Processo:
    def __init__(self, numero: str, vara: str):
        self.numero = numero
        self._vara = vara

    def descricao(self) -> str:
        return f"{self.numero} ({self._vara})"
```

```java
public class Processo {
    private final String numero;   // private + getter = encapsulamento
    private String vara;

    public Processo(String numero, String vara) {   // construtor = __init__
        this.numero = numero;                        // this = self
        this.vara = vara;
    }

    public String getNumero() { return numero; }
    public String getVara() { return vara; }
    public void setVara(String vara) { this.vara = vara; }

    public String descricao() {
        return numero + " (" + vara + ")";
    }
}

// Java 16+: para dados imutáveis (DTOs), record gera construtor, getters, equals e toString
public record ProcessoResumo(String numero, String vara) {}
// uso: resumo.numero()  ← sem "get"
```

```typescript
// Em Angular você usa interface para "formato de dados" vindo da API
export interface Processo {
  id: number;
  numero: string;
  vara: string;
  segredoJustica?: boolean;   // ? = opcional
}

// e class para serviços/componentes
class ProcessoUtil {
  constructor(private readonly numero: string) {}   // atalho: declara e atribui
  descricao(): string { return `Processo ${this.numero}`; }
}
```

```php
class Processo {
    public function __construct(
        private string $numero,     // PHP 8: promoção de propriedade, igual ao TS
        private string $vara,
    ) {}
    public function descricao(): string { return "{$this->numero} ({$this->vara})"; }
}
$p = new Processo("0001234-39.2025.8.01.0001", "1ª Cível");
echo $p->descricao();               // -> em vez de .
```

### Interface e herança em Java

```java
public interface Notificador {          // contrato
    void notificar(String mensagem);
}

public class EmailNotificador implements Notificador {
    @Override
    public void notificar(String mensagem) { /* ... */ }
}

// Classe herda de UMA classe (extends) e implementa VÁRIAS interfaces (implements)
```

## 5. TypeScript que o Angular exige

O Angular usa TypeScript o tempo todo. O mínimo para não travar:

```typescript
// Generics: Observable<Processo[]> = "um fluxo que vai entregar uma lista de Processo"
this.http.get<Processo[]>("/api/processos").subscribe(lista => this.processos = lista);

// Union types
type Situacao = "ATIVO" | "ARQUIVADO" | "SUSPENSO";

// Optional chaining e nullish coalescing
const vara = processo?.vara ?? "não informada";

// Desestruturação e spread
const { numero, vara } = processo;
const copia = { ...processo, vara: "2ª Cível" };

// async/await com Promise (no Angular você usa mais Observable, mas precisa reconhecer)
async function carregar(): Promise<Processo[]> {
  const resp = await fetch("/api/processos");
  return resp.json();
}
```

**Observable x Promise** (pergunta clássica): Promise entrega **um** valor, uma vez, e começa a executar na hora. Observable (RxJS) pode entregar **vários** valores ao longo do tempo, só começa quando alguém faz `subscribe` e pode ser cancelado. O `HttpClient` do Angular devolve Observable.

## 6. Mapa mental: seu `app.py` x Spring Boot x Angular

| No seu banco de questões (Python) | Spring Boot | Angular |
|---|---|---|
| `BaseHTTPRequestHandler.do_GET` + `if path == ...` | `@RestController` + `@GetMapping("/api/...")` | — |
| `sqlite3.connect` + SQL na mão | `JpaRepository` (SQL gerado) ou `@Query` | — |
| `SCHEMA = "CREATE TABLE..."` | Entidade `@Entity` + migration Flyway | — |
| `json.dumps(resultado)` | Automático (Jackson) | — |
| HTML montado em string | — | Componente + template HTML |
| `fetch` no JS da página | — | `HttpClient` num `@Injectable` service |
| `python3 app.py` | `./mvnw spring-boot:run` | `ng serve` |
