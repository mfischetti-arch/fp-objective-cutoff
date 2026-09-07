set heuristics emphasis off
..
..
set load sets_f/10teams_rec50_s0.set
..
read /nfsd/rop/instances/miplib2017/10teams.mps.gz
optimize
display statistics
write solution sols/fact/10teams__rec50_s0.sol
quit
