# Validation report

## Moon (7 known analogs)

- median percentile of known analogs: **40.5** (null baseline 52.0)
- recall in the top 5 % of land cells: **14 %**
- recall in the top 10 % of land cells: **14 %** (target: 70 %)

- by target group: equatorial (Apollo 17) median 68.3; polar (Artemis, Shackleton) median 40.5
- The known lunar analogs are Apollo-era training sites for equatorial mare and impact geology. Against the equatorial target they rank well above chance; against the polar Artemis targets they do not - there is no documented set of Earth analogs for the lunar south pole to validate against.

| site | percentile | accessible by design |
|---|---:|---|
| Mauna Kea (Hawaii) | 96.5 | no |
| Askja (Iceland) | 84.5 | no |
| Meteor Crater (Arizona) | 54.1 | yes |
| SP Crater / Black Point lava flow (Arizona) | 40.5 | yes |
| Craters of the Moon (Idaho) | 30.1 | yes |
| Sudbury Basin (Canada) | 29.7 | yes |
| Ries Crater (Germany) | 27.0 | yes |

### Ablation (change in median percentile)

| variant | delta |
|---|---:|
| without_T | +29.50 |
| without_H | +7.73 |
| without_M | +0.00 |
| without_W | -9.17 |
| without_B | +0.00 |
| without_C | +1.78 |
| without_A | +0.00 |
| without_I | +0.00 |
| gravity_scaling_on | +0.00 |

## Mars (9 known analogs)

- median percentile of known analogs: **73.0** (null baseline 49.8)
- recall in the top 5 % of land cells: **11 %**
- recall in the top 10 % of land cells: **11 %** (target: 70 %)

| site | percentile | accessible by design |
|---|---:|---|
| Atacama Desert - Yungay | 100.0 | no |
| Holuhraun lava field (Iceland) | 84.0 | no |
| Mars Desert Research Station (Utah) | 81.5 | yes |
| Rio Tinto | 73.7 | yes |
| Lanzarote (Canary Islands) | 73.0 | yes |
| Haughton Crater (Devon Island) | 69.3 | no |
| Svalbard - Bockfjord volcanic complex | 65.1 | no |
| Death Valley / Mojave | 12.6 | yes |
| McMurdo Dry Valleys | 11.6 | no |

### Ablation (change in median percentile)

| variant | delta |
|---|---:|
| without_T | -10.37 |
| without_H | -2.41 |
| without_M | +0.00 |
| without_W | +0.30 |
| without_B | +0.00 |
| without_C | +4.26 |
| without_A | +0.00 |
| without_I | +0.00 |
| gravity_scaling_on | +0.00 |

## How to read this

Known analog sites were partly chosen because they are accessible, not only
because they are physically similar. Sites marked *accessible by design* are
expected to rank lower, and that is a property of the ground truth, not a
failure of the method.
