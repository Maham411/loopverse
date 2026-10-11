# Recommendation

**Operational recommendation (2-3 sentences):**
Our forecast keeps all 15 covered Lahore areas between 103 and 153 µg/m³ PM2.5 from 29 Oct to 7 Nov 2026, so under the official 165 µg/m³ rule no area-day is forecast hazardous: schools stay on normal timing under the current policy (DOC-03), and sensitive groups should reduce prolonged outdoor exertion (DOC-01). Because hazardous days arrive as sudden spikes that no model here can predict, the dashboard and assistant add an advisory early-warning watch where the forecast is at least 130 µg/m³ (89 area-days, led by Faisal Town, DHA, Shadman and Walled City). In October this watch caught 7 of 13 hazardous days that the 165 rule missed, so authorities should keep half-day plans ready in watched areas and make the evening-before school decision (DOC-03) from that day's sensor readings.

**Limitations (2-3 bullet points):**
- The model forecasts the typical level well (October test MAE 13.9 µg/m³, vs 14.8 for a 7-day average and 18.7 for yesterday's value), but spikes have no warning signal, so no forecast reaches 165. All 150 rows are `hazardous = 0` under the official rule, and real spike days will likely be missed. A "never hazardous" alarm scores 96.9% accuracy with 0 recall, which is why we report recall and false alarms.
- The advisory 130 µg/m³ watch is noisy: in October it also raised 105 false alarms (about 6% of watches were real hazardous days). That is why it is kept out of `predictions.csv`, which follows SPEC section 3 exactly.
- Sensor data ends on 2026-10-28, so 135 of 150 rows rely on chained forecasts with no new readings (recursive 10-day backtest MAE 15.4, slightly low on average). Batch 2 is the AQI of the same readings as batch 1, so it fills gaps but adds no independent information.

**Reference forecast fallback used?** No
_If yes, where and why:_ Not used. Every number comes from our own model (`source: "team_model"`).
