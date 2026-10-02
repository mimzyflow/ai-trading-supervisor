import ccxt, pandas as pd, talib.abstract as ta
ex=ccxt.kraken({'enableRateLimit': True})
for pair in ('BTC/EUR','ETH/EUR'):
    rows=ex.fetch_ohlcv(pair,'15m',limit=720)
    df=pd.DataFrame(rows, columns=['ts','open','high','low','close','volume'])
    df['ema20']=ta.EMA(df,timeperiod=20)
    df['ema50']=ta.EMA(df,timeperiod=50)
    df['rsi']=ta.RSI(df,timeperiod=14)
    df['vol_mean']=df['volume'].rolling(20).mean()
    crossed=(df['close']>df['ema20']) & (df['close'].shift(1)<=df['ema20'].shift(1))
    signal=(df['ema20']>df['ema50']) & crossed & (df['rsi']>50) & (df['rsi']<68) & (df['volume']>df['vol_mean']) & (df['volume']>0)
    signal.iloc[:200]=False
    print(f"{pair} valid={len(df)-200} signals={int(signal.sum())}")
