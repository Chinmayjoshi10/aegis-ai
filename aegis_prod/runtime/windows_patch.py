import multiprocessing as mp

try:
    mp.set_start_method("spawn", force=True)
except RuntimeError:
    pass
