from __future__ import annotations
import pandas as pd

def entry_mask(df,cfg):
    tests=[]
    if cfg.get("use_supertrend",True): tests.append((df.close>df.entry_supertrend)&(df.entry_st_direction==1))
    if cfg.get("use_rsi",True): tests.append(df.rsi_14>float(cfg.get("rsi_level",70)))
    if cfg.get("use_adx",True): tests.append(df.adx_12<float(cfg.get("adx_max",35)))
    if cfg.get("use_bollinger",True): tests.append(df.close>df.bb_upper)
    if cfg.get("use_williams",True): tests.append(df.williams_r_14>float(cfg.get("williams_level",-8)))
    if not tests: return pd.Series(False,index=df.index)
    mask=tests[0].fillna(False)
    for test in tests[1:]: mask &= test.fillna(False)
    return mask

def run_ce_backtest(data,config):
    df=data.copy().reset_index(drop=True)
    df["entry_signal"]=entry_mask(df,config["entry"])
    df["premium_ok"]=df.close.between(float(config["premium_low"]),float(config["premium_high"]))
    df["entry_signal"] &= df["premium_ok"]
    ts=pd.to_datetime(df.timestamp)
    trades=[]; position=None
    force_time=config.get("force_exit_time","15:15")
    for i,row in df.iterrows():
        clock=ts.iloc[i].strftime("%H:%M")
        if position is not None:
            reason=None
            if pd.notna(row.exit_supertrend) and row.close<row.exit_supertrend:
                reason="Option candle close below Supertrend (10,2)"
            elif config.get("force_exit_enabled",True) and clock>=force_time:
                reason=f"Forced exit at {force_time}"
            if reason:
                px=float(row.close); qty=int(config["units"])
                gross=(px-position["entry_price"])*qty
                cost=float(config.get("estimated_cost_per_trade",0))
                trades.append({"entry_time":position["entry_time"],"exit_time":ts.iloc[i],
                    "entry_price":position["entry_price"],"exit_price":px,"units":qty,
                    "gross_pnl_rupees":gross,"estimated_costs_rupees":cost,
                    "net_pnl_rupees":gross-cost,"exit_reason":reason})
                position=None
                continue
        if position is None and i+1<len(df) and bool(row.entry_signal):
            nxt=df.iloc[i+1]; entry_time=ts.iloc[i+1]
            if entry_time.strftime("%H:%M")>=force_time: continue
            px=float(nxt.open)
            if float(config["premium_low"])<=px<=float(config["premium_high"]):
                position={"entry_time":entry_time,"entry_price":px}
    if position is not None and len(df):
        px=float(df.iloc[-1].close); qty=int(config["units"])
        gross=(px-position["entry_price"])*qty
        cost=float(config.get("estimated_cost_per_trade",0))
        trades.append({"entry_time":position["entry_time"],"exit_time":ts.iloc[-1],
            "entry_price":position["entry_price"],"exit_price":px,"units":qty,
            "gross_pnl_rupees":gross,"estimated_costs_rupees":cost,
            "net_pnl_rupees":gross-cost,"exit_reason":"End of available data (forced close)"})
    t=pd.DataFrame(trades)
    if t.empty:
        summary={"trades":0,"wins":0,"losses":0,"win_rate_pct":0.0,"net_pnl_rupees":0.0,"avg_pnl_rupees":0.0,"max_drawdown_rupees":0.0}
    else:
        pnl=t.net_pnl_rupees; equity=pnl.cumsum(); dd=equity-equity.cummax().clip(lower=0)
        summary={"trades":len(t),"wins":int((pnl>0).sum()),"losses":int((pnl<=0).sum()),
          "win_rate_pct":float((pnl>0).mean()*100),"net_pnl_rupees":float(pnl.sum()),
          "avg_pnl_rupees":float(pnl.mean()),"max_drawdown_rupees":float(dd.min())}
    return {"summary":summary,"trades":t,"data":df}
