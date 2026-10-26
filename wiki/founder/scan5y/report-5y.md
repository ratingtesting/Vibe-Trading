## 1. Сводка прогона

| Показатель | Значение |
|---|---|
| Прогонов всего | 224 |
| Успешных (OK) | 224 |
| Ошибок | 0 |
| Окно | 2021-10-20 .. 2026-10-19 (5 лет, дневные бары) |
| Наблюдений на прогон | 1826 (5 лет x 365) |
| Семейств стратегий | 17 |
| Вариантов (параметры x риск) | 224 |
| Пар | 28 |
| Исполнение размера | position_adjustment=rebalance (dropped=0) |
| Пул испытаний для DSR | 224 |
| Разброс Sharpe по пулу (попериодный) | 0.021149 |
| Ожидаемые ложные срабатывания при 5% | 11.2 |
| Прошли ЭТАЛОН (t>=3, DSR>=0.95, |DD|<=20%) | 0 |
| Прошли КАНДИДАТ (t>=2.5, DSR>=0.95, |DD|<=20%) | 0 |

## 2. ЭТАЛОНЫ (t>=3 + DSR>=0.95 + |DD|<=20%) — полный список

_Ни один прогон не прошёл все три условия. Путь ниже показывает, чего именно не хватает каждой строке._

## 3. КАНДИДАТЫ (t>=2.5 + DSR>=0.95 + |DD|<=20%) — полный список

_Ни один прогон не прошёл все три условия._

## 4. Все строки с t>=2.5, отсортированные по DSR — полный список

| # | Стратегия | Пара | Параметры | Риск | Годовая % | t | DSR | Просадка % | Sharpe/набл | DSR-прошёл | DD-прошёл |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | RegimeSwitching | TRXUSDT | regime_period=50, trend_lookback=14 | vol10 | 13.15 | 2.601 | 0.5325 | 10.92 | 0.06087 | нет | да |

## 5. BTC-копилка: полный расклад счёта

| # | Стратегия | Пара | Риск | База %/год | С копилкой %/год | Δ годовой | База DD % | DD с копилкой % | Δ DD | BTC накоплено, шт | BTC в $ | Актив в $ | Кэш в $ | ВСЕГО в $ | Доля BTC % | Фиксаций | Возвратов |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | TSMOM | AAVEUSDT | vol10 | 2.45 | 2.46 | 0.00 | -12.98 | -12.98 | 0.00 | 0.000000 | 0.00 | 112.90 | 0.00 | 112.90 | 0.0 | 0 | 0 |
| 2 | TSMOM | FETUSDT | raw | -5.46 | -100.00 | -94.54 | -89.48 | -100.00 | -10.52 | 0.000000 | 0.00 | 0.00 | 0.00 | 0.00 | 0.0 | 0 | 1 |
| 3 | TSMOM | CKBUSDT | raw | -7.76 | -19.42 | -11.66 | -77.51 | -94.95 | -17.43 | 0.000381 | 31.45 | 2.52 | 0.00 | 33.97 | 92.6 | 1 | 1 |
| 4 | TSMOM | GALAUSDT | raw | -12.04 | 31.18 | 43.23 | -94.18 | -75.28 | 18.90 | 0.004549 | 375.71 | 12.81 | -0.00 | 388.52 | 96.7 | 4 | 0 |
| 5 | TSMOM | DUSKUSDT | raw | -17.49 | 14.64 | 32.13 | -97.52 | -78.83 | 18.70 | 0.002265 | 187.04 | 10.95 | 0.00 | 197.99 | 94.5 | 5 | 1 |
| 6 | TSMOM | AAVEUSDT | raw | -6.06 | -10.44 | -4.38 | -83.03 | -89.65 | -6.62 | 0.000649 | 53.62 | 4.01 | 0.00 | 57.64 | 93.0 | 1 | 1 |
| 7 | TSMOM | AAVEUSDT | vol10 | 1.62 | 1.62 | 0.00 | -13.23 | -13.23 | 0.00 | 0.000000 | 0.00 | 108.36 | 0.00 | 108.36 | 0.0 | 0 | 0 |
| 8 | TSMOM | HBARUSDT | raw | -7.72 | -100.00 | -92.28 | -83.33 | -100.00 | -16.67 | 0.000000 | 0.00 | 0.00 | 0.00 | 0.00 | 0.0 | 0 | 1 |

### 5.1 Итоги по копилке

| Показатель | Значение |
|---|---|
| Кандидатов посчитано с копилкой | 8 |
| Копилка улучшила годовую доходность | 4 из 8 |
| Копилка ухудшила просадку (п.п.) | 3 из 8 |
| Всего фиксаций (переводов в BTC) | 11 |
| Всего возвратов резерва в актив | 5 |
| Максимум BTC накоплено, шт | 0.004549 |
| Стартовый капитал копилки, $ | 100 |

## 6. Лучшие по годовой доходности при просадке <= 20% — полный список

| Строки этого списка НЕ прошли статистический бар DSR>=0.95. Это альтернатива «просто доходность», показанная честно.

| # | Стратегия | Пара | Параметры | Риск | Годовая % | t | DSR | Просадка % | Sharpe/набл |
|---|---|---|---|---|---|---|---|---|---|
| 1 | RegimeSwitching | TRXUSDT | regime_period=50, trend_lookback=14 | vol10 | 13.15 | 2.601 | 0.5325 | 10.92 | 0.06087 |
| 2 | ft_ema21_50 | SUPERUSDT |  | vol10 | 11.34 | 2.195 | 0.3663 | 11.97 | 0.05137 |
| 3 | RegimeSwitching | TRXUSDT | regime_period=50, trend_lookback=60 | vol10 | 10.67 | 2.090 | 0.3045 | 11.68 | 0.04892 |
| 4 | RegimeSwitching | TRXUSDT | regime_period=50, trend_lookback=30 | vol10 | 10.31 | 2.012 | 0.2748 | 13.21 | 0.04708 |
| 5 | RegimeSwitching | TRXUSDT | regime_period=50, trend_lookback=14 | vol12dd820 | 7.90 | 1.915 | 0.1556 | 8.05 | 0.04482 |
| 6 | RegimeSwitching | TRXUSDT | regime_period=50, trend_lookback=60 | vol12dd820 | 6.93 | 1.628 | 0.0892 | 12.14 | 0.03809 |
| 7 | TSMOM | ZECUSDT | lookback=252 | vol10 | 6.79 | 2.027 | 0.2938 | 8.46 | 0.04744 |
| 8 | RegimeSwitching | TRXUSDT | regime_period=50, trend_lookback=30 | vol12dd820 | 6.71 | 1.579 | 0.0805 | 13.20 | 0.03695 |
| 9 | MARegimeFilter | ZECUSDT | ma_period=20 | vol10 | 4.15 | 1.215 | 0.0868 | 14.92 | 0.02844 |
| 10 | VolatilityBreakout | XLMUSDT | atr_period=21, quantile=0.8 | vol10 | 3.63 | 1.378 | 0.0592 | 5.05 | 0.03225 |
| 11 | VolatilityBreakout | XRPUSDT | atr_period=21, quantile=0.7 | vol10 | 3.46 | 1.370 | 0.0987 | 4.99 | 0.03207 |
| 12 | RegimeSwitching | TWTUSDT | regime_period=20, trend_lookback=90 | vol10 | 3.24 | 0.950 | 0.0552 | 8.79 | 0.02224 |
| 13 | RegimeSwitching | THETAUSDT | regime_period=200, trend_lookback=30 | vol10 | 2.76 | 0.929 | 0.0528 | 11.85 | 0.02175 |
| 14 | RegimeSwitching | THETAUSDT | regime_period=200, trend_lookback=90 | vol10 | 2.72 | 0.891 | 0.0490 | 13.82 | 0.02085 |
| 15 | ft_ema9_21 | SUSHIUSDT |  | vol10 | 2.72 | 0.653 | 0.0287 | 17.42 | 0.01528 |
| 16 | MARegimeFilter | YGGUSDT | ma_period=30 | vol10 | 2.65 | 0.877 | 0.0453 | 16.40 | 0.02052 |
| 17 | TSMOM | ZECUSDT | lookback=252 | vol12dd820 | 2.53 | 1.719 | 0.2009 | 4.16 | 0.04022 |
| 18 | VolatilityBreakout | XTZUSDT | atr_period=14, quantile=0.7 | vol10 | 2.07 | 0.830 | 0.0385 | 12.84 | 0.01943 |
| 19 | RegimeSwitching | TWTUSDT | regime_period=50, trend_lookback=10 | vol10 | 2.02 | 0.602 | 0.0267 | 13.95 | 0.01409 |
| 20 | VolatilityBreakout | XRPUSDT | atr_period=21, quantile=0.6 | vol10 | 1.97 | 0.726 | 0.0314 | 7.69 | 0.01700 |
| 21 | TSMOM | ZECUSDT | lookback=180 | vol12dd820 | 1.95 | 1.356 | 0.1140 | 6.10 | 0.03173 |
| 22 | VolatilityBreakout | XTZUSDT | atr_period=14, quantile=0.8 | vol10 | 1.90 | 0.840 | 0.0374 | 9.98 | 0.01965 |
| 23 | MARegimeFilter | ZECUSDT | ma_period=20 | vol12dd820 | 1.86 | 1.202 | 0.0876 | 5.72 | 0.02814 |
| 24 | ZScoreMeanReversion | VTHOUSDT | entry_z=-1.5, period=20 | vol10 | 1.56 | 0.437 | 0.0102 | 16.97 | 0.01022 |
| 25 | VolatilityBreakout | XRPUSDT | atr_period=14, quantile=0.9 | vol12dd820 | 1.42 | 1.499 | 0.1361 | 3.53 | 0.03509 |
| 26 | VolatilityBreakout | XRPUSDT | atr_period=21, quantile=0.7 | vol12dd820 | 1.36 | 1.229 | 0.0801 | 5.51 | 0.02875 |
| 27 | ZScoreMeanReversion | XLMUSDT | entry_z=-1.0, period=5 | vol10 | 1.33 | 0.466 | 0.0162 | 10.33 | 0.01091 |
| 28 | MARegimeFilter | YGGUSDT | ma_period=50 | vol10 | 1.26 | 0.473 | 0.0186 | 18.64 | 0.01106 |
| 29 | ZScoreMeanReversion | VTHOUSDT | entry_z=-2.5, period=20 | vol10 | 1.25 | 0.598 | 0.0246 | 10.05 | 0.01399 |
| 30 | RegimeSwitching | TWTUSDT | regime_period=20, trend_lookback=90 | vol12dd820 | 1.19 | 0.796 | 0.0339 | 4.92 | 0.01862 |
| 31 | TSMOM | ZENUSDT | lookback=180 | vol10 | 1.15 | 0.435 | 0.0138 | 8.80 | 0.01017 |
| 32 | VolatilityBreakout | XLMUSDT | atr_period=21, quantile=0.9 | vol10 | 1.11 | 0.933 | 0.0459 | 3.80 | 0.02183 |
| 33 | RegimeSwitching | THETAUSDT | regime_period=200, trend_lookback=60 | vol10 | 1.06 | 0.420 | 0.0173 | 13.63 | 0.00983 |
| 34 | VolatilityBreakout | XLMUSDT | atr_period=21, quantile=0.8 | vol12dd820 | 0.92 | 1.073 | 0.0387 | 2.81 | 0.02511 |
| 35 | RegimeSwitching | THETAUSDT | regime_period=200, trend_lookback=30 | vol12dd820 | 0.89 | 0.940 | 0.0539 | 3.64 | 0.02201 |
| 36 | RegimeSwitching | TWTUSDT | regime_period=20, trend_lookback=60 | vol12dd820 | 0.85 | 0.587 | 0.0217 | 5.37 | 0.01373 |
| 37 | RegimeSwitching | TRBUSDT | regime_period=50, trend_lookback=90 | vol12dd820 | 0.78 | 0.587 | 0.0252 | 7.04 | 0.01374 |
| 38 | MARegimeFilter | YGGUSDT | ma_period=30 | vol12dd820 | 0.72 | 0.692 | 0.0298 | 5.17 | 0.01620 |
| 39 | ZScoreMeanReversion | VTHOUSDT | entry_z=-2.0, period=20 | vol10 | 0.71 | 0.320 | 0.0128 | 13.24 | 0.00750 |
| 40 | VolatilityBreakout | XRPUSDT | atr_period=21, quantile=0.6 | vol12dd820 | 0.69 | 0.576 | 0.0235 | 7.05 | 0.01348 |
| 41 | MARegimeFilter | XVSUSDT | ma_period=200 | vol12dd820 | 0.67 | 0.644 | 0.0194 | 3.31 | 0.01507 |
| 42 | VolatilityBreakout | XTZUSDT | atr_period=14, quantile=0.7 | vol12dd820 | 0.65 | 0.830 | 0.0385 | 4.02 | 0.01942 |
| 43 | RegimeSwitching | TRBUSDT | regime_period=100, trend_lookback=10 | vol12dd820 | 0.65 | 0.501 | 0.0206 | 6.60 | 0.01172 |
| 44 | VolatilityBreakout | XTZUSDT | atr_period=14, quantile=0.8 | vol12dd820 | 0.60 | 0.839 | 0.0374 | 3.09 | 0.01964 |
| 45 | ZScoreMeanReversion | VTHOUSDT | entry_z=-1.5, period=20 | vol12dd820 | 0.57 | 0.436 | 0.0102 | 5.36 | 0.01020 |
| 46 | MARegimeFilter | YGGUSDT | ma_period=75 | vol10 | 0.48 | 0.234 | 0.0104 | 16.83 | 0.00548 |
| 47 | ZScoreMeanReversion | XLMUSDT | entry_z=-1.0, period=5 | vol12dd820 | 0.43 | 0.443 | 0.0154 | 3.15 | 0.01036 |
| 48 | MARegimeFilter | YGGUSDT | ma_period=50 | vol12dd820 | 0.43 | 0.472 | 0.0185 | 5.93 | 0.01104 |
| 49 | ZScoreMeanReversion | VETUSDT | entry_z=-2.5, period=20 | vol12dd820 | 0.40 | 0.806 | 0.0405 | 1.89 | 0.01885 |
| 50 | RegimeSwitching | THETAUSDT | regime_period=200, trend_lookback=60 | vol12dd820 | 0.38 | 0.432 | 0.0178 | 4.23 | 0.01010 |
| 51 | TSMOM | ZILUSDT | lookback=30 | vol12dd820 | 0.30 | 0.270 | 0.0096 | 5.77 | 0.00632 |
| 52 | ZScoreMeanReversion | VTHOUSDT | entry_z=-2.0, period=20 | vol12dd820 | 0.25 | 0.319 | 0.0127 | 4.12 | 0.00747 |
| 53 | VolatilityBreakout | XLMUSDT | atr_period=21, quantile=0.9 | vol12dd820 | 0.22 | 0.497 | 0.0179 | 2.16 | 0.01163 |
| 54 | MARegimeFilter | YGGUSDT | ma_period=75 | vol12dd820 | 0.19 | 0.233 | 0.0104 | 5.31 | 0.00546 |
| 55 | RegimeSwitching | TRBUSDT | regime_period=100, trend_lookback=14 | vol10 | 0.03 | 0.093 | 0.0074 | 16.94 | 0.00218 |
| 56 | VolatilityBreakout | XVSUSDT | atr_period=7, quantile=0.6 | vol12dd820 | -0.01 | 0.012 | 0.0059 | 3.28 | 0.00029 |
| 57 | TSMOM | ZILUSDT | lookback=30 | vol10 | -0.03 | 0.087 | 0.0067 | 18.09 | 0.00203 |
| 58 | RegimeSwitching | TWTUSDT | regime_period=50, trend_lookback=10 | vol12dd820 | -0.07 | -0.015 | 0.0054 | 4.87 | -0.00034 |
| 59 | ZScoreMeanReversion | UNIUSDT | entry_z=-2.5, period=40 | vol12dd820 | -0.07 | -0.076 | 0.0045 | 3.70 | -0.00179 |
| 60 | MARegimeFilter | YFIUSDT | ma_period=100 | vol12dd820 | -0.08 | -0.079 | 0.0046 | 4.61 | -0.00186 |
| 61 | ZScoreMeanReversion | WINUSDT | entry_z=-1.5, period=10 | vol12dd820 | -0.09 | -0.064 | 0.0051 | 4.41 | -0.00149 |
| 62 | VolatilityBreakout | XVGUSDT | atr_period=14, quantile=0.6 | vol12dd820 | -0.11 | -0.113 | 0.0042 | 3.00 | -0.00265 |
| 63 | RegimeSwitching | TRBUSDT | regime_period=50, trend_lookback=90 | vol10 | -0.14 | 0.049 | 0.0065 | 17.69 | 0.00114 |
| 64 | RegimeSwitching | TRBUSDT | regime_period=100, trend_lookback=10 | vol10 | -0.15 | 0.042 | 0.0064 | 16.35 | 0.00098 |
| 65 | VolatilityBreakout | XVSUSDT | atr_period=7, quantile=0.6 | vol10 | -0.15 | 0.014 | 0.0059 | 10.70 | 0.00032 |
| 66 | TSMOM | ZENUSDT | lookback=126 | vol12dd820 | -0.20 | -0.187 | 0.0039 | 4.12 | -0.00437 |
| 67 | RegimeSwitching | TLMUSDT | regime_period=100, trend_lookback=30 | vol12dd820 | -0.24 | -0.188 | 0.0035 | 5.57 | -0.00439 |
| 68 | VolatilityBreakout | XVGUSDT | atr_period=7, quantile=0.8 | vol12dd820 | -0.25 | -0.386 | 0.0022 | 2.44 | -0.00903 |
| 69 | VolatilityBreakout | XVSUSDT | atr_period=7, quantile=0.7 | vol12dd820 | -0.31 | -0.423 | 0.0016 | 3.31 | -0.00991 |
| 70 | ZScoreMeanReversion | VETUSDT | entry_z=-1.5, period=40 | vol12dd820 | -0.31 | -0.327 | 0.0021 | 3.99 | -0.00765 |
| 71 | ZScoreMeanReversion | UNIUSDT | entry_z=-2.5, period=40 | vol10 | -0.33 | -0.076 | 0.0045 | 12.11 | -0.00177 |
| 72 | ZScoreMeanReversion | XECUSDT | entry_z=-1.5, period=5 | vol12dd820 | -0.36 | -0.407 | 0.0016 | 3.02 | -0.00953 |
| 73 | TSMOM | ZRXUSDT | lookback=14 | vol12dd820 | -0.37 | -0.283 | 0.0026 | 6.77 | -0.00661 |
| 74 | RegimeSwitching | TLMUSDT | regime_period=100, trend_lookback=14 | vol12dd820 | -0.38 | -0.321 | 0.0024 | 5.33 | -0.00751 |
| 75 | VolatilityBreakout | XVGUSDT | atr_period=7, quantile=0.9 | vol12dd820 | -0.40 | -0.870 | 0.0004 | 2.19 | -0.02035 |
| 76 | MARegimeFilter | YFIUSDT | ma_period=100 | vol10 | -0.41 | -0.078 | 0.0046 | 14.67 | -0.00183 |
| 77 | MARegimeFilter | YFIUSDT | ma_period=150 | vol12dd820 | -0.41 | -0.518 | 0.0012 | 4.98 | -0.01213 |
| 78 | TSMOM | ZRXUSDT | lookback=14 | vol10 | -0.42 | -0.013 | 0.0055 | 19.28 | -0.00030 |
| 79 | VolatilityBreakout | XVGUSDT | atr_period=14, quantile=0.6 | vol10 | -0.48 | -0.113 | 0.0043 | 9.91 | -0.00263 |
| 80 | RegimeSwitching | TFUELUSDT | regime_period=200, trend_lookback=90 | vol12dd820 | -0.48 | -0.409 | 0.0019 | 5.33 | -0.00958 |
| 81 | TSMOM | ZILUSDT | lookback=63 | vol12dd820 | -0.48 | -0.471 | 0.0017 | 5.84 | -0.01103 |
| 82 | ZScoreMeanReversion | WINUSDT | entry_z=-1.5, period=10 | vol10 | -0.50 | -0.063 | 0.0051 | 14.33 | -0.00147 |
| 83 | ZScoreMeanReversion | UNIUSDT | entry_z=-2.0, period=40 | vol12dd820 | -0.56 | -0.634 | 0.0007 | 6.22 | -0.01483 |
| 84 | TSMOM | ZILUSDT | lookback=45 | vol12dd820 | -0.58 | -0.561 | 0.0013 | 5.82 | -0.01314 |
| 85 | ZScoreMeanReversion | WAXPUSDT | entry_z=-2.5, period=10 | vol12dd820 | -0.58 | -1.160 | 0.0000 | 4.14 | -0.02718 |
| 86 | RegimeSwitching | TKOUSDT | regime_period=100, trend_lookback=90 | vol12dd820 | -0.61 | -0.489 | 0.0012 | 7.10 | -0.01145 |
| 87 | RegimeSwitching | UNIUSDT | regime_period=20, trend_lookback=10 | vol12dd820 | -0.62 | -0.428 | 0.0019 | 6.97 | -0.01001 |
| 88 | VolatilityBreakout | XTZUSDT | atr_period=14, quantile=0.9 | vol10 | -0.65 | -0.431 | 0.0016 | 5.77 | -0.01007 |
| 89 | ZScoreMeanReversion | WAXPUSDT | entry_z=-2.0, period=10 | vol12dd820 | -0.67 | -0.913 | 0.0002 | 6.01 | -0.02138 |
| 90 | TSMOM | 1INCHUSDT | lookback=7 | vol12dd820 | -0.68 | -0.669 | 0.0007 | 5.34 | -0.01566 |
| 91 | TSMOM | ZRXUSDT | lookback=21 | vol12dd820 | -0.75 | -0.616 | 0.0010 | 8.02 | -0.01440 |
| 92 | RegimeSwitching | TKOUSDT | regime_period=200, trend_lookback=10 | vol12dd820 | -0.76 | -0.692 | 0.0005 | 6.89 | -0.01620 |
| 93 | ZScoreMeanReversion | VETUSDT | entry_z=-1.0, period=40 | vol12dd820 | -0.78 | -0.763 | 0.0004 | 5.13 | -0.01786 |
| 94 | RegimeSwitching | TKOUSDT | regime_period=200, trend_lookback=14 | vol12dd820 | -0.81 | -0.716 | 0.0005 | 6.92 | -0.01676 |
| 95 | RegimeSwitching | UMAUSDT | regime_period=20, trend_lookback=30 | vol12dd820 | -0.83 | -0.673 | 0.0009 | 5.97 | -0.01576 |
| 96 | TSMOM | ZENUSDT | lookback=126 | vol10 | -0.84 | -0.186 | 0.0039 | 13.41 | -0.00436 |
| 97 | TSMOM | ZRXUSDT | lookback=10 | vol12dd820 | -0.85 | -0.687 | 0.0008 | 5.79 | -0.01607 |
| 98 | ZScoreMeanReversion | WINUSDT | entry_z=-1.0, period=10 | vol12dd820 | -0.90 | -0.782 | 0.0013 | 9.19 | -0.01829 |
| 99 | TSMOM | 1INCHUSDT | lookback=5 | vol12dd820 | -0.90 | -0.904 | 0.0003 | 7.27 | -0.02114 |
| 100 | VolatilityBreakout | XVGUSDT | atr_period=7, quantile=0.8 | vol10 | -0.91 | -0.385 | 0.0022 | 7.97 | -0.00902 |
| 101 | TSMOM | ZENUSDT | lookback=90 | vol12dd820 | -0.93 | -1.113 | 0.0002 | 5.57 | -0.02605 |
| 102 | RegimeSwitching | TLMUSDT | regime_period=100, trend_lookback=60 | vol12dd820 | -1.00 | -0.843 | 0.0005 | 6.94 | -0.01974 |
| 103 | RegimeSwitching | TLMUSDT | regime_period=100, trend_lookback=30 | vol10 | -1.05 | -0.187 | 0.0035 | 17.69 | -0.00437 |
| 104 | TSMOM | 1INCHUSDT | lookback=10 | vol10 | -1.09 | -0.236 | 0.0028 | 15.74 | -0.00552 |
| 105 | VolatilityBreakout | XVSUSDT | atr_period=7, quantile=0.7 | vol10 | -1.12 | -0.423 | 0.0016 | 10.74 | -0.00989 |
| 106 | RegimeSwitching | UMAUSDT | regime_period=20, trend_lookback=60 | vol10 | -1.13 | -0.199 | 0.0033 | 15.68 | -0.00467 |
| 107 | ZScoreMeanReversion | VETUSDT | entry_z=-1.5, period=40 | vol10 | -1.18 | -0.326 | 0.0021 | 12.85 | -0.00763 |
| 108 | ZScoreMeanReversion | XECUSDT | entry_z=-1.5, period=5 | vol10 | -1.35 | -0.411 | 0.0015 | 10.10 | -0.00961 |
| 109 | VolatilityBreakout | XVGUSDT | atr_period=7, quantile=0.9 | vol10 | -1.36 | -0.869 | 0.0004 | 7.31 | -0.02034 |
| 110 | RegimeSwitching | UMAUSDT | regime_period=20, trend_lookback=14 | vol12dd820 | -1.46 | -1.026 | 0.0003 | 7.84 | -0.02402 |
| 111 | MARegimeFilter | YFIUSDT | ma_period=150 | vol10 | -1.49 | -0.518 | 0.0012 | 15.78 | -0.01212 |
| 112 | MARegimeFilter | YFIUSDT | ma_period=200 | vol10 | -1.56 | -0.579 | 0.0009 | 15.14 | -0.01355 |
| 113 | ft_bb_revert | SUSHIUSDT |  | vol10 | -1.79 | -0.735 | 0.0004 | 17.03 | -0.01719 |
| 114 | ZScoreMeanReversion | WAXPUSDT | entry_z=-2.5, period=10 | vol10 | -1.98 | -1.160 | 0.0000 | 13.29 | -0.02717 |
| 115 | ZScoreMeanReversion | UNIUSDT | entry_z=-2.0, period=40 | vol10 | -1.99 | -0.632 | 0.0007 | 19.60 | -0.01480 |
| 116 | ZScoreMeanReversion | WAXPUSDT | entry_z=-2.0, period=10 | vol10 | -2.31 | -0.912 | 0.0002 | 18.96 | -0.02137 |
| 117 | TSMOM | ZILUSDT | lookback=63 | vol10 | -2.44 | -0.777 | 0.0005 | 18.32 | -0.01818 |
| 118 | TSMOM | 1INCHUSDT | lookback=7 | vol10 | -2.44 | -0.668 | 0.0007 | 17.14 | -0.01563 |
| 119 | ZScoreMeanReversion | WAXPUSDT | entry_z=-1.0, period=20 | vol12dd820 | -2.71 | -2.679 | 0.0000 | 14.70 | -0.06277 |
| 120 | ZScoreMeanReversion | VETUSDT | entry_z=-1.0, period=40 | vol10 | -2.75 | -0.762 | 0.0005 | 16.32 | -0.01784 |
| 121 | TSMOM | ZILUSDT | lookback=45 | vol10 | -2.77 | -0.867 | 0.0004 | 18.42 | -0.02030 |
| 122 | RegimeSwitching | UMAUSDT | regime_period=20, trend_lookback=30 | vol10 | -2.97 | -0.667 | 0.0009 | 19.47 | -0.01562 |
| 123 | TSMOM | ZENUSDT | lookback=90 | vol10 | -3.20 | -1.113 | 0.0002 | 17.65 | -0.02604 |

## 7. Оговорки к числам

| # | Оговорка |
|---|---|
| 1 | Период один и тот же для всех строк: 5 лет дневных баров (1826 наблюдений). |
| 2 | Доходность в годовых = (prod(1+r))^(365/n)-1 из дневной доходности, а не деление на глаз. |
| 3 | DSR считается по ВСЕМ строкам пула в попериодной шкале (mean/std) — как требует multipletesting.py. |
| 4 | skew/kurtosis — по реальному ряду доходности, kurtosis неэксцессовая (3 = гауссова). |
| 5 | Отбор сделан на том же 5-летнем окне, что и скан: это НЕ независимая проверка. |
| 6 | Все строки пула уже просмотрены: повторный перебор на них не даёт нового чистого теста. |
| 7 | Комиссия движка (maker/taker/проскальзывание) учтена в доходности стратегии; в копилке — только комиссия переводов. |
| 8 | Большой перебор сам по себе почти не оставляет шансов пройти DSR>=0.95: ожидается ~11 ложных срабатываний. |

| # | Оговорка копилки |
|---|---|
| 1 | Наложение применяется к реализованной дневной доходности стратегии, а не к повторному прогону движка со смешанным BTC-рукавом. |
| 2 | Отбор кандидатов сделан на том же 5-летнем окне, которое идёт в скан: поздний срез не является неприкосновенной проверкой. |
| 3 | Комиссия движка уже учтена в доходности стратегии; в копилке считается только комиссия переводов (10 bps на ногу). |
| 4 | Цены актива и BTC — из локальных биржевых CSV, тот же источник, что и доходность. |
