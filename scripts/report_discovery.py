"""Summarise all discovery runs into reports/discovery_summary.md."""
import glob
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp.feed import ANNOUNCE_TYPES  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load(name, mode):
    rows = []
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "discovery", mode, "*", "*", name))):
        run = os.path.relpath(os.path.dirname(path), os.path.join(ROOT, "data", "discovery", mode))
        with open(path, encoding="utf-8") as f:
            rows += [{**json.loads(line), "run": run.replace(os.sep, " ")} for line in f]
    return pd.DataFrame(rows)


def md(df):
    return df.to_markdown(index=False) if len(df) else "_(ไม่มีข้อมูล)_"


def main():
    req, items = load("requests.jsonl", "types"), load("items.jsonl", "types")
    out = ["# Discovery summary", ""]
    if req.empty:
        out.append("No runs yet.")
    else:
        req["scope"] = req.apply(lambda r: "deptId" if isinstance(r.get("deptId"), str)
                                 else "deptsubId" if isinstance(r.get("deptsubId"), str) else "national", axis=1)
        out += [f"Runs: {req['run'].nunique()} ({', '.join(sorted(req['run'].unique()))})", "",
                f"Requests: {len(req)} | failed: {(~req['ok']).sum()} | items: {len(items)}", ""]

        if not items.empty:
            items["key"] = items["link"].fillna("") + "|" + items["title"].fillna("")
        out += ["## By announce type", ""]
        rows = []
        for t, label in ANNOUNCE_TYPES.items():
            r = req[req["anounceType"] == t]
            it = items[items["anounceType"] == t] if not items.empty else items
            rows.append({
                "type": t, "ความหมาย": label, "requests": len(r), "failed": int((~r["ok"]).sum()),
                "feeds with items": int((r["n_items"] > 0).sum()), "capped (=20)": int(r["capped"].sum()),
                "unique items": it["key"].nunique() if len(it) else 0,
            })
        out += [md(pd.DataFrame(rows)), ""]

        out += ["## By request scope", "",
                md(req.groupby("scope").agg(requests=("ok", "size"), failed=("ok", lambda s: int((~s).sum())),
                                            with_items=("n_items", lambda s: int((s > 0).sum())),
                                            items=("n_items", "sum")).reset_index()), ""]

        errors = req[~req["ok"]]["error"].fillna("").str.slice(0, 80).value_counts().head(10)
        out += ["## Top errors", "", md(errors.rename_axis("error").reset_index(name="count")), ""]

        if not items.empty:
            out += ["## Item fields seen", "",
                    ", ".join(c for c in items.columns if c not in req.columns and c not in ("key", "fetched_at")), ""]
            for t in ANNOUNCE_TYPES:
                it = items[items["anounceType"] == t].drop_duplicates("key")
                if it.empty:
                    continue
                out += [f"## Samples: {t} ({ANNOUNCE_TYPES[t]})", ""]
                cols = [c for c in ("dept_name", "pubDate", "title", "description", "link") if c in it.columns]
                sample = it.sample(min(15, len(it)), random_state=1)[cols].copy()
                for c in ("title", "description"):
                    if c in sample:
                        sample[c] = sample[c].fillna("").str.slice(0, 160)
                out += [md(sample), ""]

            capped = req[req["capped"]].groupby(["anounceType", "dept_name"]).size().reset_index(name="times capped")
            out += ["## Feeds that hit the 20-item cap", "", md(capped.sort_values("times capped", ascending=False).head(40)), ""]

    sweep = load("requests.jsonl", "sweep")
    if not sweep.empty:
        valid = sweep[sweep["ok"] & sweep["channel"].apply(lambda c: bool(c) and bool(c.get("title")))]
        out += ["## deptId sweep", "", f"Codes swept: {len(sweep)} | responded with a channel: {len(valid)} | "
                f"with items today: {(sweep['n_items'] > 0).sum()}", ""]

    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", "discovery_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("\n".join(out[:12]))


if __name__ == "__main__":
    main()
