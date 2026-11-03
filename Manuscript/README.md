# Manuscript: data, analysis and figures

Data and code behind *Formulator-Pen: A Modular Dispensing Mechanism and Automated Robotic
Platform for High-Viscosity Liquid Handling in Self-Driving Laboratories*
(M. M. Rastegardoost, R. Durao, H. Ohsaka, F. Le Devedec; submitted to *Digital Discovery*).
The version of this repository that accompanies the manuscript is release v1.0.0, archived on
Zenodo: https://doi.org/10.5281/zenodo.23930607.

```
Manuscript/
  data/                    raw data (see data/README.md for every column)
    formulatorpen.csv        calibration and validation dispenses of the four strategies
    platform_validation.csv  multi-pen tool-changing run (Section 4.2, Fig. 7)
    fluids.csv               test fluids: nominal grade, measured viscosity, density, tip
  analysis/
    statistics.py            reproduces Table 3 and every number quoted in the text
    main_figures.ipynb       regenerates Figures 2-7
    si_figures.py            regenerates Figures S2-S6
    toc_graphic.py           table-of-contents graphic
    requirements.txt         Python packages
    results/                 tables written by statistics.py
  figures/
    main/                    Figures 1-7 (SVG and PNG)
    supplementary/           Figures S2-S6
    toc/                     table-of-contents graphic
    inputs/                  artwork used by the figure code (strategy schematics, platform photos)
```

## Reproduce

Python 3.10 or newer:

```bash
cd Manuscript/analysis
pip install -r requirements.txt
python statistics.py ../data results
jupyter nbconvert --to notebook --execute --inplace main_figures.ipynb
python si_figures.py ../data/formulatorpen.csv ../figures/inputs ../figures/supplementary
python toc_graphic.py ../figures/toc/toc_graphic
```

`statistics.py` prints the summary quoted in the paper (dispense counts, volumetric slopes,
precision at 3.0 g, run-order statistics, absolute error floor, platform validation) and
writes these tables to `results/`:

| File | Content | Manuscript |
|---|---|---|
| `calibration_fits.csv` | slope a, offset b, R², RMSE and volumetric slope a/ρ of every calibration | eq. 2, Fig. 4 |
| `validation_summary.csv` | mean, SD, CV and systematic error of every validation condition | eq. 4, Figs. 4-5 |
| `operating_parameters.csv` | tip, actuator settings, sample sizes, intake time, effective intake conductance μQ_in and tubing pressure drop | Table 3, Section 3.3 |
| `run_order_analysis.csv` | first-dispense bias and run-order drift of every validation condition | Section 3.5 |
| `scorecard.csv` | raw and normalized strategy scores | Fig. 6E |
| `platform_validation.csv` | per-pen summary of the tool-changing run | Section 4.2 |

Viscosities in all outputs are the measured values of `data/fluids.csv`; the dataset itself
keeps the nominal grade as the fluid key.
