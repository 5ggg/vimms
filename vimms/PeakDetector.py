import numpy as np
import pandas as pd

from vimms.Roi import Roi, make_roi
from vimms.PythonMzmine import get_base_scoring_df

QCB_MZML2CHEMS_DICT = {'min_ms1_intensity': 1.75E5,
                  'mz_tol': 2,
                  'mz_units':'ppm',
                  'min_length':1,
                  'min_intensity':0,
                  'start_rt':0,
                  'stop_rt':1560}

def get_intensity_difference(roi_intensities, n, positive=True):
    # add exception for short roi
    difference = []
    for i in range(len(roi_intensities) - n):
        difference.append(np.log(roi_intensities[i + n]) - np.log(roi_intensities[i]))
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
        for j in range(1, len(roi_intensities[i:])):
            if (roi_intensities[i:][j] > roi_intensities[i:][j - 1 - current_skip]) == increasing_TF:
                current_increasing += 1 + current_skip
                current_skip = 0
            else:
                current_skip += 1
                if current_skip > n_skip:
                    max_increasing = max(max_increasing, current_increasing)
                    break
    return max_increasing


def get_intensity_list(roi, max_length):
    if max_length is None:
        return roi.intensity_list
    else:
        return roi.intensity_list[0:max_length]


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






def rois2classificationdata(rois, picked_peaks, mz_slack=0.01):
    base_roi = []
    base_status = []
    split_roi = []
    split_status = []
    for roi in rois:
        rt_check1 = (picked_peaks['rt min'] >= roi.rt_list[0]) & (roi.rt_list[-1] >= picked_peaks['rt min'])
        rt_check2 = (picked_peaks['rt max'] >= roi.rt_list[0]) & (roi.rt_list[-1] >= picked_peaks['rt max'])
        rt_check3 = (picked_peaks['rt min'] <= roi.rt_list[0]) & (picked_peaks['rt max'] >= roi.rt_list[-1])
        rt_check = rt_check1 | rt_check2 | rt_check3
        # plus and minus one is just slack for the initital check
        initial_mz_check = (picked_peaks['m/z max'] + 1 >= roi.get_mean_mz()) & (
                    roi.get_mean_mz() >= picked_peaks['m/z min'] - 1)
        possible_peaks = np.nonzero(rt_check & initial_mz_check)[0]
        if len(possible_peaks) == 0:
            base_roi.append(roi)
            split_roi.append(roi)
            base_status.append(0)
            split_status.append(0)
        else:
            updated_possible_peaks = []
            for j in possible_peaks:
                peak = picked_peaks.iloc[j]
                check_peak = np.nonzero((peak['rt min'] < roi.rt_list) & (roi.rt_list < peak['rt max']))[0]
                mean_mz = np.mean(np.array(roi.mz_list)[check_peak])
                if peak['m/z min'] - mz_slack < mean_mz < peak['m/z max'] + mz_slack:
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


def get_roi_classification_params(rois,  roi_param_dict):
    df = pd.DataFrame()
    if roi_param_dict['include_log_max_intensity']:
        df['log_max_intensity'] = np.log([roi.get_max_intensity() for roi in rois])
    if roi_param_dict['include_log_intensity_difference']:
        df['log_intensity_difference'] = np.log(df['log_max_intensity']) - np.log([roi.get_min_intensity() for roi in rois])
    if roi_param_dict['consecutively_change_max'] > 0:
        for i in range(roi_param_dict['consecutively_change_max']):
            df['n_increase_' + str(i)] = [get_max_increasing(roi.intensity_list, i, True) for roi in rois]
            df['n_decrease_' + str(i)] = [get_max_increasing(roi.intensity_list, i, False) for roi in rois]
            df['n_interaction_' + str(i)] = df['n_increase_' + str(i)] * df['n_decrease_' + str(i)]
    if roi_param_dict['intensity_change_max'] > 0:
        for i in range(roi_param_dict['intensity_change_max']):
            df['intensity_increase_' + str(i)] = [get_intensity_difference(roi.intensity_list, i+1, True) for roi in rois]
            df['intensity_decrease_' + str(i)] = [get_intensity_difference(roi.intensity_list, i+1, False) for roi in rois]
            df['intensity_interaction_' + str(i)] = df['intensity_increase_' + str(i)] * df['intensity_decrease_' + str(i)]
    if roi_param_dict['lag_max'] > 0:
        for i in range(roi_param_dict['lag_max']):
            df['autocorrelation_' + str(i+1)] = [roi.get_autocorrelation(i+1) for roi in rois]
    return df

    # colnames = []
    # #if roi_param_dict['include_log_max_intensity']:
    # colnames.append('log_max_intensity')
    # #if roi_param_dict['include_log_intensity_difference']:
    # colnames.append('log_intensity_difference')
    # #if roi_param_dict['consecutively_change_max'] > 0:
    # #     for i in range(roi_param_dict['consecutively_change_max']):
    # #         colnames.extend(['n_increase_' +str(i), 'n_decrease_' + str(i), 'n_interaction_' + str(i)])
    # # if roi_param_dict['intensity_change_max'] > 0:
    # #     for i in range(roi_param_dict['intensity_change_max']):
    # #         colnames.extend(['intensity_increase_' + str(i), 'intensity_decrease_' + str(i), 'intensity_interaction_' + str(i+1)])
    # # if roi_param_dict['lag_max'] > 0:
    # #     for i in range(roi_param_dict['lag_max']):
    # #         colnames.append('autocorrelation_' + str(i+1))
    # df = pd.DataFrame(columns=colnames)
    # for j in range(len(rois)):
    #     if max_length is None:
    #         intensities = rois[j].intensity_list
    #     else:
    #         max_it = min(len(rois[j].intensity_list), max_length)
    #         intensities = rois[j].intensity_list[0:max_it]
    #     values = []
    #     #if roi_param_dict['include_log_max_intensity']:
    #     values.append(np.log(max(intensities)))
    #     #if roi_param_dict['include_log_intensity_difference']:
    #     values.append(np.log(max(intensities)) - np.log(min(intensities)))
    #     # if roi_param_dict['consecutively_change_max'] > 0:
    #     #     for i in range(roi_param_dict['consecutively_change_max']):
    #     #         increase = get_max_increasing(intensities, i, True)
    #     #         decrease = get_max_increasing(intensities, i, False)
    #     #         interaction = increase * decrease
    #     #         values.extend([increase, decrease, interaction])
    #     # if roi_param_dict['intensity_change_max'] > 0:
    #     #     for i in range(roi_param_dict['intensity_change_max']):
    #     #         increase = get_intensity_difference(intensities, i+1, True)
    #     #         decrease = get_intensity_difference(intensities, i+1, False)
    #     #         interaction = increase * decrease
    #     #         values.extend([increase, decrease, interaction])
    #     # if roi_param_dict['lag_max'] > 0:
    #     #     for i in range(roi_param_dict['lag_max']):
    #     #         auto = pd.Series(intensities).autocorr(lag=i+1)
    #     #         values.append(auto)
    #     df.loc[j] = values
    # return df

