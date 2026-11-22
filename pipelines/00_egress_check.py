# Databricks notebook source
# MAGIC %md
# MAGIC # Egress check — can this workspace reach the public data APIs?
# MAGIC Run once on Free Edition serverless compute. The result decides where ingestion lives:
# MAGIC - all OK      -> ingestion runs as a Databricks job (bronze written directly)
# MAGIC - any blocked -> ingestion runs in GitHub Actions and uploads Parquet to a UC Volume

# COMMAND ----------

import json
import time
import urllib.error
import urllib.request

TARGETS = {
    # 3 most recent points of the Copom target rate (SGS 432)
    "bcb_sgs": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/3?formato=json",
    # IBGE SIDRA: last monthly IPCA change (table 1737, var 63). The API root returns 403 by design.
    "ibge_sidra": "https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/63/p/last%201",
    # Tesouro Transparente portal root
    "tesouro": "https://www.tesourotransparente.gov.br/",
    # Control: a host that is usually allowed (package index)
    "control_pypi": "https://pypi.org/simple/",
}

results = []
for name, url in TARGETS.items():
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "macro-sql-br-egress-check"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(300).decode("utf-8", errors="replace")
            results.append(
                {
                    "target": name,
                    "ok": True,
                    "status": resp.status,
                    "ms": int((time.time() - t0) * 1000),
                    "sample": body[:120],
                }
            )
    except urllib.error.HTTPError as e:
        # An HTTP error still proves the host is reachable.
        results.append(
            {
                "target": name,
                "ok": True,
                "status": e.code,
                "ms": int((time.time() - t0) * 1000),
                "sample": str(e)[:120],
            }
        )
    except Exception as e:  # DNS failure, proxy refusal, timeout -> blocked
        results.append(
            {
                "target": name,
                "ok": False,
                "status": None,
                "ms": int((time.time() - t0) * 1000),
                "sample": f"{type(e).__name__}: {e}"[:200],
            }
        )

print(json.dumps(results, indent=2, ensure_ascii=False))

# COMMAND ----------

display(spark.createDataFrame(results))  # noqa: F821 (spark/display exist in Databricks)

# COMMAND ----------

# Return the results so `databricks jobs get-run-output` can read them from the CLI.
dbutils.notebook.exit(json.dumps(results, ensure_ascii=False))  # noqa: F821
