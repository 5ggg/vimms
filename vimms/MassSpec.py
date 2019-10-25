import math
from collections import defaultdict

import numpy as np
import trio
from events import Events

from vimms.Common import LoggerMixin, adduct_transformation


class Peak(object):
    """
    A class to represent an empirical or sampled scan-level peak object
    """

    def __init__(self, mz, rt, intensity, ms_level):
        """
        Creates a peak object
        :param mz: mass-to-charge value
        :param rt: retention time value
        :param intensity: intensity value
        :param ms_level: MS level
        """
        self.mz = mz
        self.rt = rt
        self.intensity = intensity
        self.ms_level = ms_level

    def __repr__(self):
        return 'Peak mz=%.4f rt=%.2f intensity=%.2f ms_level=%d' % (self.mz, self.rt, self.intensity, self.ms_level)

    def __eq__(self, other):
        if not isinstance(other, Peak):
            # don't attempt to compare against unrelated types
            return NotImplemented

        return math.isclose(self.mz, other.mz) and \
               math.isclose(self.rt, other.rt) and \
               math.isclose(self.intensity, other.intensity) and \
               self.ms_level == other.ms_level


class Scan(object):
    """
    A class to store scan information
    """

    def __init__(self, scan_id, mzs, intensities, ms_level, rt, scan_duration=None, isolation_windows=None,
                 parent=None, param=None):
        """
        Creates a scan
        :param scan_id: current scan id
        :param mzs: an array of mz values
        :param intensities: an array of intensity values
        :param ms_level: the ms level of this scan
        :param rt: the retention time of this scan
        :param scan_duration: how long this scan takes, if known.
        :param isolation_windows: the window to isolate precursor peak, if known
        :param parent: parent precursor peak, if known
        :param param: scan parameters, if known
        """
        assert len(mzs) == len(intensities)
        self.scan_id = scan_id

        # ensure that mzs and intensites are sorted by their mz values
        p = mzs.argsort()
        self.mzs = mzs[p]
        self.intensities = intensities[p]

        self.ms_level = ms_level
        self.rt = rt
        self.num_peaks = len(mzs)

        self.scan_duration = scan_duration
        self.isolation_windows = isolation_windows
        self.parent = parent
        self.param = param

    def __repr__(self):
        return 'Scan %d num_peaks=%d rt=%.2f ms_level=%d' % (self.scan_id, self.num_peaks, self.rt, self.ms_level)


class ScanParameters(object):
    """
    A class to store parameters used to instruct the mass spec how to generate a scan.
    This object is usually created by the controllers.
    """

    # possible scan parameter names
    MS_LEVEL = 'ms_level'
    ISOLATION_WINDOWS = 'isolation_windows'
    PRECURSOR = 'precursor'
    DYNAMIC_EXCLUSION_MZ_TOL = 'mz_tol'
    DYNAMIC_EXCLUSION_RT_TOL = 'rt_tol'
    TIME = 'time'
    N = 'N'

    def __init__(self):
        """
        Creates a scan parameter object
        """
        self.params = {}

    def set(self, key, value):
        """
        Sets scan parameter value
        :param key: a scan parameter name
        :param value: a scan parameter value
        :return:
        """
        self.params[key] = value

    def get(self, key):
        """
        Gets scan parameter value
        :param key:
        :return:
        """
        if key in self.params:
            return self.params[key]
        else:
            return None

    def __repr__(self):
        return 'ScanParameters %s' % (self.params)


class FragmentationEvent(object):
    """
    A class to store fragmentation events. Mostly used for benchmarking purpose.
    """

    def __init__(self, chem, query_rt, ms_level, peaks, scan_id):
        """
        Creates a fragmentation event
        :param chem: the chemical that were fragmented
        :param query_rt: the time when fragmentation occurs
        :param ms_level: MS level of fragmentation
        :param peaks: the set of peaks produced during the fragmentation event
        :param scan_id: the scan id linked to this fragmentation event
        """
        self.chem = chem
        self.query_rt = query_rt
        self.ms_level = ms_level
        self.peaks = peaks
        self.scan_id = scan_id

    def __repr__(self):
        return 'MS%d FragmentationEvent for %s at %f' % (self.ms_level, self.chem, self.query_rt)


class ExclusionItem(object):
    """
    A class to store the item to exclude when computing dynamic exclusion window
    """

    def __init__(self, from_mz, to_mz, from_rt, to_rt):
        """
        Creates a dynamic exclusion item
        :param from_mz: m/z lower bounding box
        :param to_mz: m/z upper bounding box
        :param from_rt: RT lower bounding box
        :param to_rt: RT upper bounding box
        """
        self.from_mz = from_mz
        self.to_mz = to_mz
        self.from_rt = from_rt
        self.to_rt = to_rt


class IndependentMassSpectrometer(LoggerMixin):
    """
    A class that represents (synchronous) mass spectrometry process.
    Independent here refers to how the intensity of each peak in a scan is independent of each other
    i.e. there's no ion supression effect.
    """
    MS_SCAN_ARRIVED = 'MsScanArrived'
    ACQUISITION_STREAM_OPENING = 'AcquisitionStreamOpening'
    ACQUISITION_STREAM_CLOSING = 'AcquisitionStreamClosing'

    def __init__(self, ionisation_mode, chemicals, peak_sampler, add_noise=False):
        """
        Creates a mass spec object.
        :param ionisation_mode: POSITIVE or NEGATIVE
        :param chemicals: a list of Chemical objects in the dataset
        :param peak_sampler: an instance of DataGenerator.PeakSampler object
        :param add_noise: a flag to indicate whether to add noise
        :param use_exclusion_list: a flag to indicate whether to perform dynamic exclusion
        """

        # current scan index and internal time
        self.idx = 0
        self.time = 0

        # current task queue
        self.processing_queue = []
        self.repeating_scan_parameters = None
        self.environment = None

        # the events here follows IAPI events
        self.events = Events((self.MS_SCAN_ARRIVED, self.ACQUISITION_STREAM_OPENING, self.ACQUISITION_STREAM_CLOSING,))
        self.event_dict = {
            self.MS_SCAN_ARRIVED: self.events.MsScanArrived,
            self.ACQUISITION_STREAM_OPENING: self.events.AcquisitionStreamOpening,
            self.ACQUISITION_STREAM_CLOSING: self.events.AcquisitionStreamClosing
        }

        # the list of all chemicals in the dataset
        self.chemicals = chemicals
        self.ionisation_mode = ionisation_mode  # currently unused

        # stores the chromatograms start and end rt for quick retrieval
        chem_rts = np.array([chem.rt for chem in self.chemicals])
        self.chrom_min_rts = np.array([chem.chromatogram.min_rt for chem in self.chemicals]) + chem_rts
        self.chrom_max_rts = np.array([chem.chromatogram.max_rt for chem in self.chemicals]) + chem_rts

        # here's where we store all the stuff to sample from
        self.peak_sampler = peak_sampler

        # required to sample for different scan durations based on (N, DEW) in the hybrid controller
        self.current_N = 0
        self.current_DEW = 0

        self.add_noise = add_noise  # whether to add noise to the generated fragment peaks
        self.fragmentation_events = []  # which chemicals produce which peaks

    ####################################################################################################################
    # Public methods
    ####################################################################################################################

    def step(self):
        """
        Performs one step of a mass spectrometry process
        :return:
        """

        # get scan param from the processing queue and do one scan
        param = self._get_param()
        scan = self._get_scan(self.time, param)

        # notify the controller that a new scan has been generated
        # at this point, the MS_SCAN_ARRIVED event handler in the controller is called
        # and the processing queue will be updated with new sets of scan parameters to do
        self.fire_event(self.MS_SCAN_ARRIVED, scan)

        # sample scan duration and increase internal time
        current_level = scan.ms_level
        current_N = self.current_N
        current_DEW = self.current_DEW
        try:
            next_scan_param = self.get_processing_queue()[0]
        except IndexError:
            next_scan_param = None

        current_scan_duration = self._increase_time(current_level, current_N, current_DEW,
                                                    next_scan_param)
        scan.scan_duration = current_scan_duration

        # stores the updated value of N and DEW
        self._store_next_N_DEW(next_scan_param)
        return scan

    def get_processing_queue(self):
        """
        Returns the current processing queue
        :return:
        """
        return self.processing_queue

    def add_to_processing_queue(self, param):
        """
        Adds a new scan parameters to the processing queue of scan parameters. Usually done by the controllers.
        :param param: the scan parameters to add
        :return: None
        """
        self.processing_queue.append(param)

    def disable_repeating_scan(self):
        """
        Disable repeating scan
        :return: None
        """
        self.set_repeating_scan(None)

    def set_repeating_scan(self, params):
        """
        Sets the parameters for the default repeating scans that will be done when the processing queue is empty.
        :param params:
        :return:
        """
        self.repeating_scan_parameters = params

    def reset(self):
        """
        Resets the mass spec state so we can reuse it again
        :return: None
        """
        for key in self.event_dict:  # clear event handlers
            self.clear(key)
        self.time = 0
        self.idx = 0
        self.processing_queue = []
        self.repeating_scan_parameters = None
        self.current_N = 0
        self.current_DEW = 0
        self.fragmentation_events = []

    def fire_event(self, event_name, arg=None):
        """
        Simulates sending an event
        :param event_name: the event name
        :param arg: the event parameter
        :return: None
        """
        if event_name not in self.event_dict:
            raise ValueError('Unknown event name')

        e = self.event_dict[event_name]
        if event_name == self.MS_SCAN_ARRIVED: # if it's a scan event, then pass the scan to the controller
            scan = arg
            self.environment.add_scan(scan)
        else:
            # pretend to fire the event
            # actually here we just runs the event handler method directly
            if arg is not None:
                e(arg)
            else:
                e()

    def register(self, event_name, handler):
        """
        Register event handler
        :param event_name: the event name
        :param handler: the event handler
        :return: None
        """
        if event_name not in self.event_dict:
            raise ValueError('Unknown event name')
        e = self.event_dict[event_name]
        e += handler  # register a new event handler for e

    def clear(self, event_name):
        """
        Clears event handler for a given event name
        :param event_name: the event name
        :return: None
        """
        if event_name not in self.event_dict:
            raise ValueError('Unknown event name')
        e = self.event_dict[event_name]
        e.targets = []

    ####################################################################################################################
    # Private methods
    ####################################################################################################################

    def _get_param(self):
        """
        Retrieves a new set of scan parameters from the processing queue
        :return: A new set of scan parameters from the queue if available, otherwise it returns the default scan params.
        """
        # if the processing queue is empty, then just do the repeating scan
        if len(self.processing_queue) == 0:
            param = self.repeating_scan_parameters
        else:
            # otherwise pop the parameter for the next scan from the queue
            param = self.processing_queue.pop(0)
        return param

    def _increase_time(self, current_level, current_N, current_DEW, next_scan_param):
        # look into the queue, find out what the next scan ms_level is, and compute the scan duration
        # only applicable for simulated mass spec, since the real mass spec can generate its own scan duration.
        self.idx += 1
        if next_scan_param is None:  # if queue is empty, the next one is an MS1 scan by default
            next_level = 1
        else:
            next_level = next_scan_param.get(ScanParameters.MS_LEVEL)

        # sample current scan duration based on current_DEW, current_N, current_level and next_level
        current_scan_duration = self._sample_scan_duration(current_DEW, current_N,
                                                           current_level, next_level)

        self.time += current_scan_duration
        self.logger.info('Time %f Len(queue)=%d' % (self.time, len(self.processing_queue)))
        return current_scan_duration

    def _sample_scan_duration(self, current_DEW, current_N, current_level, next_level):
        # get scan duration based on current and next level
        if current_level == 1 and next_level == 1:
            # special case: for the transition (1, 1), we can try to get the times for the
            # fullscan data (N=0, DEW=0) if it's stored
            try:
                current_scan_duration = self.peak_sampler.scan_durations(current_level, next_level, 1, N=0, DEW=0)
            except KeyError:  ## ooops not found
                current_scan_duration = self.peak_sampler.scan_durations(current_level, next_level, 1,
                                                                         N=current_N, DEW=current_DEW)
        else:  # for (1, 2), (2, 1) and (2, 2)
            current_scan_duration = self.peak_sampler.scan_durations(current_level, next_level, 1,
                                                                     N=current_N, DEW=current_DEW)
        current_scan_duration = current_scan_duration.flatten()[0]
        return current_scan_duration

    def _store_next_N_DEW(self, next_scan_param):
        """
        Stores the N and DEW parameter values for the next scan params
        :param next_scan_param: A new set of scan parameters
        :return: None
        """
        if next_scan_param is not None:
            # Only the hybrid controller sends these N and DEW parameters. For other controllers they will be None
            next_N = next_scan_param.get(ScanParameters.N)
            next_DEW = next_scan_param.get(ScanParameters.DYNAMIC_EXCLUSION_RT_TOL)
        else:
            next_N = None
            next_DEW = None

        # keep track of the N and DEW values for the next scan if they have been changed by the Hybrid Controller
        if next_N is not None:
            self.current_N = next_N
        if next_DEW is not None:
            self.current_DEW = next_DEW

    ####################################################################################################################
    # Scan generation methods
    ####################################################################################################################

    def _get_scan(self, scan_time, param):
        """
        Constructs a scan at a particular timepoint
        :param time: the timepoint
        :return: a mass spectrometry scan at that time
        """
        scan_mzs = []  # all the mzs values in this scan
        scan_intensities = []  # all the intensity values in this scan
        ms_level = param.get(ScanParameters.MS_LEVEL)
        isolation_windows = param.get(ScanParameters.ISOLATION_WINDOWS)
        scan_id = self.idx

        # for all chemicals that come out from the column coupled to the mass spec
        idx = self._get_chem_indices(scan_time)
        for i in idx:
            chemical = self.chemicals[i]

            # mzs is a list of (mz, intensity) for the different adduct/isotopes combinations of a chemical
            if self.add_noise:
                mzs = self._get_all_mz_peaks_noisy(chemical, scan_time, ms_level, isolation_windows)
            else:
                mzs = self._get_all_mz_peaks(chemical, scan_time, ms_level, isolation_windows)

            peaks = []
            if mzs is not None:
                chem_mzs = []
                chem_intensities = []
                for peak_mz, peak_intensity in mzs:
                    if peak_intensity > 0:
                        chem_mzs.append(peak_mz)
                        chem_intensities.append(peak_intensity)
                        p = Peak(peak_mz, scan_time, peak_intensity, ms_level)
                        peaks.append(p)

                scan_mzs.extend(chem_mzs)
                scan_intensities.extend(chem_intensities)

            # for benchmarking purpose
            if len(peaks) > 0:
                frag = FragmentationEvent(chemical, scan_time, ms_level, peaks, scan_id)
                self.fragmentation_events.append(frag)

        scan_mzs = np.array(scan_mzs)
        scan_intensities = np.array(scan_intensities)

        # Note: at this point, the scan duration is not set yet because we don't know what the next scan is going to be
        # We will set it later in the get_next_scan() method after we've notified the controller that this scan is produced.
        return Scan(scan_id, scan_mzs, scan_intensities, ms_level, scan_time,
                    scan_duration=None, isolation_windows=isolation_windows, param=param)

    def _get_chem_indices(self, query_rt):
        rtmin_check = self.chrom_min_rts <= query_rt
        rtmax_check = query_rt <= self.chrom_max_rts
        idx = np.nonzero(rtmin_check & rtmax_check)[0]
        return idx

    def _get_all_mz_peaks_noisy(self, chemical, query_rt, ms_level, isolation_windows):
        mz_peaks = self._get_all_mz_peaks(chemical, query_rt, ms_level, isolation_windows)
        if self.peak_sampler is None:
            return mz_peaks
        if mz_peaks is not None:
            noisy_mz_peaks = [(mz_peaks[i][0], self.peak_sampler.get_msn_noisy_intensity(mz_peaks[i][1], ms_level)) for
                              i in range(len(mz_peaks))]
        else:
            noisy_mz_peaks = []
        noisy_mz_peaks += self.peak_sampler.get_noise_sample()
        return noisy_mz_peaks

    def _get_all_mz_peaks(self, chemical, query_rt, ms_level, isolation_windows):
        if not self._rt_match(chemical, query_rt):
            return None
        mz_peaks = []
        for which_isotope in range(len(chemical.isotopes)):
            for which_adduct in range(len(self._get_adducts(chemical))):
                mz_peaks.extend(
                    self._get_mz_peaks(chemical, query_rt, ms_level, isolation_windows, which_isotope, which_adduct))
        if mz_peaks == []:
            return None
        else:
            return mz_peaks

    def _get_mz_peaks(self, chemical, query_rt, ms_level, isolation_windows, which_isotope, which_adduct):
        # EXAMPLE OF USE OF DEFINITION: if we wants to do an ms2 scan on a chemical. we would first have ms_level=2 and the chemicals
        # ms_level =1. So we would go to the "else". We then check the ms1 window matched. It then would loop through
        # the children who have ms_level = 2. So we then go to second elif and return the mz and intensity of each ms2 fragment
        mz_peaks = []
        if ms_level == 1 and chemical.ms_level == 1:  # fragment ms1 peaks
            # returns ms1 peaks if chemical is has ms_level = 1 and scan is an ms1 scan
            if not (which_isotope > 0 and which_adduct > 0):
                # rechecks isolations window if not monoisotopic and "M + H" adduct
                if self._isolation_match(chemical, query_rt, isolation_windows[0], which_isotope, which_adduct):
                    intensity = self._get_intensity(chemical, query_rt, which_isotope, which_adduct)
                    mz = self._get_mz(chemical, query_rt, which_isotope, which_adduct)
                    mz_peaks.extend([(mz, intensity)])
        elif ms_level == chemical.ms_level:
            # returns ms2 fragments if chemical and scan are both ms2, 
            # returns ms3 fragments if chemical and scan are both ms3, etc, etc
            intensity = self._get_intensity(chemical, query_rt, which_isotope, which_adduct)
            mz = self._get_mz(chemical, query_rt, which_isotope, which_adduct)
            return [(mz, intensity)]
            # TODO: Potential improve how the isotope spectra are generated
        else:
            # check isolation window for ms2+ scans, queries children if isolation windows ok
            if self._isolation_match(chemical, query_rt, isolation_windows[chemical.ms_level - 1], which_isotope,
                                     which_adduct) and chemical.children is not None:
                for i in range(len(chemical.children)):
                    mz_peaks.extend(self._get_mz_peaks(chemical.children[i], query_rt, ms_level, isolation_windows,
                                                       which_isotope, which_adduct))
            else:
                return []
        return mz_peaks

    def _get_adducts(self, chemical):
        if chemical.ms_level == 1:
            return chemical.adducts
        else:
            return self._get_adducts(chemical.parent)

    def _rt_match(self, chemical, query_rt):
        return chemical.ms_level != 1 or chemical.chromatogram._rt_match(query_rt - chemical.rt)

    def _get_intensity(self, chemical, query_rt, which_isotope, which_adduct):
        if chemical.ms_level == 1:
            intensity = chemical.isotopes[which_isotope][1] * self._get_adducts(chemical)[which_adduct][1] * \
                        chemical.max_intensity
            return intensity * chemical.chromatogram.get_relative_intensity(query_rt - chemical.rt)
        else:
            return self._get_intensity(chemical.parent, query_rt, which_isotope, which_adduct) * \
                   chemical.parent_mass_prop * chemical.prop_ms2_mass

    def _get_mz(self, chemical, query_rt, which_isotope, which_adduct):
        if chemical.ms_level == 1:
            return (adduct_transformation(chemical.isotopes[which_isotope][0],
                                          self._get_adducts(chemical)[which_adduct][0]) +
                    chemical.chromatogram.get_relative_mz(query_rt - chemical.rt))
        else:
            ms1_parent = chemical
            while ms1_parent.ms_level != 1:
                ms1_parent = chemical.parent
            isotope_transformation = ms1_parent.isotopes[which_isotope][0] - ms1_parent.isotopes[0][0]
            # TODO: Needs improving
            return (adduct_transformation(chemical.isotopes[0][0],
                                          self._get_adducts(chemical)[which_adduct][0]) + isotope_transformation)

    def _isolation_match(self, chemical, query_rt, isolation_windows, which_isotope, which_adduct):
        # assumes list is formated like:
        # [(min_1,max_1),(min_2,max_2),...]
        for window in isolation_windows:
            if window[0] < self._get_mz(chemical, query_rt, which_isotope, which_adduct) <= window[1]:
                return True
        return False


class AsyncMassSpectrometer(IndependentMassSpectrometer):

    def __init__(self, ionisation_mode, chemicals, peak_sampler, spectra_send_channel, task_receive_channel,
                 add_noise=False, dynamic_exclusion=True):
        super().__init__(ionisation_mode, chemicals, peak_sampler, add_noise, dynamic_exclusion)
        self.spectra_send_channel = spectra_send_channel
        self.task_receive_channel = task_receive_channel

    def _get_param(self):
        # get current task
        # check if there's a new task from the controller, if yes then add to task queue
        try:
            received = self.task_receive_channel.receive_nowait()
            received_tasks = received['tasks']
            received_scan = received['scan']
            print('mass_spec received %d new tasks for %s' % (len(received_tasks), received_scan))
            self.processing_queue.extend(received_tasks)
        except trio.WouldBlock:  # no new task
            pass

        # if the processing queue is empty, then just do the repeating scan
        if len(self.processing_queue) == 0:
            param = self.repeating_scan_parameters
        else:
            # otherwise pop the parameter for the next scan from the queue
            param = self.processing_queue.pop(0)
        return param

    async def fire_event(self, event_name, arg=None):
        if event_name not in self.event_dict:
            raise ValueError('Unknown event name')

        if event_name == self.MS_SCAN_ARRIVED:  # add new scan to spectra send channel
            assert arg is not None
            scan = arg
            await self.spectra_send_channel.send(scan)
            print('mass_spec sent', scan)
        else:
            # pretend to fire the event
            # actually here we just runs the event handler method directly
            e = self.event_dict[event_name]
            if arg is not None:
                e(arg)
            else:
                e()