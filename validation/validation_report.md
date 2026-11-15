# Validation report

## Moon (7 known analogs)

- median percentile of known analogs: **44.4** (null baseline 52.1)
- recall in the top 5 % of land cells: **0 %**
- recall in the top 10 % of land cells: **0 %** (target: 70 %)

| site | percentile | accessible by design |
|---|---:|---|
| Mauna Kea (Hawaii) | 85.9 | no |
| Askja (Iceland) | 68.5 | no |
| Sudbury Basin (Canada) | 45.3 | yes |
| Ries Crater (Germany) | 44.4 | yes |
| Meteor Crater (Arizona) | 40.2 | yes |
| SP Crater / Black Point lava flow (Arizona) | 26.8 | yes |
| Craters of the Moon (Idaho) | 5.9 | yes |

### Ablation (change in median percentile)

| variant | delta |
|---|---:|
| without_T | +10.97 |
| without_H | -9.33 |
| without_M | +0.00 |
| without_W | +3.98 |
| without_B | +0.00 |
| without_C | +1.88 |
| without_A | +0.00 |
| without_I | +0.00 |
| gravity_scaling_on | +0.00 |

## Mars (9 known analogs)

- median percentile of known analogs: **24.9** (null baseline 51.5)
- recall in the top 5 % of land cells: **11 %**
- recall in the top 10 % of land cells: **11 %** (target: 70 %)

| site | percentile | accessible by design |
|---|---:|---|
| Atacama Desert - Yungay | 99.4 | no |
| Haughton Crater (Devon Island) | 87.8 | no |
| Rio Tinto | 53.5 | yes |
| Holuhraun lava field (Iceland) | 42.4 | no |
| Mars Desert Research Station (Utah) | 24.9 | yes |
| McMurdo Dry Valleys | 18.0 | no |
| Svalbard - Bockfjord volcanic complex | 13.7 | no |
| Lanzarote (Canary Islands) | 9.3 | yes |
| Death Valley / Mojave | 6.4 | yes |

### Ablation (change in median percentile)

| variant | delta |
|---|---:|
| without_T | +31.83 |
| without_H | +8.63 |
| without_M | +0.00 |
| without_W | +9.46 |
| without_B | +0.00 |
| without_C | +39.25 |
| without_A | +0.00 |
| without_I | +0.00 |
| gravity_scaling_on | +0.00 |

## How to read this

Known analog sites were partly chosen because they are accessible, not only
because they are physically similar. Sites marked *accessible by design* are
expected to rank lower, and that is a property of the ground truth, not a
failure of the method.
