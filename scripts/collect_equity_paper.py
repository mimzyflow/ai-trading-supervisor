#!/usr/bin/env python3
import json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_lab.equity_live import collect
from supervisor.report import atomic_write
root=Path(__file__).resolve().parents[1]; now=datetime.now(timezone.utc); bundle=collect(now)
atomic_write(root/'research_state/equities.bundle.json',json.dumps(bundle,ensure_ascii=False,allow_nan=False))
print(json.dumps({'state':'validated','observed_at':now.isoformat(),'assets':len(bundle['assets']),'last_closed_session':bundle['assets'][0]['bars'][-1]['close_at']}))
