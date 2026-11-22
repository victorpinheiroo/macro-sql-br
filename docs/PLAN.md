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
- 38 testes, todos com dados **sintéticos**.

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
| 1 | Teste de rede → decidir onde roda a ingestão. Confirmar códigos SGS na fonte. Ingestão real + silver/gold. Golden set v1: 15 perguntas com oráculo externo; runner no CI | Parquet real lido pelo DuckDB; CI roda o golden set em todo PR |
| 2 | `LLMClient` neutro + cache em disco; teste de saída estruturada nos modelos gratuitos; planejador + caminho de métricas ponta a ponta | Tabela: qual modelo devolve `Plan` válido e em que %; acurácia no golden set por modelo |
| 3 | SQL livre + guardrails ligados; checagem de período; regras de frequência e unidade; relatório de mutações com dados reais | Placar com recall e falso alarme sobre o golden set real |
| 4 | Esclarecimento + confiança; golden set 30+; FastAPI + Streamlit + Docker; README com números; vídeo | `docker compose up` responde sem conta Databricks; manchete na primeira tela |

**v1.1 (depois de publicado):** SIDRA, Tesouro, comparação com Genie, juro real ex-ante.

## Decisões pendentes

- [x] Resultado do teste de rede → **ingestão no Databricks** (2026-11-22). Serverless da Free Edition
  alcança SGS (200), SIDRA `/values/...` (200), Tesouro Transparente (200) e PyPI (200). A raiz
  `apisidra.ibge.gov.br/` devolve 403 em qualquer lugar; o teste usa um endpoint real.
- [ ] SGS 432 (meta Selic) devolve linhas com **data futura**: em 2026-11-22 o último ponto era
  09/12/2026 (a meta se repete até a próxima reunião do Copom). "Último dado" precisa cortar em
  `data <= data de coleta`; virar pergunta do golden set.
- [ ] Confirmar códigos SGS: IPCA (433), câmbio, dívida bruta e líquida.
- [ ] Confirmar quais acumulados o IBGE publica para usar como oráculo.
- [ ] Ver como o SGS responde a uma janela sem dados e tratar em `sgs.fetch`.
