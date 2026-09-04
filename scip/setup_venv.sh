#!/bin/bash
# Ambiente per fpc sul DEI. Da eseguire SU arrow-16, che e' la lama fuori coda
# tenuta apposta per compilare e installare:
#
#     ssh dei 'ssh arrow-16 "bash ~/fpc/setup_venv.sh"'
#
# Dal login non funzionerebbe: li' l'interprete e' un 3.6 e non e' quello dei
# nodi di calcolo. Il venv sta sotto la home (~/fpc), non su /nfsd/rop che e'
# condivisa col gruppo; le istanze si leggono da /nfsd/rop/instances e basta.
set -e
source /nfsd/opt/gurobi.env
cd ~/fpc

if [ ! -d venv ]; then
  python3.12 -m venv venv
fi
./venv/bin/pip -q install --upgrade pip
# gurobipy 13.0.x per parlare con la licenza /nfsd/opt/gurobi.lic (Gurobi 13.0.1)
./venv/bin/pip -q install "gurobipy==13.0.*" numpy scipy

echo "== verifica su $(hostname)"
./venv/bin/python - <<'PY'
import gurobipy as gp, numpy, scipy
print("gurobipy", gp.gurobi.version(), "| numpy", numpy.__version__, "| scipy", scipy.__version__)
e = gp.Env(params={"OutputFlag": 0})
m = gp.Model(env=e); x = m.addVars(5000, vtype="B", obj=1)
m.addConstr(x.sum() >= 7); m.optimize()
print("licenza ok: 5000 binarie, obj =", m.ObjVal)
PY
