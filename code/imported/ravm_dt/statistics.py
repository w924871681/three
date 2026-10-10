import numpy as np
import pandas as pd

def cluster_bootstrap(df,value,replicates=4000,seed=2904):
    # Each center first averages all seeds/stages within the supplied condition.
    centers=df.groupby('center_id')[value].mean().to_numpy()
    if not len(centers):raise ValueError('empty bootstrap')
    rng=np.random.default_rng(seed);means=centers[rng.integers(len(centers),size=(replicates,len(centers)))].mean(1)
    return float(centers.mean()),*np.quantile(means,[.025,.975]).tolist()

def paired_bootstrap(df,method,reference,value='deployed_service_mse'):
    d=df.groupby(['center_id','method'])[value].mean().unstack('method')
    diff=(d[method]-d[reference]).dropna().rename('difference').reset_index()
    return cluster_bootstrap(diff,'difference')
