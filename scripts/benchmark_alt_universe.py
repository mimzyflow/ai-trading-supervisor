from pathlib import Path
import pandas as pd

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
        details.sort(key=lambda x:x[1], reverse=True)
        print(" top",[(a,round(b*100,1)) for a,b in details[:3]])
        print(" worst",[(a,round(b*100,1)) for a,b in details[-3:]])
