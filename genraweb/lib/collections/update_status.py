"""Stand alone script to report up to dateness.

Uses fp_updates.csv and nn_updates.csv in this folder.

fp_updates.csv lists FPs and non-FP filters (none currently 20240507), which the
pesticides list was at one point.  fp_updates.csv tracks up to dateness of FP
generation, i.e. the individual *_fp collections in the MongoDB DataMart.
nn_updates.csv lists FP x Filter pre-calculation of nearest neighbors as stored in
fp_info.  A lot of things will be updated / recalculated at once, but these files can
track dependencies given YYYYMMDD dates.
"""
from pathlib import Path

import pandas as pd

fp_path = Path(__file__).parent / "fp_updates.csv"
nn_path = Path(__file__).parent / "nn_updates.csv"
fp_stat = pd.read_csv(fp_path, dtype=str, keep_default_na=False)
nn_stat = pd.read_csv(nn_path, dtype=str, keep_default_na=False)
filters = ["None"] + fp_stat[fp_stat.Type.str.contains("Filter")].FP.to_list()
for fp in fp_stat.itertuples():
    # No calc. for Filter only entries
    fp_min_date = min(fp.UpstreamDate, fp.Import, fp.Calc or "99999999")
    ok = fp.UpstreamDate == fp_min_date
    msg = "OK" if ok else "OUTDATED"
    print(f"{msg:>8} {fp.FP}")
    for filter in filters:
        status = nn_stat[(nn_stat.FP == fp.FP) & (nn_stat.Filter == filter)]
        if status.empty:
            print(f"Adding {fp.FP} {filter} entry")
            nn_stat = nn_stat._append(
                dict(FP=fp.FP, Filter=filter, Calc="20230410"), ignore_index=True
            )
        else:
            assert len(status.index) == 1
            filter_min_date = (
                fp.UpstreamDate
                if filter == "None"
                else fp_stat[fp_stat.FP == filter].iloc[0].Upstream
            )
            ok = (
                ok
                and status.iloc[0].Calc <= fp.UpstreamDate
                and status.iloc[0].Calc <= filter_min_date
            )
            msg = "OK" if ok else "OUTDATED"
            print(f"    {msg:>8} {fp.FP} {filter}")

nn_stat.to_csv(nn_path, index=False)
