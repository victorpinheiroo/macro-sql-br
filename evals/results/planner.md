Planner `planner@1` on the golden set (31 questions, metrics path; basic = v1, hard = relative dates, paraphrases, custom windows). Numbers are shares of questions.

| model | correct: all | basic | hard | valid plan | exact plan | provider errors | structured output | median latency (s) | mean tokens in/out |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| databricks-meta-llama-3-3-70b-instruct | 31/31 | 16/16 | 15/15 | 31/31 | 30/31 | 0 | constrained | 0.9 | 1107 / 30 |
| databricks-llama-4-maverick | 31/31 | 16/16 | 15/15 | 31/31 | 31/31 | 0 | constrained | 1.0 | 1063 / 30 |
| databricks-meta-llama-3-1-8b-instruct | 29/31 | 15/16 | 14/15 | 31/31 | 28/31 | 0 | constrained | 0.8 | 1087 / 30 |
| databricks-gpt-oss-120b | 31/31 | 16/16 | 15/15 | 31/31 | 31/31 | 0 | constrained | 1.0 | 1080 / 131 |
| databricks-gpt-oss-20b | 31/31 | 16/16 | 15/15 | 31/31 | 31/31 | 0 | constrained | 1.2 | 1080 / 174 |
| databricks-qwen3-next-80b-a3b-instruct | 31/31 | 16/16 | 15/15 | 31/31 | 31/31 | 0 | constrained | 0.8 | 1167 / 38 |
| databricks-qwen35-122b-a10b | 31/31 | 16/16 | 15/15 | 31/31 | 30/31 | 0 | constrained | 1.7 | 1206 / 190 |
| databricks-gemma-3-12b | 30/31 | 16/16 | 14/15 | 31/31 | 27/31 | 0 | constrained | 1.1 | 1219 / 39 |

Misses:

| model | id | trap | got plan | expected plan | error |
| --- | --- | --- | --- | --- | --- |
| databricks-meta-llama-3-1-8b-instruct | g05 | window_12m | `{"metrics": ["ipca"], "start": "2025-10-01", "end": "2026-10-01"}` | `{"metrics": ["ipca"], "start": "2025-11-01", "end": "2026-10-31"}` |  |
| databricks-meta-llama-3-1-8b-instruct | h02 | relative_ytd | `{"metrics": ["ipca"], "start": "2022-01-01", "end": "2022-10-01"}` | `{"metrics": ["ipca"], "start": "2026-01-01", "end": "2026-10-31"}` |  |
| databricks-gemma-3-12b | h01 | relative_latest | `{"metrics": ["ipca"], "start": "2025-11-23", "end": "2026-11-22"}` | `{"metrics": ["ipca"], "start": "2025-11-01", "end": "2026-10-31"}` |  |
