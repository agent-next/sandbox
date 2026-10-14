# =========================================================================
# rf-openems demo artifact: 2.45 GHz microstrip patch antenna on FR-4.
# Written from scratch for this demo; geometry equations per Balanis
# (*Antenna Theory* 4th ed.) and Pozar. PHYSICS ONLY — the judge runs
# these numbers through MEEP and decides.
# =========================================================================

# ---- design parameters (the judge reads & mutates these) ------------------
f_target_ghz = 2.45     # GHz — target resonance
er           = 4.4      # FR-4 relative permittivity
tanD         = 0.02     # FR-4 loss tangent
patch_L      = 30.0     # mm — patch length (along feed)
patch_W      = 37.0     # mm — patch width
sub_h        = 1.6      # mm — substrate thickness
feed_inset   = 5.0      # mm — feed point inset from the radiating edge
line_L       = 12.0     # mm — feed line beyond the patch edge
line_w       = 3.1      # mm — feed line width (≈50 Ω for 1.6 mm FR-4)
resolution   = 10       # voxel cells per mm

# ---- run ------------------------------------------------------------------
def main():
    import os, sys, json
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "judge"))
    from sim_engine import simulate_antenna
    p = dict(f_target_ghz=f_target_ghz, er=er, tanD=tanD,
             patch_L=patch_L, patch_W=patch_W, sub_h=sub_h,
             feed_inset=feed_inset, line_L=line_L, line_w=line_w)
    r = simulate_antenna(p, resolution)
    s11  = r["s11_db"]; fr = r["freqs_ghz"]
    i = min(range(len(s11)), key=lambda k: s11[k])
    out = dict(params=p, S11_dB_at_target=None,
               f_res_GHz=fr[i],
               freqs_GHz=fr, S11_dB=s11)
    # closest sample to the target
    import bisect
    j = min(range(len(fr)), key=lambda k: abs(fr[k] - f_target_ghz))
    out["S11_dB_at_target"] = s11[j]
    with open(os.path.join(os.path.dirname(__file__), "antenna_results.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print("RESULT S11_at_{:.2f}GHz={:.2f}dB f_res={:.3f}GHz".format(
        f_target_ghz, out["S11_dB_at_target"], out["f_res_GHz"]))


if __name__ == "__main__":
    main()
