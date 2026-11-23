End to end on the golden set (43 questions), planner `planner@2`. A case is correct when the route matches and, when a number is expected, it is within tolerance.

| model | correct | metrics | free SQL | clarify | decline | route ok | median model time (s) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| databricks-meta-llama-3-3-70b-instruct | **33/43** | 24/31 | 2/3 | 2/4 | 5/5 | 34/43 | 1.9 |
| databricks-llama-4-maverick | **41/43** | 30/31 | 2/3 | 4/4 | 5/5 | 41/43 | 1.0 |
| databricks-meta-llama-3-1-8b-instruct | **9/43** | 3/31 | 0/3 | 1/4 | 5/5 | 12/43 | 0.7 |
| databricks-gpt-oss-120b | **40/43** | 30/31 | 3/3 | 3/4 | 4/5 | 41/43 | 1.3 |
| databricks-gpt-oss-20b | **36/43** | 25/31 | 2/3 | 4/4 | 5/5 | 39/43 | 1.4 |
| databricks-qwen3-next-80b-a3b-instruct | **40/43** | 29/31 | 2/3 | 4/4 | 5/5 | 42/43 | 1.7 |
| databricks-qwen35-122b-a10b | **42/43** | 30/31 | 3/3 | 4/4 | 5/5 | 43/43 | 2.0 |
| databricks-gemma-3-12b | **37/43** | 26/31 | 2/3 | 4/4 | 5/5 | 39/43 | 1.0 |

Misses:

| model | id | trap | expected | got | detail |
| --- | --- | --- | --- | --- | --- |
| databricks-meta-llama-3-3-70b-instruct | g01 | inflation_summed | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-3-70b-instruct | g13 | rate_summed | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-3-70b-instruct | h01 | relative_latest | metrics | error | could not plan the question: plan: Input should be a valid date or datetime, input is too short |
| databricks-meta-llama-3-3-70b-instruct | h03 | relative_month | metrics | error | could not plan the question: plan: Input should be a valid date or datetime, input is too short |
| databricks-meta-llama-3-3-70b-instruct | h04 | relative_today | metrics | error | could not plan the question: plan: Input should be a valid date or datetime, input is too short |
| databricks-meta-llama-3-3-70b-instruct | h12 | custom_window | metrics | out_of_scope | Este sistema informa quanto foram os números; não faz previsões nem recomendações. |
| databricks-meta-llama-3-3-70b-instruct | h15 | custom_window | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-3-70b-instruct | c02 | ambiguous_selic | clarify | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-3-70b-instruct | c04 | not_yet_published | clarify | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-3-70b-instruct | f02 | count_changes | free_sql | free_sql |  |
| databricks-llama-4-maverick | h04 | relative_today | metrics | out_of_scope | Este sistema informa quanto foram os números; não faz previsões nem recomendações. |
| databricks-llama-4-maverick | f02 | count_changes | free_sql | error | execution: BinderException: Binder Error: WHERE clause cannot contain window functions!

LINE 1: ....ref_date BETWEEN '2023-01-01' AND '2023-12-31' AND o.value  |
| databricks-meta-llama-3-1-8b-instruct | g01 | inflation_summed | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | g02 | inflation_summed | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | g03 | inflation_summed | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | g04 | inflation_summed | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | g05 | window_12m | metrics | metrics | plan {"metrics": ["ipca"], "start": "2025-10-01", "end": "2026-10-01"} value 4.722526242616998 |
| databricks-meta-llama-3-1-8b-instruct | g06 | window_12m | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | g07 | inflation_summed | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | g08 | single_month | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | g10 | level_aggregated | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | g11 | level_aggregated | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | g12 | level_aggregated | metrics | clarify | A pergunta tem mais de uma leitura. |
| databricks-meta-llama-3-1-8b-instruct | g13 | rate_summed | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | g14 | rate_summed | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | g15 | fisher_as_subtraction | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | g16 | fisher_as_subtraction | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | h01 | relative_latest | metrics | metrics | plan {"metrics": ["ipca"], "start": "2026-10-01", "end": "2026-10-01"} value 0.14000000000000679 |
| databricks-meta-llama-3-1-8b-instruct | h02 | relative_ytd | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | h03 | relative_month | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | h04 | relative_today | metrics | out_of_scope | Este sistema informa quanto foram os números; não faz previsões nem recomendações. |
| databricks-meta-llama-3-1-8b-instruct | h05 | relative_year | metrics | out_of_scope | Este sistema informa quanto foram os números; não faz previsões nem recomendações. |
| databricks-meta-llama-3-1-8b-instruct | h06 | paraphrase | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | h07 | paraphrase | metrics | out_of_scope | Este sistema informa quanto foram os números; não faz previsões nem recomendações. |
| databricks-meta-llama-3-1-8b-instruct | h08 | paraphrase | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | h09 | paraphrase | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | h10 | custom_window | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | h12 | custom_window | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | h13 | custom_window | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | h14 | level_on_date | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | c01 | ambiguous_selic | clarify | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | c02 | ambiguous_selic | clarify | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | c04 | not_yet_published | clarify | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | f01 | argmax | free_sql | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-meta-llama-3-1-8b-instruct | f02 | count_changes | free_sql | free_sql |  |
| databricks-meta-llama-3-1-8b-instruct | f03 | max_level | free_sql | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-gpt-oss-120b | h03 | relative_month | metrics | metrics | plan {"metrics": ["ipca"], "start": "2026-09-01", "end": "2026-09-30"} value 0.8199999999999985 |
| databricks-gpt-oss-120b | c04 | not_yet_published | clarify | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-gpt-oss-120b | s02 | advice | out_of_scope | error | could not plan the question: no JSON object in output |
| databricks-gpt-oss-20b | g01 | inflation_summed | metrics | error | no JSON object in output |
| databricks-gpt-oss-20b | g02 | inflation_summed | metrics | free_sql |  |
| databricks-gpt-oss-20b | g05 | window_12m | metrics | error | execution: BinderException: Binder Error: Ambiguous reference to column name "series_id" (use: 'obs.series_id' or 'series.series_id')

LINE 1: ... obs JOIN seri |
| databricks-gpt-oss-20b | h01 | relative_latest | metrics | metrics | plan {"metrics": ["ipca"], "start": "2025-10-01", "end": "2026-09-30"} value 4.576119675071899 |
| databricks-gpt-oss-20b | h02 | relative_ytd | metrics | metrics | plan {"metrics": ["ipca"], "start": "2026-01-01", "end": "2026-09-30"} value 3.9513166123103627 |
| databricks-gpt-oss-20b | h03 | relative_month | metrics | metrics | plan {"metrics": ["ipca"], "start": "2026-09-01", "end": "2026-09-30"} value 0.8199999999999985 |
| databricks-gpt-oss-20b | f02 | count_changes | free_sql | error | no JSON object in output |
| databricks-qwen3-next-80b-a3b-instruct | h03 | relative_month | metrics | metrics | plan {"metrics": ["ipca"], "start": "2026-09-01", "end": "2026-09-30"} value 0.8199999999999985 |
| databricks-qwen3-next-80b-a3b-instruct | h13 | custom_window | metrics | unavailable | Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e juro real). |
| databricks-qwen3-next-80b-a3b-instruct | f02 | count_changes | free_sql | free_sql |  |
| databricks-qwen35-122b-a10b | h03 | relative_month | metrics | metrics | plan {"metrics": ["ipca"], "start": "2026-09-01", "end": "2026-09-30"} value 0.8199999999999985 |
| databricks-gemma-3-12b | h01 | relative_latest | metrics | clarify | O período pedido vai além do último dado completo publicado. |
| databricks-gemma-3-12b | h02 | relative_ytd | metrics | clarify | O período pedido vai além do último dado completo publicado. |
| databricks-gemma-3-12b | h03 | relative_month | metrics | metrics | plan {"metrics": ["ipca"], "start": "2026-09-01", "end": "2026-09-30"} value 0.8199999999999985 |
| databricks-gemma-3-12b | h07 | paraphrase | metrics | clarify | A pergunta tem mais de uma leitura. |
| databricks-gemma-3-12b | h08 | paraphrase | metrics | free_sql |  |
| databricks-gemma-3-12b | f02 | count_changes | free_sql | free_sql |  |
