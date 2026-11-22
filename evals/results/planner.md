Planner `planner@1` on the golden set (16 questions, metrics path). Numbers are shares of questions.

| model | valid plan | exact plan | correct number | provider errors | structured output | median latency (s) | mean tokens in/out |
| --- | --- | --- | --- | --- | --- | --- | --- |
| databricks-meta-llama-3-3-70b-instruct | 16/16 | 16/16 | 16/16 | 0 | constrained | 0.8 | 1107 / 30 |
| databricks-llama-4-maverick | 16/16 | 16/16 | 16/16 | 0 | constrained | 1.0 | 1063 / 30 |
| databricks-meta-llama-3-1-8b-instruct | 16/16 | 15/16 | 15/16 | 0 | constrained | 0.9 | 1087 / 30 |
| databricks-gpt-oss-120b | 16/16 | 16/16 | 16/16 | 0 | constrained | 1.0 | 1080 / 115 |
| databricks-gpt-oss-20b | 16/16 | 16/16 | 16/16 | 0 | constrained | 1.3 | 1080 / 165 |
| databricks-qwen3-next-80b-a3b-instruct | 16/16 | 16/16 | 16/16 | 0 | constrained | 0.9 | 1167 / 38 |
| databricks-qwen35-122b-a10b | 16/16 | 16/16 | 16/16 | 0 | constrained | 1.7 | 1207 / 177 |
| databricks-gemma-3-12b | 16/16 | 15/16 | 16/16 | 0 | constrained | 1.1 | 1219 / 39 |

Misses:

| model | id | trap | got plan | expected plan | error |
| --- | --- | --- | --- | --- | --- |
| databricks-meta-llama-3-1-8b-instruct | g05 | window_12m | `{"metrics": ["ipca"], "start": "2025-10-01", "end": "2026-10-01"}` | `{"metrics": ["ipca"], "start": "2025-11-01", "end": "2026-10-31"}` |  |
