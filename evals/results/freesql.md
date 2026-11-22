Free-SQL path on the golden set (31 questions; model writes the SQL from a data dictionary, no metric rules). Verifier = static + period + differential vs metrics path.

| model | free SQL correct | metrics path correct | provider errors | no answer | guardrail blocks | wrong answers flagged | right answers flagged | unverifiable period |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| databricks-meta-llama-3-3-70b-instruct | 8/31 | 31/31 | 0 | 1 | 0 | 22/22 | 1/8 | 3 |
| databricks-llama-4-maverick | 8/31 | 31/31 | 0 | 7 | 0 | 16/16 | 0/8 | 2 |
| databricks-meta-llama-3-1-8b-instruct | 2/31 | 29/31 | 0 | 10 | 2 | 19/19 | 0/2 | 10 |
| databricks-gpt-oss-120b | 13/31 | 31/31 | 0 | 1 | 0 | 17/17 | 1/13 | 7 |
| databricks-gpt-oss-20b | 10/31 | 31/31 | 0 | 4 | 0 | 17/17 | 1/10 | 4 |
| databricks-qwen3-next-80b-a3b-instruct | 9/31 | 31/31 | 0 | 0 | 0 | 22/22 | 1/9 | 2 |
| databricks-qwen35-122b-a10b | 21/31 | 31/31 | 0 | 0 | 0 | 10/10 | 0/21 | 8 |
| databricks-gemma-3-12b | 7/31 | 30/31 | 0 | 5 | 1 | 19/19 | 0/7 | 3 |

All models: verifier flagged 142/142 wrong answers and 4/78 right ones.
