from pathlib import Path

from tqdm import tqdm

from vimms.Common import LoggerMixin, DEFAULT_MS1_SCAN_WINDOW
from vimms.Controller import TopNController, HybridController
from vimms.MassSpec import ScanParameters, IndependentMassSpectrometer
from vimms.MzmlWriter import MzmlWriter


class Environment(LoggerMixin):
    def __init__(self, mass_spec, controller, min_time, max_time, progress_bar=True):
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
        self.mass_spec.reset()
        self._set_initial_values()
        self._set_default_scan_params()

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
                    scan = self.mass_spec.step()
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
            N, DEW = self._get_N_DEW()
            if N > 0 and DEW > 0:
                msg = '(%.3fs) ms_level=%d N=%d DEW=%d' % (self.mass_spec.time, scan.ms_level, N, DEW)
            else:
                msg = '(%.3fs) ms_level=%d' % (self.mass_spec.time, scan.ms_level)
            pbar.update(scan.scan_duration)
            pbar.set_description(msg)

    def add_tasks(self, scan_params):
        self.task_channel.extend(scan_params)
        while len(self.task_channel) > 0:
            new_task = self.task_channel.pop(0)
            self.mass_spec.processing_queue.append(new_task)

    def add_scan(self, scan):
        self.scan_channel.append(scan)
        scan = self.scan_channel.pop(0)
        tasks = self.controller.handle_scan(scan)
        self.add_tasks(tasks)

    def write_mzML(self, out_dir, out_file):
        mzml_filename = Path(out_dir, out_file)
        writer = MzmlWriter('my_analysis', self.controller.scans,
                            precursor_information=self.mass_spec.precursor_information)
        writer.write_mzML(mzml_filename)
        self.logger.debug('Written %s' % mzml_filename)

    def _set_default_scan_params(self):
        default_scan = ScanParameters()
        default_scan.set(ScanParameters.MS_LEVEL, 1)
        default_scan.set(ScanParameters.ISOLATION_WINDOWS, [[DEFAULT_MS1_SCAN_WINDOW]])
        self.mass_spec.set_repeating_scan(default_scan)

    def _set_initial_values(self):
        self.mass_spec.environment = self
        self.controller.environment = self

        N, DEW = self._get_N_DEW()
        self.mass_spec.current_N = N
        self.mass_spec.current_DEW = DEW
        self.mass_spec.time = self.min_time

    def _get_N_DEW(self):
        if isinstance(self.controller, HybridController):
            current_N, current_rt_tol, idx = self.controller._get_current_N_DEW()
            return current_N, current_rt_tol
        elif isinstance(self.controller, TopNController):
            return self.controller.N, self.controller.rt_tol
        else:
            return 0, 0