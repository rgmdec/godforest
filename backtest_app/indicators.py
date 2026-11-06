from __future__ import annotations
import numpy as np
import pandas as pd

def true_range(df):
    prev=df["close"].shift(1)
    return pd.concat([df["high"]-df["low"],(df["high"]-prev).abs(),(df["low"]-prev).abs()],axis=1).max(axis=1)

def wilder_rma(series,length):
    return series.ewm(alpha=1/length,adjust=False,min_periods=length).mean()

def supertrend(df,length=10,factor=2.0):
    atr=wilder_rma(true_range(df),length)
    mid=(df["high"]+df["low"])/2
    upper=mid+factor*atr
    lower=mid-factor*atr
    fu=upper.copy(); fl=lower.copy()
    direction=pd.Series(1,index=df.index,dtype="int64")
    line=pd.Series(np.nan,index=df.index,dtype="float64")
    for i in range(1,len(df)):
        if pd.isna(atr.iloc[i]): continue
        pc=df["close"].iloc[i-1]
        fu.iloc[i]=upper.iloc[i] if upper.iloc[i]<fu.iloc[i-1] or pc>fu.iloc[i-1] else fu.iloc[i-1]
        fl.iloc[i]=lower.iloc[i] if lower.iloc[i]>fl.iloc[i-1] or pc<fl.iloc[i-1] else fl.iloc[i-1]
        if pd.isna(line.iloc[i-1]):
            direction.iloc[i]=1 if df["close"].iloc[i]>=mid.iloc[i] else -1
        elif direction.iloc[i-1]==-1:
            direction.iloc[i]=1 if df["close"].iloc[i]>fu.iloc[i] else -1
        else:
            direction.iloc[i]=-1 if df["close"].iloc[i]<fl.iloc[i] else 1
        line.iloc[i]=fl.iloc[i] if direction.iloc[i]==1 else fu.iloc[i]
    return line,direction

def add_ce_indicators(raw,config=None):
    required={"timestamp","open","high","low","close"}
    missing=required-set(raw.columns)
    if missing: raise ValueError("Missing columns: "+", ".join(sorted(missing)))
    df=raw.copy()
    df["timestamp"]=pd.to_datetime(df["timestamp"],errors="coerce")
    for col in ["open","high","low","close"]: df[col]=pd.to_numeric(df[col],errors="coerce")
    df=df.dropna(subset=["timestamp","open","high","low","close"]).sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    if df.empty: raise ValueError("No valid OHLC candles.")
    if (df.high<df.low).any(): raise ValueError("Found candles where high is below low.")
    cfg=config or {}; e=cfg.get("entry",{}); x=cfg.get("exit",{})
    df["entry_supertrend"],df["entry_st_direction"]=supertrend(df,int(e.get("supertrend_length",10)),float(e.get("supertrend_factor",2)))
    df["exit_supertrend"],df["exit_st_direction"]=supertrend(df,int(x.get("supertrend_length",10)),float(x.get("supertrend_factor",2)))
    rsi_len=int(e.get("rsi_length",14)); delta=df.close.diff()
    ag=wilder_rma(delta.clip(lower=0),rsi_len); al=wilder_rma(-delta.clip(upper=0),rsi_len)
    rs=ag/al.replace(0,np.nan)
    df["rsi_14"]=100-100/(1+rs)
    df.loc[(al==0)&(ag>0),"rsi_14"]=100
    adx_len=int(e.get("adx_length",12)); up=df.high.diff(); down=-df.low.diff()
    pdm=pd.Series(np.where((up>down)&(up>0),up,0.0),index=df.index)
    mdm=pd.Series(np.where((down>up)&(down>0),down,0.0),index=df.index)
    atr=wilder_rma(true_range(df),adx_len)
    pdi=100*wilder_rma(pdm,adx_len)/atr.replace(0,np.nan)
    mdi=100*wilder_rma(mdm,adx_len)/atr.replace(0,np.nan)
    dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    df["adx_12"]=wilder_rma(dx,adx_len)
    bb_len=int(e.get("bb_length",20)); bb_factor=float(e.get("bb_factor",2))
    mid=df.close.rolling(bb_len,min_periods=bb_len).mean()
    sd=df.close.rolling(bb_len,min_periods=bb_len).std(ddof=0)
    df["bb_upper"]=mid+bb_factor*sd; df["bb_middle"]=mid; df["bb_lower"]=mid-bb_factor*sd
    wr_len=int(e.get("williams_length",14))
    hi=df.high.rolling(wr_len,min_periods=wr_len).max()
    lo=df.low.rolling(wr_len,min_periods=wr_len).min()
    df["williams_r_14"]=-100*(hi-df.close)/(hi-lo).replace(0,np.nan)
    return df
