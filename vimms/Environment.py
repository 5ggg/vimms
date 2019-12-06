import time
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from vimms.Common import DEFAULT_MS1_SCAN_WINDOW, POSITIVE
from vimms.Controller import TopNController, HybridController
from vimms.MassSpec import ScanParameters, IndependentMassSpectrometer
from vimms.MzmlWriter import MzmlWriter


class Environment(object):
    def __init__(self, mass_spec, controller, min_time, max_time, progress_bar=True, out_dir=None, out_file=None):
        """
        Initialises a synchronous environment to run the mass spec and controller
        :param mass_spec: An instance of Mass Spec object
        :param controller: An instance of Controller object
        :param min_time: start time
        :param max_time: end time
        :param progress_bar: True if a progress bar is to be shown
        """
        self.scan_channel = []
        self.task_channel = []
        self.mass_spec = mass_spec
        self.controller = controller
        self.min_time = min_time
        self.max_time = max_time
        self.progress_bar = progress_bar
        self.default_scan_params = ScanParameters()
        self.default_scan_params.set(ScanParameters.MS_LEVEL, 1)
        self.default_scan_params.set(ScanParameters.ISOLATION_WINDOWS, [[DEFAULT_MS1_SCAN_WINDOW]])
        self.out_dir = out_dir
        self.out_file = out_file

    def run(self):
        """
        Runs the mass spec and controller
        :return: None
        """
        # reset mass spec and set some initial values for each run
        self.mass_spec.reset()
        self.controller.reset()
        self._set_initial_values()

        # register event handlers from the controller
        self.mass_spec.register_event(IndependentMassSpectrometer.MS_SCAN_ARRIVED, self.add_scan)
        self.mass_spec.register_event(IndependentMassSpectrometer.ACQUISITION_STREAM_OPENING,
                                      self.controller.handle_acquisition_open)
        self.mass_spec.register_event(IndependentMassSpectrometer.ACQUISITION_STREAM_CLOSING,
                                      self.controller.handle_acquisition_closing)
        self.mass_spec.register_event(IndependentMassSpectrometer.STATE_CHANGED,
                                      self.controller.handle_state_changed)

        # run mass spec
        bar = tqdm(total=self.max_time - self.min_time, initial=0) if self.progress_bar else None
        self.mass_spec.fire_event(IndependentMassSpectrometer.ACQUISITION_STREAM_OPENING)
        try:
            # perform one step of mass spec up to max_time
            while self.mass_spec.time < self.max_time:
                # controller._process_scan() is called here immediately when a scan is produced within a step
                scan = self.mass_spec.step()
                # update controller internal states AFTER a scan has been generated and handled
                self.controller.update_state_after_scan(scan)
                # increment progress bar
                self._update_progress_bar(bar, scan)
        except Exception as e:
            raise e
        finally:
            self.mass_spec.close()
            self.close_progress_bar(bar)
        self.write_mzML(self.out_dir, self.out_file)

    def _update_progress_bar(self, pbar, scan):
        """
        Updates progress bar based on elapsed time
        :param elapsed: Elapsed time to increment the progress bar
        :param pbar: progress bar object
        :param scan: the newly generated scan
        :return: None
        """
        if pbar is not None:
            N, DEW = self._get_N_DEW(self.mass_spec.time)
            if N is not None and DEW is not None:
                msg = '(%.3fs) ms_level=%d N=%d DEW=%d' % (self.mass_spec.time, scan.ms_level, N, DEW)
            else:
                msg = '(%.3fs) ms_level=%d' % (self.mass_spec.time, scan.ms_level)
            if pbar.n + scan.scan_duration < pbar.total:
                pbar.update(scan.scan_duration)
            pbar.set_description(msg)

    def close_progress_bar(self, bar):
        if bar is not None:
            try:
                bar.close()
            except Exception as e:
                logger.warning('Failed to close progress bar: %s' % str(e))
                pass

    def add_scan(self, scan):
        """
        Adds a newly generated scan. In this case, immediately we process it in the controller without saving the scan.
        :param scan: A newly generated scan
        :return: None
        """
        self.scan_channel.append(scan)
        scan = self.scan_channel.pop(0)
        tasks = self.controller.handle_scan(scan)
        self.add_tasks(tasks)

    def add_tasks(self, scan_params):
        """
        Stores new tasks from the controller. In this case, immediately we pass the new tasks to the mass spec.
        :param scan_params: new tasks
        :return: None
        """
        self.task_channel.extend(scan_params)
        while len(self.task_channel) > 0:
            new_task = self.task_channel.pop(0)
            self.mass_spec.add_to_processing_queue(new_task)

    def write_mzML(self, out_dir, out_file):
        """
        Writes mzML to output file
        :param out_dir: output directory
        :param out_file: output filename
        :return: None
        """
        if out_file is None:  # if no filename provided, just quits
            return
        else:
            if out_dir is None:  # no out_dir, use only out_file
                mzml_filename = Path(out_file)
            else:  # both our_dir and out_file are provided
                mzml_filename = Path(out_dir, out_file)

        logger.debug('Writing mzML file to %s' % mzml_filename)
        try:
            precursor_information = self.controller.precursor_information
        except AttributeError:
            precursor_information = None
        writer = MzmlWriter('my_analysis', self.controller.scans, precursor_information)
        writer.write_mzML(mzml_filename)
        logger.debug('mzML file successfully written!')

    def _set_initial_values(self):
        """
        Sets initial environment, mass spec start time, default scan parameters and other values
        :return: None
        """
        self.controller.set_environment(self)
        self.mass_spec.set_environment(self)
        self.mass_spec.time = self.min_time

        N, DEW = self._get_N_DEW(self.mass_spec.time)
        if N is not None:
            self.mass_spec.current_N = N
        if DEW is not None:
            self.mass_spec.current_DEW = DEW

    def get_default_scan_params(self):
        """
        Gets the default method scan parameters. Now it's set to do MS1 scan only.
        :return: the default scan parameters
        """
        return self.default_scan_params

    def _get_N_DEW(self, time):
        """
        Gets the current N and DEW depending on which controller type it is
        :return: The current N and DEW values, None otherwise
        """
        if isinstance(self.controller, HybridController):
            current_N, current_rt_tol, idx = self.controller._get_current_N_DEW(time)
            return current_N, current_rt_tol
        elif isinstance(self.controller, TopNController):
            return self.controller.N, self.controller.rt_tol
        else:
            return None, None


class IAPIEnvironment(Environment):

    def __init__(self, mass_spec, controller, max_time, progress_bar=True, out_dir=None, out_file=None):
        super().__init__(mass_spec, controller, 0, max_time, progress_bar, out_dir, out_file)
        self.stop_time = None
        self.last_time = None
        self.pbar = tqdm(total=max_time, initial=0) if self.progress_bar else None

    def run(self):
        """
        Runs the mass spec and controller
        :return: None
        """
        # reset mass spec and set some initial values for each run
        self.mass_spec.reset()
        self.controller.reset()
        self._set_initial_values()

        # register event handlers from the controller
        self.mass_spec.register_event(IndependentMassSpectrometer.MS_SCAN_ARRIVED, self.add_scan)
        self.mass_spec.register_event(IndependentMassSpectrometer.ACQUISITION_STREAM_OPENING,
                                      self.controller.handle_acquisition_open)
        self.mass_spec.register_event(IndependentMassSpectrometer.ACQUISITION_STREAM_CLOSING,
                                      self.controller.handle_acquisition_closing)
        self.mass_spec.register_event(IndependentMassSpectrometer.STATE_CHANGED,
                                      self.controller.handle_state_changed)

        self.mass_spec.fire_event(IndependentMassSpectrometer.ACQUISITION_STREAM_OPENING)
        self.mass_spec.run()

        self.last_time = time.time()
        self.stop_time = self.last_time + self.max_time

    def add_scan(self, scan):
        # stop event handling if stop_time has been reached
        if time.time() > self.stop_time:
            self.mass_spec.close()
            self.close_progress_bar(self.pbar)
            self.write_mzML(self.out_dir, self.out_file)
        else:
            # handle the scan immediately by passing it to the controller
            self.scan_channel.append(scan)
            scan = self.scan_channel.pop(0)
            tasks = self.controller.handle_scan(scan)
            self.add_tasks(tasks)  # push new tasks to mass spec queue

            # update controller internal states AFTER a scan has been generated and handled
            self.controller.update_state_after_scan(scan)

            # increment progress bar
            self._update_progress_bar(self.pbar, scan)

    def _update_progress_bar(self, pbar, scan):
        if pbar is not None:
            current_time = time.time()
            elapsed = current_time - self.last_time
            self.last_time = current_time
            N, DEW = self._get_N_DEW(self.mass_spec.time)
            if N is not None and DEW is not None:
                msg = '(%.3fs) ms_level=%d N=%d DEW=%d' % (elapsed, scan.ms_level, N, DEW)
            else:
                msg = '(%.3fs) ms_level=%d' % (elapsed, scan.ms_level)
            pbar.update(elapsed)
            pbar.set_description(msg)
