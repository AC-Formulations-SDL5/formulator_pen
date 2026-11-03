"""Reproduce the numbers reported in the Formulator-Pen manuscript from the raw data.

Writes CSV tables to <out_dir>:
  calibration_fits.csv        pre-calibration slope a, offset b, R^2, RMSE, volumetric slope a/rho (eq. 2)
  validation_summary.csv      mean, SD, CV and systematic error of every validation condition (eq. 4)
  operating_parameters.csv    Table 3: tip, actuator settings, n, intake time and effective conductance
  run_order_analysis.csv      first-dispense bias and run-order drift of every validation condition
  scorecard.csv               Fig. 6E: raw and normalized scores of the four strategies
  platform_validation.csv     Section 4.2: per-pen summary of the tool-changing run
and prints the summary statistics quoted in the text.

Usage: python statistics.py <data_dir> <out_dir>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

DATA, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

STRATEGY = {3: "Fill-and-Dispense", 4: "Remote-Reservoir", 5: "On-Board Reservoir", 6: "Pressurized On-Board"}
RUNS = [f"Run{i}" for i in range(1, 11)]
TUBE_ID_M = 3.18e-3          # intake tubing inner diameter
TUBE_LENGTH_M = {4: 0.30, 5: 0.04, 6: 0.04}

fluids = pd.read_csv(DATA / "fluids.csv")
nominal_to = fluids.set_index("nominal_viscosity_cP")
df = pd.read_csv(DATA / "formulatorpen.csv", na_values="NULL")
df["viscosity_cP"] = df["Viscosity (cP)"].map(nominal_to["measured_viscosity_cP"])
df["density_g_mL"] = df["Viscosity (cP)"].map(nominal_to["density_g_mL"])
df["strategy"] = df["Prototype"].map(STRATEGY)
df["n"] = df[RUNS].notna().sum(axis=1)
df["mean_g"] = df[RUNS].mean(axis=1)
df["sd_g"] = df[RUNS].std(axis=1)
df["cv_pct"] = df["sd_g"] / df["mean_g"] * 100
df["error_pct"] = (df["mean_g"] - df["Volume (g)"]) / df["Volume (g)"] * 100
cal = df[df["Data Type"] == "Calibration"]
val = df[df["Data Type"] == "Test"]

# --- calibration fits (eq. 2)
fits = []
for (p, v), s in cal.groupby(["Prototype", "viscosity_cP"]):
    s = s.sort_values("Volume (g)")
    f = stats.linregress(s["Volume (g)"], s["mean_g"])
    rmse = np.sqrt(((s["mean_g"] - (f.slope * s["Volume (g)"] + f.intercept)) ** 2).mean())
    fits.append(dict(strategy=STRATEGY[p], prototype=p, viscosity_cP=v, slope_a=f.slope, offset_b_g=f.intercept,
                     r2=f.rvalue ** 2, rmse_g=rmse, volumetric_slope=f.slope / s["density_g_mL"].iloc[0],
                     levels=len(s), n_per_level=f'{int(s["n"].min())}-{int(s["n"].max())}'))
fits = pd.DataFrame(fits)
fits.round(4).to_csv(OUT / "calibration_fits.csv", index=False)

# --- validation summary (eq. 4)
cols = ["strategy", "viscosity_cP", "Volume (g)", "n", "mean_g", "sd_g", "cv_pct", "error_pct",
        "Mean Job Time In (s)", "Mean Job Time Out (s)", "Mean Job Time Misc (s)", "Mean Job Time Total (s)"]
vs = val[cols].rename(columns={"Volume (g)": "target_g"}).sort_values(["strategy", "viscosity_cP", "target_g"])
vs.round(4).to_csv(OUT / "validation_summary.csv", index=False)

# --- Table 3: operating parameters, intake time and effective intake conductance mu*Q_in
rows = []
for (p, v), s in val.groupby(["Prototype", "viscosity_cP"]):
    r = s.iloc[0]
    fit = fits[(fits.prototype == p) & (fits.viscosity_cP == v)].iloc[0]
    t3 = s[np.isclose(s["Volume (g)"], 3.0)]
    t_in = t3["Mean Job Time In (s)"].iloc[0] if len(t3) else np.nan
    v_cmd_m3 = (3.0 - fit.offset_b_g) / fit.slope_a * 1e-6          # commanded intake volume for a 3 g dose
    mu_q = v / 1000 * v_cmd_m3 / t_in if t_in == t_in else np.nan     # Pa s * m^3/s = Pa m^3
    dp_tube = 128 * mu_q * TUBE_LENGTH_M.get(p, np.nan) / (np.pi * TUBE_ID_M ** 4) if mu_q == mu_q else np.nan
    rows.append(dict(strategy=STRATEGY[p], viscosity_cP=v, tip_gauge=int(r["Dispense Tip Gauge"]),
                     pwm_in_out=f'{int(r["PWM%In"])}/{int(r["PWM%Out"])}',
                     max_step_in_out_pct=f'{r["Step%In"]:g}/{r["Step%Out"]:g}'.replace("nan", "-"),
                     pause_in_out_s=f'{r["SettleIn (s)"]:g}/{r["SettleOut (s)"]:g}'.replace("nan", "-"),
                     n_cal_per_level=fit.n_per_level, n_val_per_level=f'{int(s["n"].min())}-{int(s["n"].max())}',
                     slope_a=round(fit.slope_a, 3), volumetric_slope=round(fit.volumetric_slope, 3),
                     intake_time_3g_s=round(t_in, 1) if t_in == t_in else None,
                     muQ_in_1e7_Pa_m3=round(mu_q * 1e7, 2) if mu_q == mu_q else None,
                     tubing_pressure_drop_kPa=round(dp_tube / 1000, 1) if dp_tube == dp_tube else None,
                     job_time_3g_min=round(t3["Mean Job Time Total (s)"].iloc[0] / 60, 2) if len(t3) else None))
pd.DataFrame(rows).to_csv(OUT / "operating_parameters.csv", index=False)

# --- run-order analysis (Section 3.5)
ro = []
for _, r in df[df["Data Type"].isin(["Test", "Test (2x)", "Test (3x)", "Test_tighter"])].iterrows():
    x = r[RUNS].dropna().values.astype(float)
    if len(x) < 4:
        continue
    dev = x - r["Volume (g)"]
    trend = stats.linregress(np.arange(len(x)), dev)
    ro.append(dict(strategy=r["strategy"], data_type=r["Data Type"], viscosity_cP=r["viscosity_cP"], target_g=r["Volume (g)"],
                   n=len(x), first_minus_rest_g=dev[0] - dev[1:].mean(), drift_g_per_run=trend.slope, drift_p=trend.pvalue))
ro = pd.DataFrame(ro)
ro.round(5).to_csv(OUT / "run_order_analysis.csv", index=False)

# --- scorecard (Fig. 6E): matched condition 14,570 cP, min-max normalized, 1 = best
m = val[val["viscosity_cP"] == 14570]
sc = pd.DataFrame(index=list(STRATEGY.values()))
for p, name in STRATEGY.items():
    fit = fits[(fits.prototype == p) & (fits.viscosity_cP == 14570)].iloc[0]
    sm = m[m["Prototype"] == p]
    sc.loc[name, "accuracy_abs_1_minus_a_over_rho"] = abs(1 - fit.volumetric_slope)
    sc.loc[name, "precision_mean_cv_pct"] = sm["cv_pct"].mean()
    sc.loc[name, "throughput_5g_min"] = sm.loc[np.isclose(sm["Volume (g)"], 5.0), "Mean Job Time Total (s)"].iloc[0] / 60
    sc.loc[name, "viscosity_range_cP"] = val.loc[val["Prototype"] == p, "viscosity_cP"].max()
sc["operational_autonomy"] = [0.5, 1.0, 0.5, 0.5]     # mean of CNC independence and refill autonomy (design rubric)
sc["mechanical_simplicity"] = [1.0, 0.3, 0.65, 0.45]  # ordinal design score
for c, lower_is_better in [("accuracy_abs_1_minus_a_over_rho", True), ("precision_mean_cv_pct", True), ("throughput_5g_min", True),
                           ("viscosity_range_cP", False), ("operational_autonomy", False), ("mechanical_simplicity", False)]:
    x = sc[c]; nrm = (x - x.min()) / (x.max() - x.min())
    sc[c + "_score"] = 1 - nrm if lower_is_better else nrm
sc.round(4).to_csv(OUT / "scorecard.csv", index_label="strategy")

# --- platform validation (Section 4.2)
pv = pd.read_csv(DATA / "platform_validation.csv")
pv["error_pct"] = (pv["actual_weight_g"] - pv["target_g"]) / pv["target_g"] * 100
pv["overhead_s"] = pv["job_duration_s"] - pv["dispense_time_s"]
ps = pv.groupby("fluid").agg(n=("actual_weight_g", "size"), target_g=("target_g", "first"), mean_g=("actual_weight_g", "mean"),
                             sd_g=("actual_weight_g", "std"), min_error_pct=("error_pct", "min"), max_error_pct=("error_pct", "max"),
                             overhead_min_s=("overhead_s", "min"), overhead_max_s=("overhead_s", "max"))
ps["cv_pct"] = ps["sd_g"] / ps["mean_g"] * 100
ps["error_pct"] = (ps["mean_g"] - ps["target_g"]) / ps["target_g"] * 100
ps.round(4).to_csv(OUT / "platform_validation.csv")

# --- summary quoted in the text
print(f"dispenses: calibration {int(cal['n'].sum()) + int(df[df['Data Type'] == 'Calibration_tighter']['n'].sum())}, "
      f"validation {int(df[df['Data Type'].str.startswith('Test')]['n'].sum())}")
print(f"volumetric slopes a/rho: {fits.volumetric_slope.min():.3f}-{fits.volumetric_slope.max():.3f}; "
      f"mass slopes a: {fits.slope_a.min():.3f}-{fits.slope_a.max():.3f}")
v3 = vs[np.isclose(vs.target_g, 3.0)]
print(f"3.0 g validation: {len(v3)} pairs, CV <= 0.5% in {(v3.cv_pct <= 0.5).sum()}, error {v3.error_pct.min():.2f} to {v3.error_pct.max():.2f}%")
std = ro[ro.data_type == "Test"]
print(f"run order: {len(ro)} conditions; first-minus-rest median {ro.first_minus_rest_g.median():+.4f} g, "
      f"IQR {ro.first_minus_rest_g.quantile(.25):+.4f} to {ro.first_minus_rest_g.quantile(.75):+.4f} g, "
      f"Wilcoxon p = {stats.wilcoxon(ro.first_minus_rest_g).pvalue:.2f}; drift p<0.05 in {(ro.drift_p < 0.05).sum()} "
      f"({((ro.drift_p < 0.05) & (ro.drift_g_per_run > 0)).sum()} positive)")
print("absolute SD (g), median by strategy at <=1 g and >=3 g:")
for name, s in val.groupby("strategy"):
    print(f"  {name:22s} {s[s['Volume (g)'] <= 1]['sd_g'].median():.4f}  {s[s['Volume (g)'] >= 3]['sd_g'].median():.4f}")
print(ps[["n", "mean_g", "sd_g", "cv_pct", "error_pct", "min_error_pct", "max_error_pct", "overhead_min_s", "overhead_max_s"]].round(3).to_string())
print("tables written to", OUT)
