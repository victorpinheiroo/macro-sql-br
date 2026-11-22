# Plano de execução — macro-sql-br

Ritmo: ~20 h/semana. As horas são **estimativas**; reavalie no fim de cada semana e corte escopo
antes de estender prazo.

## Estado atual

- Catálogo de métricas em YAML validado (`ipca`, `selic`, `selic_meta`, `juro_real`).
- Compilador plano → SQL (`compound`, `sum`, `avg`, `last`); transpila DuckDB → Databricks.
- Guardrails por AST, um teste por regra (14 ataques).
- Verificador em duas camadas: `aggregation_mismatch` (estática, pelo catálogo) e `differential`
  (compara com o caminho de métricas).
- Conjunto de mutações com 5 operadores + relatório (`python -m macrosql.mutation_report obs.parquet`).
- Ingestão SGS → bronze Parquet append-only com `ingested_at` (`python -m macrosql.ingest`).
- Teste de rede: `pipelines/00_egress_check.py` (rodar no Databricks).
- 40 testes, todos com dados **sintéticos**.
- **Pipeline real no Databricks** (2026-11-22): Asset Bundle (`databricks.yml`), job serverless
  `sgs_pipeline` em prod agendado diariamente às 10h (BRT); dev só roda à mão.
  bronze (append-only, `ingested_at`) → silver (último valor por ponto, `is_complete`) → gold
  (`obs` + `series_status`) → Parquet no volume `exports`. Mesmo SQL em DuckDB e Databricks
  (`transform.py`, sqlglot). Gold: 10.467 pontos desde 2000-01-01.
- **Golden set v1**: 16 perguntas em `evals/golden.jsonl`, todas com oráculo externo (IBGE SIDRA
  1737 publicado; Calculadora do Cidadão do BCB). Runner `python -m macrosql.golden` no CI sobre o
  snapshot `data/snapshot/obs.csv`. Caminho de métricas: **16/16 no DuckDB e 16/16 no Databricks
  SQL**, mesmos valores. Ainda sem LLM: mede só a metade determinística.
- **Planejador LLM ponta a ponta** (semana 2): `LLMClient` neutro (`llm.py`) com cache em disco por
  (versão do prompt, provedor, modelo, hash da entrada) e backoff em 429; prompt versionado
  `prompts/planner.yml` (`planner@1`); `plan.py` valida a saída no schema e no catálogo; modelo
  vem de `config/models.yml`. Resultado em `evals/results/planner.md`: 8 modelos gratuitos do
  Databricks, todos com saída estruturada **constrained**; 7/8 acertam 16/16 o número; Llama 3.1
  8B erra g05 (janela de 13 meses no "12 meses até outubro").
- **Semana 3**: golden set com 31 perguntas (15 difíceis: datas relativas com `as_of`, paráfrases,
  janelas fora do ano civil, oráculo por número-índice do IBGE). Caminho SQL livre
  (`freesql.py`, prompt `freesql@1` só com dicionário de dados) + guardrails + DuckDB isolado
  (acesso externo desligado, config travada, timeout). Verificador com 3ª camada, checagem de
  período por AST. Placar: métricas 244/248 vs SQL livre 78/248; verificador 142/142 nas erradas
  (119/142 sem o diferencial); red team 0 inseguras; mutações 114/114, 0/31 falso alarme.

### Linha de base do verificador (dados sintéticos, 4 consultas-semente)

| operador | mutantes | estática | diferencial | qualquer |
| --- | --- | --- | --- | --- |
| rate_summed | 2 | 2 | 2 | 2 |
| level_compounded | 2 | 2 | 2 | 2 |
| series_swap | 2 | 0 | 2 | 2 |
| fisher_as_subtraction | 1 | 0 | 1 | 1 |
| period_shift | 4 | 0 | 2 | 2 |

Falso alarme estático em SQL correto: 0/4. **Não é número de README**: serve para mostrar que o
mecanismo funciona. Achado: período deslocado escapa do diferencial quando a série não mudou no
intervalo (ex.: meta Selic parada entre reuniões do Copom). Correção prevista na semana 3: checar as
datas literais do SQL contra o período do plano.

## Princípios

1. **Toda manchete tem denominador.** Recall por operador + taxa de falso alarme.
2. **Oráculo fora do código.** Cada pergunta do golden set registra `oracle`:
   `publicado` (número da própria fonte) > `calculadora_bcb` (Calculadora do Cidadão) > `planilha`.
   Nenhuma resposta esperada sai do `compile.py`.
3. **Verificação em camadas, cada uma medida:** regras do catálogo → recomputação → período →
   plausibilidade → back-translation (só fica se aumentar o recall; senão vira achado no README).
4. **Prometer só o demonstrável.** Revisões fora do escopo; bronze append-only desde já.
   "Último dado" = referência + data de coleta.
5. **Ambiguidade é caso de teste.** Perguntas cuja resposta esperada é pedir esclarecimento.

## Cronograma (fatia vertical primeiro)

| Semana | Entrega | Critério de pronto |
| --- | --- | --- |
| 1 ✅ | Teste de rede → decidir onde roda a ingestão. Confirmar códigos SGS na fonte. Ingestão real + silver/gold. Golden set v1: 15 perguntas com oráculo externo; runner no CI | Parquet real lido pelo DuckDB; CI roda o golden set em todo PR |
| 2 ✅ | `LLMClient` neutro + cache em disco; teste de saída estruturada nos modelos gratuitos; planejador + caminho de métricas ponta a ponta | Tabela: qual modelo devolve `Plan` válido e em que %; acurácia no golden set por modelo |
| 3 ✅ | SQL livre + guardrails ligados; checagem de período; regras de frequência e unidade; relatório de mutações com dados reais | Placar com recall e falso alarme sobre o golden set real |
| 4 | Esclarecimento + confiança; golden set 30+; FastAPI + Streamlit + Docker; README com números; vídeo | `docker compose up` responde sem conta Databricks; manchete na primeira tela |

**v1.1 (depois de publicado):** SIDRA, Tesouro, comparação com Genie, juro real ex-ante.

## Decisões pendentes

- [ ] **O planejador continua saturado** com 31 perguntas: 6 de 8 modelos fazem 31/31. Erros reais
  vistos: Llama 3.1 8B põe "este ano" em 2022 e usa 13 meses no "12 meses até"; Gemma conta
  "últimos 12 meses" por dias (23/11/2025–22/11/2026, 11 meses completos). Escolher modelo pelo
  planejador exige perguntas ambíguas e fora do catálogo (semana 4: esclarecimento).
- [x] Red team achou brecha no guardrail: `getenv()` passava (no DuckDB do Python a função não
  existe, mas o guardrail não pode depender do motor). Nova regra `no_introspection`: `getenv`,
  `current_setting`, `duckdb_*`, `pragma_*`.
- [ ] Tolerância de 0,02 p.p. deixa passar IPCA somado em janela curta (abr–set/2025: 1,56 vs
  1,569). O verificador pega pelo método; o golden aceita pelo número. Decidir se a correção
  exige método certo, não só número na tolerância.
- [ ] Falhas sem resposta no SQL livre (28/248): erro de binder (8), zero linhas (7), JSON
  ausente (3), sintaxe (2). Medir se uma segunda tentativa com o erro no prompt recupera.
- [x] Saída estruturada: o Gemma 3 12B recusa `format: date` no JSON schema (xgrammar). O
  `LLMClient` remove `title`/`format` do schema e cai para JSON no prompt se o provedor recusar.
  Com isso os 8 modelos ficam em modo constrained.
- [x] Limite de taxa da Free Edition: 429 depois de ~10 chamadas seguidas no mesmo endpoint.
  Backoff exponencial (respeita `Retry-After`) resolve; zero erros de provedor nos 128 casos.

- [x] Resultado do teste de rede → **ingestão no Databricks** (2026-11-22). Serverless da Free Edition
  alcança SGS (200), SIDRA `/values/...` (200), Tesouro Transparente (200) e PyPI (200). A raiz
  `apisidra.ibge.gov.br/` devolve 403 em qualquer lugar; o teste usa um endpoint real.
- [ ] SGS 432 (meta Selic) devolve linhas com **data futura**: em 2026-11-22 o último ponto era
  09/12/2026 (a meta se repete até a próxima reunião do Copom). A ingestão já corta em `--end` = hoje,
  então o bronze não tem linhas futuras; a pergunta "Selic hoje" ainda vira caso do golden set.
- [x] IPCA = SGS 433 confirmado contra a publicação do IBGE (SIDRA 1737, v63). 4390 e 432 conferem
  com o título no portal de dados abertos do BCB.
- [ ] Confirmar códigos SGS: câmbio, dívida bruta e líquida.
- [x] Janela sem dados: o SGS responde **404** `Value(s) not found`, não lista vazia. `sgs.fetch`
  trata como vazio; outro 404 continua levantando erro.
- [x] SGS 4390 inclui o **mês corrente parcial** (em 2026-11-22, nov = 0,66 com o mês pela metade).
  Silver marca `is_complete = false`; gold exclui. Falta a pergunta no golden set ("Selic de
  novembro" deve virar esclarecimento ou aviso).
- [x] Acumulados publicados pelo IBGE (SIDRA 1737): v63 mensal, v69 no ano, v2265 em 12 meses.
- [x] Calculadora do Cidadão (Selic) **não conta a taxa do dia final**: 02/01–31/12/2024 dá 10,8255%;
  01/01/2024–01/01/2025 dá 10,8760%. O oráculo usa a segunda convenção. Resta ±0,012 p.p. contra o
  composto da 4390 (duas casas decimais por mês); tolerância 0,03 p.p. Achado para o README.
- [ ] Tolerância do IPCA: 0,02 p.p. em acumulados (IBGE arredonda o índice; nós compomos variações
  com duas casas). Maior desvio observado: 0,0052 (2022).
