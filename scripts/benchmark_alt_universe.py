from pathlib import Path
import pandas as pd
from benchmark_metrics import passive_net_return

DATA = Path("backtests/alt_recent")
windows = [
    ("DEV", pd.Timestamp("2026-07-12", tz="UTC"), pd.Timestamp("2026-08-25", tz="UTC")),
    ("VALID", pd.Timestamp("2026-08-25", tz="UTC"), pd.Timestamp("2026-10-03", tz="UTC")),
    ("FULL", pd.Timestamp("2026-07-12", tz="UTC"), pd.Timestamp("2026-10-03", tz="UTC")),
]

files=[p for p in DATA.glob("*-4h.feather") if not p.name.startswith("EURC_EUR")]
for label,start,end in windows:
    rets=[]
    details=[]
    for p in files:
        df=pd.read_feather(p)
        df["date"]=pd.to_datetime(df["date"],utc=True)
        sub=df[(df["date"]>=start)&(df["date"]<end)]
        if len(sub)<2:
            continue
        ret=float(sub.iloc[-1]["close"]/sub.iloc[0]["close"]-1)
        rets.append(ret)
        details.append((p.stem.replace("-4h","").replace("_","/"),ret))
    if rets:
        avg=sum(rets)/len(rets)
        med=sorted(rets)[len(rets)//2]
        print(label,"pairs",len(rets),"equal_weight_pct",round(avg*100,2),"median_pct",round(med*100,2))
        net_full = sum(passive_net_return(r, exposure=1) for r in rets) / len(rets)
        net_capped = sum(passive_net_return(r, exposure=0.4) for r in rets) / len(rets)
        print("cash_pct", 0.0, "net_full_exposure_pct", round(net_full*100, 2), "net_40pct_exposure_pct", round(net_capped*100, 2), "fee_per_side", 0.008)
        print("Reference only: current universe snapshot; 40% is the allocation cap, not identical time-varying risk. Slippage and minimum sizes are not modelled.")
        details.sort(key=lambda x:x[1], reverse=True)
        print(" top",[(a,round(b*100,1)) for a,b in details[:3]])
        print(" worst",[(a,round(b*100,1)) for a,b in details[-3:]])
