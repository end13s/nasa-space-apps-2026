# Validation report

## Moon (7 known analogs)

- median percentile of known analogs: **70.3** (null baseline 51.5)
- recall in the top 5 % of land cells: **0 %**
- recall in the top 10 % of land cells: **29 %** (target: 70 %)

| site | percentile | accessible by design |
|---|---:|---|
| Mauna Kea (Hawaii) | 94.6 | no |
| Askja (Iceland) | 92.8 | no |
| Ries Crater (Germany) | 73.3 | yes |
| Sudbury Basin (Canada) | 70.3 | yes |
| Meteor Crater (Arizona) | 26.4 | yes |
| Craters of the Moon (Idaho) | 25.0 | yes |
| SP Crater / Black Point lava flow (Arizona) | 18.5 | yes |

### Ablation (change in median percentile)

| variant | delta |
|---|---:|
| without_T | -0.24 |
| without_H | -14.59 |
| without_M | +0.00 |
| without_W | -9.81 |
| without_B | +0.00 |
| without_C | +6.86 |
| without_A | +0.00 |
| without_I | +0.00 |
| gravity_scaling_on | +0.00 |

## Mars (9 known analogs)

- median percentile of known analogs: **62.4** (null baseline 50.5)
- recall in the top 5 % of land cells: **11 %**
- recall in the top 10 % of land cells: **11 %** (target: 70 %)

| site | percentile | accessible by design |
|---|---:|---|
| Atacama Desert - Yungay | 99.6 | no |
| Haughton Crater (Devon Island) | 82.6 | no |
| Holuhraun lava field (Iceland) | 82.3 | no |
| Mars Desert Research Station (Utah) | 69.0 | yes |
| Rio Tinto | 62.4 | yes |
| Lanzarote (Canary Islands) | 26.7 | yes |
| Svalbard - Bockfjord volcanic complex | 14.8 | no |
| Death Valley / Mojave | 12.6 | yes |
| McMurdo Dry Valleys | 11.5 | no |

### Ablation (change in median percentile)

| variant | delta |
|---|---:|
| without_T | +0.22 |
| without_H | -7.34 |
| without_M | +0.00 |
| without_W | -0.61 |
| without_B | +0.00 |
| without_C | -2.49 |
| without_A | +0.00 |
| without_I | +0.00 |
| gravity_scaling_on | +0.00 |

## How to read this

Known analog sites were partly chosen because they are accessible, not only
because they are physically similar. Sites marked *accessible by design* are
expected to rank lower, and that is a property of the ground truth, not a
failure of the method.
