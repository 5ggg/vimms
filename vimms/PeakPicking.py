import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.optimize import minimize
from pyDOE import *

from vimms.BOMAS import GetScaledValues
from vimms.Roi import Roi, make_roi
from vimms.PythonMzmine import get_base_scoring_df


PARAM_RANGE_N0 = [[0, 250]]
PARAM_RANGE_N1 = [[0, 250], [0, 500], [0, 100], [1, 50]]

from vimms.BOMAS import QCB_MZML2CHEMS_DICT

def MSmixture(theta, y, t, N):
    mean = np.array([theta[0] for i in y])
    if N == 1:
        mean += (theta[1]**2) * norm.pdf(t, abs(theta[2]), abs(theta[3]))
    return sum((y-mean)**2)


def Minimise_MSmixture(y, t, N, param_range_init, method='Nelder-Mead', restarts=10):
    init_values = GetScaledValues(restarts, param_range_init)
    opt_values = []
    opt_mins = []
    for i in range(restarts):
        #model_results = minimize(MSmixture, init_values[:, i], args=(y, t, N), method=method)
        model_results = minimize(MSmixture_posterior, init_values[:, i], args=(y, t, N), method=method)
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


def MSmixture_posterior(theta, y, t, N, sigma=None, prior_mu=None, prior_var=None, neg_like=True):
    mean = np.array([theta[0] for i in y])
    if N == 1:
        mean += (theta[1]**2) * norm.pdf(t, abs(theta[2]), abs(theta[3]))
    var = sum((y-mean)**2) / (len(y))
    log_like = sum(np.log(norm.pdf(y, mean, var)))
    if neg_like:
        return -log_like
    return log_like


class SMC_MSmixture(object):
    def __init__(self, n_particles, n_mixtures, prior_mu, prior_var, jitter_params, prior_sigsq=None):
        self.n_particles = n_particles
        self.n_mixtures = n_mixtures
        self.prior_mu = prior_mu
        self.prior_var = prior_var
        self.prior_sigsq = prior_sigsq
        self.jitter_params = jitter_params
        self.t = []
        self.y = []

        # get inital particles
        self.current_particles = np.random.multivariate_normal(prior_mu, np.diagflat(prior_var), self.n_particles)
        self.particles = []

    def update(self, new_t, new_y):
        # add new data to current data
        self.t.append(new_t)
        self.y.append(new_y)
        # get the weights
        self.current_weights = self._get_weights()
        # resample particles
        self.current_particles = self._get_resampled_particles()
        # add jitter
        self.current_particles = self._add_jitter()
        # update particles
        self.particles.append(self.current_particles)

    def _get_resampled_particles(self):
        updated_particles = self.current_particles[
            np.random.choice(self.n_particles, self.n_particles, p=self.current_weights)]
        return updated_particles

    def _add_jitter(self):
        noise = np.random.normal(loc=0, scale=self.jitter_params, size=self.current_particles.shape)
        return self.current_particles + noise

    def _get_weights(self):
        # get posteriors
        weights = [MSmixture_posterior(self.current_particles[i], self.y, self.t, self.n_mixtures, neg_like=False) for i in
                   range(self.n_particles)]
        updated_weights = np.exp(np.array(weights) - np.array(weights).max())
        # re weight
        normalised_weights = np.exp(updated_weights) / sum(np.exp(updated_weights))
        return normalised_weights


def get_intensity_difference(roi_intensities, n, positive=True):
    # add exception for short roi
    difference = []
    for i in range(len(roi_intensities) - n):
        difference.append(np.log(roi_intensities[i+n]) - np.log(roi_intensities[i]))
    if positive:
        return max(difference)
    else:
        return min(difference)


def get_max_increasing(roi_intensities, n_skip=0, increasing_TF=True):
    # add exception for short roi
    max_increasing = 0
    for i in range(len(roi_intensities)):
        current_increasing = 0
        current_skip = 0
        if len(roi_intensities[i:]) <= max_increasing:
            break
        for j in range(1,len(roi_intensities[i:])):
            if (roi_intensities[i:][j] > roi_intensities[i:][j-1-current_skip]) == increasing_TF:
                current_increasing += 1 + current_skip
                current_skip = 0
            else:
                current_skip +=1
                if current_skip > n_skip:
                    max_increasing = max(max_increasing, current_increasing)
                    break
    return max_increasing

def get_intensity_list(roi, max_length):
    if max_length is None:
        return roi.intensity_list
    else:
        return roi.intensity_list[0:max_length]


def get_roi_classification_params(rois,  max_length=None, include_log_max_intensity=True, include_log_intensity_difference=True, consecutively_change_max=3, intensity_change_max=5, lag_max=5):
    colnames = []
    if include_log_max_intensity:
        colnames.append('log_max_intensity')
    if include_log_intensity_difference:
        colnames.append('log_intensity_difference')
    if consecutively_change_max > 0:
        for i in range(consecutively_change_max):
            colnames.extend(['n_increase_' +str(i), 'n_decrease_' + str(i), 'n_interaction_' + str(i)])
    if intensity_change_max > 0:
        for i in range(intensity_change_max):
            colnames.extend(['intensity_increase_' + str(i), 'intensity_decrease_' + str(i), 'intensity_interaction_' + str(i+1)])
    if lag_max > 0:
        for i in range(lag_max):
            colnames.append('autocorrelation_' + str(i+1))
    df = pd.DataFrame(columns=colnames)
    for j in range(len(rois)):
        if max_length is None:
            intensities = rois[j].intensity_list
        else:
            max_it = min(len(rois[j].intensity_list), max_length)
            intensities = rois[j].intensity_list[0:max_it]
        values = []
        if include_log_max_intensity:
            values.append(np.log(max(intensities)))
        if include_log_intensity_difference:
            values.append(np.log(max(intensities)) - np.log(min(intensities)))
        if consecutively_change_max > 0:
            for i in range(consecutively_change_max):
                increase = get_max_increasing(intensities, i, True)
                decrease = get_max_increasing(intensities, i, False)
                interaction = increase * decrease
                values.extend([increase, decrease, interaction])
        if intensity_change_max > 0:
            for i in range(intensity_change_max):
                increase = get_intensity_difference(intensities, i+1, True)
                decrease = get_intensity_difference(intensities, i+1, False)
                interaction = increase * decrease
                values.extend([increase, decrease, interaction])
        if lag_max > 0:
            for i in range(lag_max):
                auto = pd.Series(intensities).autocorr(lag=i+1)
                values.append(auto)
        df.loc[j] = values
    return df

def mzml2classificationdata(mzmls, mzml_picked_peaks_files, min_roi_length=5, mzml2chems_dict=QCB_MZML2CHEMS_DICT):
    base_roi = []
    base_status = []
    split_roi = []
    split_status = []
    for i in range(len(mzmls)):
        good_roi, junk = make_roi(mzmls[i], mz_tol=mzml2chems_dict['mz_tol'], mz_units=mzml2chems_dict['mz_units'],
                                  min_length=min_roi_length, min_intensity=mzml2chems_dict['min_intensity'],
                                  start_rt=mzml2chems_dict['start_rt'], stop_rt=mzml2chems_dict['stop_rt'])
        picked_peaks = get_base_scoring_df(mzml_picked_peaks_files[i])
        temp_base_roi, temp_base_status, temp_split_roi, temp_split_status = rois2classificationdata(good_roi,
                                                                                                     picked_peaks)
        base_roi.extend(temp_base_roi)
        base_status.extend(temp_base_status)
        split_roi.extend(temp_split_roi)
        split_status.extend(temp_split_status)
    return base_roi, base_status, split_roi, split_status


def rois2classificationdata(rois, picked_peaks):
    base_roi = []
    base_status = []
    split_roi = []
    split_status = []
    for roi in rois:
        rt_check1 = (picked_peaks['rt min'] >= roi.rt_list[0]) & (roi.rt_list[-1] >= picked_peaks['rt min'])
        rt_check2 = (picked_peaks['rt max'] >= roi.rt_list[0]) & (roi.rt_list[-1] >= picked_peaks['rt max'])
        rt_check3 = (picked_peaks['rt min'] <= roi.rt_list[0]) & (picked_peaks['rt max'] >= roi.rt_list[-1])
        possible_peaks = np.nonzero(rt_check1 | rt_check2 | rt_check3)[0]
        # check_roi_min = roi.rt_list[0] <= picked_peaks['rt min']
        # check_roi_max = picked_peaks['rt max'] <= roi.rt_list[-1]
        # possible_peaks = np.nonzero(check_roi_min & check_roi_max)[0]
        if len(possible_peaks) == 0:
            base_roi.append(roi)
            split_roi.append(roi)
            base_status.append(0)
            split_status.append(0)
        updated_possible_peaks = []
        for j in possible_peaks:
            if picked_peaks.iloc[j]['m/z min'] < roi.get_mean_mz() < picked_peaks.iloc[j]['m/z max']:
                updated_possible_peaks.append(j)
        if len(updated_possible_peaks) == 0:
            base_roi.append(roi)
            split_roi.append(roi)
            base_status.append(0)
            split_status.append(0)
        else:
            if len(updated_possible_peaks) == 1:
                base_roi.append(roi)
                split_roi.append(roi)
                base_status.append(1)
                split_status.append(1)
            if len(updated_possible_peaks) > 1:
                base_roi.append(roi)
                base_status.append(1)
                df = picked_peaks.iloc[updated_possible_peaks]
                df = df.sort_values(by=['rt min'])
                splits = (np.array(df['rt min'][1:]) + np.array(df['rt max'][0:-1])) / 2
                splits = np.insert(np.insert(splits, 0, 0), len(splits) + 1, 2000)
                for j in range(len(splits) - 1):
                    check_range1 = roi.rt_list > splits[j]
                    check_range2 = roi.rt_list < splits[j + 1]
                    mz = np.array(roi.mz_list)[np.nonzero(check_range1 & check_range2)[0]].tolist()
                    rt = np.array(roi.rt_list)[np.nonzero(check_range1 & check_range2)[0]].tolist()
                    intensity = np.array(roi.intensity_list)[np.nonzero(check_range1 & check_range2)].tolist()
                    split_roi.append(Roi(mz, rt, intensity))
                    split_status.append(1)
    return base_roi, base_status, split_roi, split_status

