# AI Error Log

Record exactly 3 concrete mistakes an AI tool made during this event, and how your team caught and fixed them.

## Entry 1
- **Context + wrong output:** The AI-drafted build brief said batch 1 holds the PM2.5 sensors (UTC) and batch 2 the AQI sensors (PKT), and told us to convert AQI "using the exact formula provided in DOC-06 / SPEC.md". Both assumptions were wrong: each batch file contains all 15 sensors for all 120 days, and neither DOC-06 nor SPEC.md contains any conversion formula.
- **Risk:** Splitting sensors by batch would have thrown away half the readings, including the backup reading for every `-999` gap. Guessing a formula (for example the 2024 EPA AQI table) would have shifted PM2.5 values and corrupted every forecast.
- **Detection:** A data audit printed sensor counts per file (15 and 15). We then tested candidate tables against days where both networks report the same area after the UTC→PKT shift: the classic US EPA breakpoints reproduced batch 2 exactly on 98.3% of sensor-days; the 2024 table matched only 9.8%.
- **Correction + verification:** Batch timezone/unit now come from `sensor_metadata.csv`, AQI is inverted with the classic EPA table, and both networks are averaged per area-day. `test_networks_agree_after_conversion` shows a mean difference of 0.44 µg/m³, and all 56 `-999` gaps are filled from the other network (none interpolated).

## Entry 2
- **Context + wrong output:** Asked to "fix" the all-zero `hazardous` column, the AI lowered the threshold in `predictions.csv` from the official 165 µg/m³ to a calibrated 130 µg/m³, turning 89 of 150 rows into `hazardous = 1`.
- **Risk:** SPEC section 3 fixes the rule ("apply PM2.5 ≥ 165 to your predicted PM2.5"), and SPEC overrides the handbook on mechanics. The change would have broken the submission contract and labelled areas forecast at 130–153 µg/m³ as hazardous when the official rule says they are not.
- **Detection:** Our team re-read SPEC section 3 and challenged the change. The AI's own October check showed the trade-off: 7 of 13 hazardous days caught, but only about 6% of alarms were real.
- **Correction + verification:** `predictions.csv` again uses exactly ≥ 165, and `validate_submission.py` enforces it. The 130 µg/m³ level stays only as a labelled advisory "early-warning watch" in the dashboard and assistant, with its recall and false alarms reported. `test_exact_shape_and_rule` checks the 165 rule.

## Entry 3
- **Context + wrong output:** The AI's retrieval synonyms mapped every form of "close" to one concept, and "emissions" to "industry". So "When do schools close?" also cited DOC-01 ("keep windows closed"), odd-even questions cited DOC-08 (which only mentions DOC-05), and brick-kiln questions cited the transport advisory.
- **Risk:** `sources` must list only documents actually relevant and used. Irrelevant citations look like invented evidence and could mislead users about which rule applies.
- **Detection:** A 35-question retrieval evaluation (`tests/retrieval_eval.py`) with required and allowed documents per question. It scored 34/35 relevant but only 29/35 free of unrelated citations.
- **Correction + verification:**
  - Document titles are weighted.
  - Passages that merely point to another document ("see DOC-05") are down-ranked.
  - Every cited document must match a specific concept of the question, not just generic words like "smog" or "close".
  - The colliding synonyms were removed.

  Result: 35/35 relevant and 35/35 clean; `test_retrieval_quality` keeps it that way.

---
*Example (from the handbook): AI suggested a shuffled train/test split. Date-range inspection revealed future leakage. The team changed to chronological validation and accepted a worse but credible score.*
