import sys
import time
from pathlib import Path

from tqdm import tqdm

from vimms.Common import LoggerMixin, DEFAULT_MS1_SCAN_WINDOW
from vimms.Controller import TopNController, HybridController
from vimms.MassSpec import ScanParameters, IndependentMassSpectrometer
from vimms.MzmlWriter import MzmlWriter


class Environment(LoggerMixin):
    def __init__(self, mass_spec, controller, min_time, max_time, progress_bar=True):
        """
        Initialises a synchronous environment to run the mass spec and controller
        :param mass_spec: An instance of Mass Spec object
        :param controller: An instance of Controller object
        :param min_time: start time
        :param max_time: end time
        :param progress_bar: True if a progress bar is to be shown
        """
        self.logger.info('Initialising environment with mass spec %s and controller %s' %
                         (mass_spec, controller))
        self.scan_channel = []
        self.task_channel = []
        self.mass_spec = mass_spec
        self.controller = controller
        self.min_time = min_time
        self.max_time = max_time
        self.progress_bar = progress_bar

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
        self.mass_spec.register(IndependentMassSpectrometer.MS_SCAN_ARRIVED, self.controller.handle_scan)
        self.mass_spec.register(IndependentMassSpectrometer.ACQUISITION_STREAM_OPENING,
                                self.controller.handle_acquisition_open)
        self.mass_spec.register(IndependentMassSpectrometer.ACQUISITION_STREAM_CLOSING,
                                self.controller.handle_acquisition_closing)

        # run mass spec
        with tqdm(total=self.max_time - self.min_time, initial=0) as pbar:
            bar = pbar if self.progress_bar else None
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
            finally:
                self.mass_spec.fire_event(IndependentMassSpectrometer.ACQUISITION_STREAM_CLOSING)
                if bar is not None:
                    bar.close()

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
            pbar.update(scan.scan_duration)
            pbar.set_description(msg)

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
            self.mass_spec.processing_queue.append(new_task)

    def write_mzML(self, out_dir, out_file):
        """
        Writes mzML to output file
        :param out_dir: output directory
        :param out_file: output filename
        :return: None
        """
        mzml_filename = Path(out_dir, out_file)
        try:
            precursor_information = self.controller.precursor_information
        except AttributeError:
            precursor_information = None
        writer = MzmlWriter('my_analysis', self.controller.scans, precursor_information)
        writer.write_mzML(mzml_filename)
        self.logger.debug('Written %s' % mzml_filename)

    def _set_initial_values(self):
        """
        Sets initial environment, mass spec start time, default scan parameters and other values
        :return: None
        """
        self.controller.set_environment(self)
        self.mass_spec.set_environment(self)
        self.mass_spec.time = self.min_time
        self._set_default_scan_params()

        N, DEW = self._get_N_DEW(self.mass_spec.time)
        if N is not None:
            self.mass_spec.current_N = N
        if DEW is not None:
            self.mass_spec.current_DEW = DEW

    def _set_default_scan_params(self):
        """
        Sets default scan parmaeters
        :return: None
        """
        default_scan = ScanParameters()
        default_scan.set(ScanParameters.MS_LEVEL, 1)
        default_scan.set(ScanParameters.ISOLATION_WINDOWS, [[DEFAULT_MS1_SCAN_WINDOW]])
        self.mass_spec.set_repeating_scan(default_scan)

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

    def __init__(self, mass_spec, controller, max_time, progress_bar=True):
        super().__init__(mass_spec, controller, 0, max_time, progress_bar)
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
        self.mass_spec.register(IndependentMassSpectrometer.MS_SCAN_ARRIVED, self.controller.handle_scan)
        self.mass_spec.register(IndependentMassSpectrometer.ACQUISITION_STREAM_OPENING,
                                self.controller.handle_acquisition_open)
        self.mass_spec.register(IndependentMassSpectrometer.ACQUISITION_STREAM_CLOSING,
                                self.controller.handle_acquisition_closing)

        self.last_time = time.time()
        self.stop_time = self.last_time + self.max_time
        self.mass_spec.fire_event(IndependentMassSpectrometer.ACQUISITION_STREAM_OPENING)
        self.mass_spec.run()

    def add_scan(self, scan):
        # stop event handling if stop_time has been reached
        if time.time() > self.stop_time:
            self.logger.debug('Unregistering MsScanArrived event handler')
            self.mass_spec.fusionScanContainer.MsScanArrived -= self.mass_spec.step
            self.mass_spec.fire_event(IndependentMassSpectrometer.ACQUISITION_STREAM_CLOSING)
        else:
            super().add_scan(scan)  # will call the controller to handle the scan here

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
