# Source this to activate the rf-openems judge environment.
# Provides: RF_PY (python3.11 interpreter), PYTHONPATH, LD_LIBRARY_PATH,
# RF_FFMPEG (static ffmpeg binary).
BASE="${RF_OPENEMS_HOME:-$HOME/.rf-openems}"
SYSROOT="$BASE/sysroot"
if [ -x /usr/bin/python3.11 ]; then
    RF_PY=/usr/bin/python3.11
elif [ -x "$SYSROOT/usr/bin/python3.11" ]; then
    RF_PY="$SYSROOT/usr/bin/python3.11"
    export PYTHONHOME="$SYSROOT/usr"
else
    echo "env.sh: python3.11 not found (run judge/setup.sh)" >&2
    return 1 2>/dev/null || exit 1
fi
export PYTHONPATH="$SYSROOT/usr/lib/python3/dist-packages:$SYSROOT/usr/lib/python3/dist-packages/CSXCAD:$BASE/pylibs"
export LD_LIBRARY_PATH="$SYSROOT/usr/lib/x86_64-linux-gnu"
export MPLBACKEND=Agg MPLCONFIGDIR="$BASE/.mpl"
# single-threaded everywhere: parallel BLAS reductions make the FDTD and the
# DFT post-processing non-deterministic at the last-ulp level (verdict JSON
# must be byte-identical across runs)
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
RF_FFMPEG="$BASE/bin/ffmpeg"
export RF_PY RF_FFMPEG
