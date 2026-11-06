DEFAULT_CE_CONFIG={
 "name":"CE_STGY BUILDER – Positional","side":"CE","underlying":"NIFTY 50",
 "indicator_source":"selected_option_premium","premium_target":250.0,"premium_low":220.0,"premium_high":280.0,
 "entry":{"supertrend_length":10,"supertrend_factor":2.0,"rsi_length":14,"rsi_level":70.0,
 "adx_length":12,"adx_max":35.0,"bb_length":20,"bb_factor":2.0,"williams_length":14,
 "williams_level":-8.0,"logic":"AND","use_supertrend":True,"use_rsi":True,"use_adx":True,
 "use_bollinger":True,"use_williams":True},
 "exit":{"type":"supertrend_close_below","supertrend_length":10,"supertrend_factor":2.0},
 "paper_trading_only":True}
