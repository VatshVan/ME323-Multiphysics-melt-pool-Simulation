# Ti-6Al-4V input data: sources

Every number in `Ti6Al4V.cfg` and the Ti-6Al-4V entries of
`config/baseline.json` comes from one of the open-access sources below.
Where sources disagree, the alternative is listed.

## References

| Key | Source | Link |
|---|---|---|
| G18 | S. Ghosh et al., "Simulation of temperature, stress and microstructure fields during laser deposition of Ti-6Al-4V" (2018). Tables 1, 3, 4, "after" Boivineau et al., Int. J. Thermophys. 27 (2006) 507, and Welsch, Boyer & Collings, *Materials Properties Handbook: Titanium Alloys*, ASM (1993). | [arXiv:1809.01056](https://arxiv.org/abs/1809.01056) |
| Y22 | J. Yan, Q. Zhu, Z. Zhao, "Computational thermal multi-phase flow for metal additive manufacturing" (2022), Table 3 | [arXiv:2206.04799](https://arxiv.org/abs/2206.04799) |
| M24 | N. Much et al., "Improved accuracy of continuum surface flux models for metal additive manufacturing melt pool simulations" (2024), Table 1, which cites Mohr et al., Adv. Eng. Mater. 22 (2020) 2000169 (ISS levitation measurements), Boivineau et al. (2006) and Khairallah et al. (2016) | [arXiv:2401.12114](https://arxiv.org/abs/2401.12114) |
| S25 | "In situ electromagnetic field manipulation during LMD", *Materials Science in Additive Manufacturing* 4(1) (2025), Table 1 | [doi:10.36922/msam.8332](https://doi.org/10.36922/msam.8332) |
| J20 | B. Jelinek et al., "Two-dimensional thermal finite element model of directed energy deposition: matching melt pool temperature profile with pyrometer measurement" (2020), Table 1 | [arXiv:2007.01433](https://arxiv.org/abs/2007.01433) |
| Gao21 | S. Gao et al., Opt. Laser Technol. 142 (2021) 107215 (in `papers/`) | — |
| Far08 | A. Farzadi et al., Int. J. Adv. Manuf. Technol. 38 (2008) 258 (in `papers/`) | — |

## Values

| Quantity | Used | Source | Alternatives seen |
|---|---|---|---|
| Solidus T_s | 1878 K | Y22; G18 (1605 °C); S25 | M24 uses 1933 K as a numerical choice |
| Liquidus T_l | 1928 K | Y22; G18 (1655 °C); S25 | |
| Boiling T_b | 3533 K | Y22 | M24: 3133 K |
| Latent heat L_f | 2.90e5 J/kg | Y22 | S25: 2.92e5; G18: 3.65e5 |
| Density ρ (constant) | 4428 kg/m³ | G18 Table 4 (solid) | liquid 4087 (M24, Mohr 2020); S25: 4440; Y22: 4400 |
| k solid | 3.3201 + 0.012937 T W/m·K | Linear least-squares fit to G18 Table 1, 100–1500 °C (max error 0.003 W/m·K). The 20 °C entry (26.85) is excluded: it breaks the monotonic trend (8.15 at 100 °C) and is evidently a typo. | Y22: 21 (constant) |
| k liquid | −6.7374 + 0.018117 T W/m·K | Linear fit to G18 Table 1, 1665–2426 °C (max error 0.27); gives 28.2 at T_l | M24 (Boivineau): 28.63; Y22: 29 |
| c_p solid | 427.91 + 0.39895 T J/kg·K | Linear fit to G18 Table 3, 20–1400 °C (max error 46, at the α→β transition near 870 °C) | Y22: 670 (constant) |
| c_p liquid | 1130 J/kg·K | M24 (Boivineau 2006) | G18: 1126 at 1665 °C; Y22: 730 |
| Viscosity μ | 3.5e-3 Pa·s | M24 (Mohr 2020) | Y22: 5e-3; S25: 2.6e-3 |
| dσ/dT | −2.6e-4 N/m·K | Y22 | S25: −2.44e-4 |
| β (buoyancy) | 1.6e-4 1/K | S25 | |
| Emissivity ε | 0.54 | J20 (pyrometer-calibrated) | S25: 0.8 |
| Absorptivity η | 0.35 | M24 (Khairallah et al. 2016) | |
| Convection h | 25 W/m²·K | Gao21 | J20: 30 |
| A_mush, B | 1e8, 1e-4 | Project TA notes (Farzadi Eq. 2 form) | |

The smoothed step that replaces the linear solid fraction follows the form of
Gao21 Eq. 8; its cosine shape is the project's choice (see
`docs/SIMULATION_PLAN.md`).
