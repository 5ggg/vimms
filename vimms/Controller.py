import bisect
import math
import time
from collections import defaultdict

import numpy as np
import pylab as plt
from loguru import logger

from vimms.Common import POSITIVE, DEFAULT_MS1_SCAN_WINDOW, DEFAULT_MSN_SCAN_WINDOW, DEFAULT_COLLISION_ENERGY
from vimms.DIA import DiaWindows
from vimms.MassSpec import ScanParameters, ExclusionItem
from vimms.Roi import match, Roi


class Precursor(object):
    def __init__(self, precursor_mz, precursor_intensity, precursor_charge, precursor_scan_id):
        self.precursor_mz = precursor_mz
        self.precursor_intensity = precursor_intensity
        self.precursor_charge = precursor_charge
        self.precursor_scan_id = precursor_scan_id

    def __repr__(self):
        return 'Precursor mz %f intensity %f charge %d scan_id %d' % (
            self.precursor_mz, self.precursor_intensity, self.precursor_charge, self.precursor_scan_id)


class Controller(object):
    def __init__(self):
        self.scans = defaultdict(list)  # key: ms level, value: list of scans for that level
        self.make_plot = False
        self.last_ms1_scan = None
        self.environment = None

    def set_environment(self, env):
        self.environment = env

    def handle_acquisition_open(self):
        raise NotImplementedError()

    def handle_acquisition_closing(self):
        raise NotImplementedError()

    def handle_scan(self, scan, queue_size):
        logger.info('Time %f Received %s' % (scan.rt, scan))
        self.scans[scan.ms_level].append(scan)

        # plot scan if there are peaks
        if scan.num_peaks > 0:
            self._plot_scan(scan)

        # we get an ms1 scan, if it has a peak, then store it for fragmentation next time
        if scan.ms_level == 1:
            if scan.num_peaks > 0:
                self.last_ms1_scan = scan
            else:
                self.last_ms1_scan = None

        # impelemnted by subclass
        new_tasks = self._process_scan(scan, queue_size)
        return new_tasks

    def update_state_after_scan(self, last_scan):
        raise NotImplementedError()

    def handle_state_changed(self, state):
        raise NotImplementedError

    def reset(self):
        raise NotImplementedError()

    def _process_scan(self, scan, queue_size):
        raise NotImplementedError()

    def _plot_scan(self, scan):
        if self.make_plot:
            plt.figure()
            for i in range(scan.num_peaks):
                x1 = scan.mzs[i]
                x2 = scan.mzs[i]
                y1 = 0
                y2 = scan.intensities[i]
                a = [[x1, y1], [x2, y2]]
                plt.plot(*zip(*a), marker='', color='r', ls='-', lw=1)
            plt.title('Scan {0} {1}s -- {2} peaks'.format(scan.scan_id, scan.rt, scan.num_peaks))
            plt.show()


class IdleController(Controller):
    """
    A controller that doesn't do any controlling.
    """

    def __init__(self):
        super().__init__()

    def handle_acquisition_open(self):
        logger.info('Acquisition open')

    def handle_acquisition_closing(self):
        logger.info('Acquisition closing')

    def _process_scan(self, scan, queue_size):
        new_tasks = []
        return new_tasks

    def update_state_after_scan(self, last_scan):
        pass

    def handle_state_changed(self, state):
        pass

    def reset(self):
        pass


class SimpleMs1Controller(Controller):
    """
    A simple MS1 controller which does a full scan of the chemical sample, but no fragmentation
    """

    def __init__(self):
        super().__init__()

    def handle_acquisition_open(self):
        logger.info('Acquisition open')

    def handle_acquisition_closing(self):
        logger.info('Acquisition closing')

    def _process_scan(self, scan, queue_size):
        new_tasks = [
            self.environment.get_default_scan_params()
        ]
        return new_tasks

    def update_state_after_scan(self, last_scan):
        pass

    def handle_state_changed(self, state):
        pass

    def reset(self):
        pass


class TopNController(Controller):
    """
    A Top-N controller. Does an MS1 scan followed by N fragmentation scans of the peaks with the highest intensity
    that are not excluded
    """

    def __init__(self, ionisation_mode, N, isolation_width, mz_tol, rt_tol, min_ms1_intensity):
        super().__init__()
        self.ionisation_mode = ionisation_mode
        self.N = N
        self.isolation_width = isolation_width  # the isolation width (in Dalton) to select a precursor ion
        self.mz_tols = mz_tol  # the m/z window (ppm) to prevent the same precursor ion to be fragmented again
        self.rt_tols = rt_tol  # the rt window to prevent the same precursor ion to be fragmented again
        self.min_ms1_intensity = min_ms1_intensity  # minimum ms1 intensity to fragment

        # for dynamic exclusion window
        self.exclusion_list = []  # a list of ExclusionItem

        # stores the mapping between precursor peak to ms2 scans
        self.precursor_information = defaultdict(list)  # key: Precursor object, value: ms2 scans

    def handle_acquisition_open(self):
        logger.info('Acquisition open')

    def handle_acquisition_closing(self):
        logger.info('Acquisition closing')

    def _process_scan(self, scan, queue_size):
        # if there's a previous ms1 scan to process
        new_tasks = []
        if self.last_ms1_scan is not None:

            mzs = self.last_ms1_scan.mzs
            intensities = self.last_ms1_scan.intensities
            rt = self.last_ms1_scan.rt

            # loop over points in decreasing intensity
            fragmented_count = 0
            idx = np.argsort(intensities)[::-1]
            for i in idx:
                mz = mzs[i]
                intensity = intensities[i]

                # stopping criteria is after we've fragmented N ions or we found ion < min_intensity
                if fragmented_count >= self.N:
                    logger.debug('Time %f Top-%d ions have been selected' % (rt, self.N))
                    break

                if intensity < self.min_ms1_intensity:
                    logger.debug(
                        'Time %f Minimum intensity threshold %f reached at %f, %d' % (
                            rt, self.min_ms1_intensity, intensity, fragmented_count))
                    break

                # skip ion in the dynamic exclusion list of the mass spec
                if self._is_excluded(mz, rt):
                    continue

                # create a new ms2 scan parameter to be sent to the mass spec
                dda_scan_params = self._get_dda_scan_param(mz, intensity, self.isolation_width,
                                                           self.mz_tols, self.rt_tols, DEFAULT_COLLISION_ENERGY)
                new_tasks.append(dda_scan_params)
                fragmented_count += 1

            # set this ms1 scan as has been processed
            self.last_ms1_scan = None
        return new_tasks

    def update_state_after_scan(self, last_scan):
        # add precursor and DEW information based on the current scan produced
        # the DEW list update must be done after time has been increased
        self._add_precursor_info(last_scan)
        self._manage_dynamic_exclusion_list(last_scan)

    def handle_state_changed(self, state):
        logger.info('State changed!')
        pass

    def reset(self):
        self.exclusion_list = []
        self.precursor_information = defaultdict(list)

    def _get_dda_scan_param(self, mz, intensity, isolation_width, mz_tol, rt_tol, collision_energy):
        dda_scan_params = ScanParameters()
        dda_scan_params.set(ScanParameters.MS_LEVEL, 2)

        # create precursor object, assume it's all singly charged
        precursor_charge = +1 if (self.environment.mass_spec.ionisation_mode == POSITIVE) else -1
        precursor = Precursor(precursor_mz=mz, precursor_intensity=intensity,
                              precursor_charge=precursor_charge, precursor_scan_id=self.last_ms1_scan.scan_id)
        dda_scan_params.set(ScanParameters.PRECURSOR_MZ, precursor)

        # set the full-width isolation width, in Da
        dda_scan_params.set(ScanParameters.ISOLATION_WIDTH, isolation_width)

        # define dynamic exclusion parameters
        dda_scan_params.set(ScanParameters.DYNAMIC_EXCLUSION_MZ_TOL, mz_tol)
        dda_scan_params.set(ScanParameters.DYNAMIC_EXCLUSION_RT_TOL, rt_tol)

        # define other fragmentation parameters
        dda_scan_params.set(ScanParameters.COLLISION_ENERGY, collision_energy)
        dda_scan_params.set(ScanParameters.POLARITY, self.environment.mass_spec.ionisation_mode)
        dda_scan_params.set(ScanParameters.FIRST_MASS, DEFAULT_MSN_SCAN_WINDOW[0])
        dda_scan_params.set(ScanParameters.LAST_MASS, DEFAULT_MSN_SCAN_WINDOW[1])
        return dda_scan_params

    def _add_precursor_info(self, scan):
        """
            Adds precursor ion information.
            If MS2 and above, and controller tells us which precursor ion the scan is coming from, store it
        :param param: a scan parameter object
        :param scan: the newly generated scan
        :return: None
        """
        precursor = scan.scan_params.get(ScanParameters.PRECURSOR_MZ)
        if scan.ms_level >= 2 and precursor is not None:
            isolation_windows = scan.scan_params.compute_isolation_windows()
            iso_min = isolation_windows[0][0][0] # half-width isolation window, in Da
            iso_max = isolation_windows[0][0][1] # half-width isolation window, in Da
            logger.debug('Time {:.6f} Isolated precursor ion {:.4f} at ({:.4f}, {:.4f})'.format(scan.rt,
                                                                                                precursor.precursor_mz,
                                                                                                iso_min,
                                                                                                iso_max))
            self.precursor_information[precursor].append(scan)

    def _manage_dynamic_exclusion_list(self, scan):
        """
        Manages dynamic exclusion list
        :param param: a scan parameter object
        :param scan: the newly generated scan
        :return: None
        """
        # FIXME: maybe not correct, see the step() method in IAPIMassSpec class
        if scan.scan_duration is not None:
            current_time = scan.rt + scan.scan_duration
        else:
            current_time = time.time() - self.environment.mass_spec.start_time

        precursor = scan.scan_params.get(ScanParameters.PRECURSOR_MZ)
        if scan.ms_level >= 2 and precursor is not None:
            # add dynamic exclusion item to the exclusion list to prevent the same precursor ion being fragmented
            # multiple times in the same mz and rt window
            # Note: at this point, fragmentation has occurred and time has been incremented! so the time when
            # items are checked for dynamic exclusion is the time when MS2 fragmentation occurs
            # TODO: we need to add a repeat count too, i.e. how many times we've seen a fragment peak before
            #  it gets excluded (now it's basically 1)
            mz = precursor.precursor_mz
            mz_tol = scan.scan_params.get(ScanParameters.DYNAMIC_EXCLUSION_MZ_TOL)
            rt_tol = scan.scan_params.get(ScanParameters.DYNAMIC_EXCLUSION_RT_TOL)
            mz_lower = mz * (1 - mz_tol / 1e6)
            mz_upper = mz * (1 + mz_tol / 1e6)
            rt_lower = current_time
            rt_upper = current_time + rt_tol
            x = ExclusionItem(from_mz=mz_lower, to_mz=mz_upper, from_rt=rt_lower, to_rt=rt_upper)
            logger.debug('Time {:.6f} Created dynamic exclusion window mz ({}-{}) rt ({}-{})'.format(
                current_time,
                x.from_mz, x.to_mz, x.from_rt, x.to_rt
            ))
            self.exclusion_list.append(x)

        # remove expired items from dynamic exclusion list
        self.exclusion_list = list(filter(lambda x: x.to_rt > current_time, self.exclusion_list))

    def _is_excluded(self, mz, rt):
        """
        Checks if a pair of (mz, rt) value is currently excluded by dynamic exclusion window
        :param mz: m/z value
        :param rt: RT value
        :return: True if excluded, False otherwise
        """
        # TODO: make this faster?
        for x in self.exclusion_list:
            exclude_mz = x.from_mz <= mz <= x.to_mz
            exclude_rt = x.from_rt <= rt <= x.to_rt
            if exclude_mz and exclude_rt:
                logger.debug(
                    'Excluded precursor ion mz {:.4f} rt {:.2f} because of {}'.format(mz, rt, x))
                return True
        return False


class HybridController(TopNController):
    def __init__(self, ionisation_mode, N, scan_param_changepoints,
                 isolation_widths, mz_tols, rt_tols, min_ms1_intensity,
                 n_purity_scans=None, purity_shift=None, purity_threshold=0, purity_randomise=True, purity_add_ms1=True):
        super().__init__(ionisation_mode, N, isolation_widths, mz_tols, rt_tols, min_ms1_intensity)

        # make sure these are stored as numpy arrays
        self.N = np.array(N)
        self.isolation_width = np.array(isolation_widths)  # the isolation window (in Dalton) to select a precursor ion
        self.mz_tols = np.array(mz_tols)  # the m/z window (ppm) to prevent the same precursor ion to be fragmented again
        self.rt_tols = np.array(rt_tols)  # the rt window to prevent the same precursor ion to be fragmented again
        if scan_param_changepoints is not None:
            self.scan_param_changepoints = np.array([0] + scan_param_changepoints)
        else:
            self.scan_param_changepoints = np.array([0])

        # purity stuff
        self.n_purity_scans = n_purity_scans
        self.purity_shift = purity_shift
        self.purity_threshold = purity_threshold
        self.purity_randomise = purity_randomise
        self.purity_add_ms1 = purity_add_ms1

        # make sure the input are all correct
        assert len(self.N) == len(self.scan_param_changepoints) == len(self.isolation_width) == len(
            self.mz_tols) == len(self.rt_tols)
        if self.purity_threshold != 0:
            assert all(self.n_purity_scans <= np.array(self.N))

    def _process_scan(self, scan, queue_size):
        # if there's a previous ms1 scan to process
        new_tasks = []
        if self.last_ms1_scan is not None and queue_size == 0:
            # check queue size because we want to schedule both ms1 and ms2 in the hybrid controller

            mzs = self.last_ms1_scan.mzs
            intensities = self.last_ms1_scan.intensities
            rt = self.last_ms1_scan.rt

            # set up current scan parameters
            current_N, current_rt_tol, idx = self._get_current_N_DEW(rt)
            current_isolation_width = self.isolation_width[idx]
            current_mz_tol = self.mz_tols[idx]

            # calculate purities
            purities = []
            for mz_idx in range(len(self.last_ms1_scan.mzs)):
                nearby_mzs_idx = np.where(
                    abs(self.last_ms1_scan.mzs - self.last_ms1_scan.mzs[mz_idx]) < current_isolation_width)
                if len(nearby_mzs_idx[0]) == 1:
                    purities.append(1)
                else:
                    total_intensity = sum(self.last_ms1_scan.intensities[nearby_mzs_idx])
                    purities.append(self.last_ms1_scan.intensities[mz_idx] / total_intensity)

            # loop over points in decreasing intensity
            fragmented_count = 0
            idx = np.argsort(intensities)[::-1]
            for i in idx:
                mz = mzs[i]
                intensity = intensities[i]
                purity = purities[i]

                # stopping criteria is after we've fragmented N ions or we found ion < min_intensity
                if fragmented_count >= current_N:
                    logger.debug('Top-%d ions have been selected' % (current_N))
                    break

                if intensity < self.min_ms1_intensity:
                    logger.debug(
                        'Minimum intensity threshold %f reached at %f, %d' % (
                            self.min_ms1_intensity, intensity, fragmented_count))
                    break

                # skip ion in the dynamic exclusion list of the mass spec
                if self._is_excluded(mz, rt):
                    continue

                if purity <= self.purity_threshold:
                    purity_shift_amounts = [self.purity_shift * (i - (self.n_purity_scans - 1) / 2) for i in
                                            range(self.n_purity_scans)]
                    if self.purity_randomise:
                        purity_randomise_idx = np.random.choice(self.n_purity_scans, self.n_purity_scans, replace=False)
                    else:
                        purity_randomise_idx = range(self.n_purity_scans)
                    for purity_idx in purity_randomise_idx:
                        # create a new ms2 scan parameter to be sent to the mass spec
                        dda_scan_params = self._get_dda_scan_param(mz + purity_shift_amounts[purity_idx], intensity,
                                                                   current_isolation_width,
                                                                   current_mz_tol, current_rt_tol, DEFAULT_COLLISION_ENERGY)
                        new_tasks.append(dda_scan_params)
                        if self.purity_add_ms1 and purity_idx != purity_randomise_idx[-1]:
                            ms1_scan_params = self.environment.get_default_scan_params()
                            new_tasks.append(ms1_scan_params)
                        fragmented_count += 1
                else:
                    # create a new ms2 scan parameter to be sent to the mass spec
                    dda_scan_params = self._get_dda_scan_param(mz, intensity, current_isolation_width,
                                                               current_mz_tol, current_rt_tol, DEFAULT_COLLISION_ENERGY)
                    new_tasks.append(dda_scan_params)
                    fragmented_count += 1

            # set this ms1 scan as has been processed
            self.last_ms1_scan = None
        return new_tasks

    def update_state_after_scan(self, last_scan):
        super().update_state_after_scan(last_scan)

    def handle_state_changed(self, state):
        pass

    def reset(self):
        super().reset()

    def _get_current_N_DEW(self, time):
        idx = np.nonzero(self.scan_param_changepoints <= time)[0][-1]
        current_N = self.N[idx]
        current_rt_tol = self.rt_tols[idx]
        return current_N, current_rt_tol, idx


class RoiController(TopNController):
    """
    An ROI based controller with multiple options
    """

    def __init__(self, ionisation_mode, isolation_width, mz_tol, min_ms1_intensity, min_roi_intensity,
                 min_roi_length, score_method, N=None, rt_tol=10, score_params=None, min_roi_length_for_fragmentation=1):
        super().__init__(ionisation_mode, N, isolation_width, mz_tol, rt_tol, min_ms1_intensity)

        # ROI stuff
        self.min_roi_intensity = min_roi_intensity
        self.mz_units = 'ppm'
        self.min_roi_length = min_roi_length

        # Score stuff
        self.score_params = score_params
        self.score_method = score_method
        self.min_roi_length_for_fragmentation = min_roi_length_for_fragmentation

        # Create ROI
        self.live_roi = []
        self.dead_roi = []
        self.junk_roi = []
        self.live_roi_fragmented = []
        self.live_roi_last_rt = []  # last fragmentation time of ROI

    def handle_acquisition_open(self):
        logger.info('Acquisition open')

    def handle_acquisition_closing(self):
        logger.info('Acquisition closing')

    def _process_scan(self, scan, queue_size):
        # keep growing ROIs if we encounter a new ms1 scan
        self._update_roi(scan)

        # if there's a previous ms1 scan to process
        new_tasks = []
        if self.last_ms1_scan is not None:
            self.current_roi_mzs = [roi.get_mean_mz() for roi in self.live_roi]
            self.current_roi_intensities = [roi.get_max_intensity() for roi in self.live_roi]
            self.current_roi_length = np.array([roi.n for roi in self.live_roi])
            rt = self.last_ms1_scan.rt

            # loop over points in decreasing score
            scores = self._get_scores(self.score_method, self.score_params)
            idx = np.argsort(scores)[::-1]
            for i in idx:
                mz = self.current_roi_mzs[i]
                intensity = self.current_roi_intensities[i]

                # stopping criteria is done based on the scores
                if scores[i] <= 0:
                    logger.debug('Time %f Top-%d ions have been selected' % (rt, self.N))
                    break

                # updated fragmented list and times
                self.live_roi_fragmented[i] = True
                self.live_roi_last_rt[i] = rt  # TODO: May want to update this to use the time of the MS2 scan

                # create a new ms2 scan parameter to be sent to the mass spec
                dda_scan_params = self._get_dda_scan_param(mz, intensity, self.isolation_width,
                                                           self.mz_tols, self.rt_tols, DEFAULT_COLLISION_ENERGY)
                new_tasks.append(dda_scan_params)

                # set this ms1 scan as has been processed
            self.last_ms1_scan = None
        return new_tasks

    def update_state_after_scan(self, last_scan):
        # add precursor info based on the current scan produced
        # NOT doing the dynamic exclusion window thing
        self._add_precursor_info(last_scan)

    def handle_state_changed(self, state):
        pass

    def reset(self):
        super().reset()
        self.live_roi = []
        self.dead_roi = []
        self.junk_roi = []
        self.live_roi_fragmented = []
        self.live_roi_last_rt = []  # last fragmentation time of ROI

    def _update_roi(self, new_scan):
        if new_scan.ms_level == 1:
            order = np.argsort(self.live_roi)
            self.live_roi.sort()
            self.live_roi_fragmented = np.array(self.live_roi_fragmented)[order].tolist()
            self.live_roi_last_rt = np.array(self.live_roi_last_rt)[order].tolist()
            current_ms1_scan_rt = new_scan.rt
            not_grew = set(self.live_roi)
            for idx in range(len(new_scan.intensities)):
                intensity = new_scan.intensities[idx]
                mz = new_scan.mzs[idx]
                if intensity >= self.min_roi_intensity:
                    match_roi = match(Roi(mz, 0, 0), self.live_roi, self.mz_tols, mz_units=self.mz_units)
                    if match_roi:
                        match_roi.add(mz, current_ms1_scan_rt, intensity)
                        if match_roi in not_grew:
                            not_grew.remove(match_roi)
                    else:
                        new_roi = Roi(mz, current_ms1_scan_rt, intensity)
                        bisect.insort_right(self.live_roi, new_roi)
                        self.live_roi_fragmented.insert(self.live_roi.index(new_roi), False)
                        self.live_roi_last_rt.insert(self.live_roi.index(new_roi), None)

            for roi in not_grew:
                if roi.n >= self.min_roi_length:
                    self.dead_roi.append(roi)
                else:
                    self.junk_roi.append(roi)
                pos = self.live_roi.index(roi)
                del self.live_roi[pos]
                del self.live_roi_fragmented[pos]
                del self.live_roi_last_rt[pos]

    def _get_scores(self, score_method, params):
        if score_method == "Top N":
            scores = np.log(self.current_roi_intensities)  # log intensities
            scores *= (np.log(self.current_roi_intensities) > np.log(self.min_ms1_intensity))  # intensity filter
            time_filter = (1 - np.array(self.live_roi_fragmented).astype(int))
            time_filter[time_filter==0] = ((self.last_ms1_scan.rt - np.array(self.live_roi_last_rt)[time_filter==0]) > self.rt_tols)
            scores *= time_filter
            scores *= (self.current_roi_length >= self.min_roi_length_for_fragmentation)
            if len(scores) > self.N:  # number of fragmentation events filter
                scores[scores.argsort()[:(len(scores) - self.N)]] = 0
        elif score_method == "Regression Top N":
            # uses regresion methods instead of indicator functions
            scores = np.log(self.current_roi_intensities)  # log intensities
            # TODO: some other methods here
            # thinking of stores models in a dictionary maybe
            # then can just select the right one - potentially allowing us to just fit one once and save
        return scores


########################################################################################################################
# DIA Controllers
########################################################################################################################

class TreeController(Controller):
    def __init__(self, dia_design, window_type, kaufmann_design, extra_bins, num_windows=None):
        super().__init__()
        self.dia_design = dia_design
        self.window_type = window_type
        self.kaufmann_design = kaufmann_design
        self.extra_bins = extra_bins
        self.num_windows = num_windows

    def handle_acquisition_open(self):
        logger.info('Acquisition open')

    def handle_acquisition_closing(self):
        logger.info('Acquisition closing')

    def _process_scan(self, scan, queue_size):
        # if there's a previous ms1 scan to process
        new_tasks = []
        if self.last_ms1_scan is not None:

            rt = self.last_ms1_scan.rt

            # then get the last ms1 scan, select bin walls and create scan locations
            mzs = self.last_ms1_scan.mzs
            default_range = [DEFAULT_MS1_SCAN_WINDOW]  # TODO: this should maybe come from somewhere else?
            locations = DiaWindows(mzs, default_range, self.dia_design, self.window_type, self.kaufmann_design,
                                   self.extra_bins, self.num_windows).locations
            logger.debug('Window locations {}'.format(locations))
            for i in range(len(locations)):  # define isolation window around the selected precursor ions
                isolation_windows = locations[i]
                dda_scan_params = ScanParameters()
                dda_scan_params.set(ScanParameters.MS_LEVEL, 2)
                dda_scan_params.set(ScanParameters.ISOLATION_WINDOWS, isolation_windows)
                new_tasks.append(dda_scan_params)  # push this dda scan to the mass spec queue

            # set this ms1 scan as has been processed
            self.last_ms1_scan = None
        return new_tasks


class TestController(TopNController):
    def __init__(self, ionisation_mode, N, isolation_width, mz_tol, rt_tol, min_ms1_intensity):
        self.extra_scans_done = False
        super().__init__(ionisation_mode, N, isolation_width, mz_tol, rt_tol, min_ms1_intensity)

    def _process_scan(self, scan):
        # if there's a previous ms1 scan to process
        new_tasks = []
        rt2scan = 400  # TODO: Change as required
        if self.last_ms1_scan is not None and self.extra_scans_done is False:
            if self.last_ms1_scan.rt > rt2scan:
                mzs = np.array([100, 200, 300, 400])
                intensities = np.array([1, 2, 3, 4])

                # loop over points in decreasing intensity
                fragmented_count = 0
                idx = np.argsort(intensities)[::-1]
                for i in idx:
                    mz = mzs[i]
                    intensity = intensities[i]

                    # create a new ms2 scan parameter to be sent to the mass spec
                    dda_scan_params = self._get_dda_scan_param(mz, intensity, self.isolation_width,
                                                               self.mz_tols, self.rt_tols, DEFAULT_COLLISION_ENERGY)
                    new_tasks.append(dda_scan_params)
                    fragmented_count += 1

                # set this ms1 scan as has been processed
                self.last_ms1_scan = None
                self.extra_scans_done = True
        return new_tasks
