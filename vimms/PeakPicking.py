import numpy as np
from scipy.stats import norm
from scipy.optimize import minimize
from pyDOE import *

from vimms.BOMAS import GetScaledValues


PARAM_RANGE_N0 = [[0, 250]]
PARAM_RANGE_N1 = [[0, 250],[0,500],[0,100],[1,50]]


def MSmixture(theta, y, t, N):
    mean = np.array([theta[0] for i in y])
    if N == 1:
        mean += np.array([abs(theta[0]) for i in y]) + (theta[1]**2) * norm.pdf(t, abs(theta[2]), abs(theta[3]))
    return sum((y-mean)**2)


def Minimise_MSmixture(theta0, y, t, N, param_range_init, method='Nelder-Mead', restarts=10):
    init_values = GetScaledValues(restarts, param_range_init)
    opt_values = []
    opt_mins = []
    for i in range(restarts):
        model_results = minimize(MSmixture, init_values[:, i], args=(y, t, N), method=method)
        opt_mins.append(model_results)
        opt_values.append(model_results['fun'])
    final_model = opt_mins[np.array(opt_values).argmin()]
    min_value = np.array(opt_values).min()
    return final_model['x'], min_value


def GetPlot_MSmixture(t, theta, N):
    prediction = np.array([float(theta[0]) for i in t])
    if N == 1:
        prediction += np.array(theta[1] * norm.pdf(t, theta[2], theta[3]))
    return t, prediction
