from pathlib import Path

from tqdm import tqdm

from vimms.Common import LoggerMixin, DEFAULT_MS1_SCAN_WINDOW
from vimms.Controller import TopNController, HybridController
from vimms.MassSpec import ScanParameters, IndependentMassSpectrometer


class Environment(LoggerMixin):
    def __init__(self, mass_spec, controller, min_time, max_time, progress_bar=True):
        self.logger.info('Initialising environment with mass spec %s and controller %s' %
                         (mass_spec, controller))

        self.mass_spec = mass_spec
        self.controller = controller
        self.min_time = min_time
        self.max_time = max_time
        self.progress_bar = progress_bar

    def run(self):
        self.mass_spec.reset()

        # set initial N and DEW values
        if isinstance(self.controller, TopNController):
            self.mass_spec.current_N = self.controller.N
            self.mass_spec.current_DEW = self.controller.rt_tol
        elif isinstance(self.controller, HybridController):
            current_N, current_rt_tol, idx = self.controller._get_current_N_DEW()
            self.mass_spec.current_N = current_N
            self.mass_spec.current_DEW = current_rt_tol

        # set default scan parameters
        default_scan = ScanParameters()
        default_scan.set(ScanParameters.MS_LEVEL, 1)
        default_scan.set(ScanParameters.ISOLATION_WINDOWS, [[DEFAULT_MS1_SCAN_WINDOW]])
        self.mass_spec.set_repeating_scan(default_scan)

        # register event handlers from the controller
        self.mass_spec.register(IndependentMassSpectrometer.MS_SCAN_ARRIVED, self.controller.handle_scan)
        self.mass_spec.register(IndependentMassSpectrometer.ACQUISITION_STREAM_OPENING,
                                self.controller.handle_acquisition_open)
        self.mass_spec.register(IndependentMassSpectrometer.ACQUISITION_STREAM_CLOSING,
                                self.controller.handle_acquisition_closing)

        # run mass spec
        if self.progress_bar:
            with tqdm(total=self.max_time - self.min_time, initial=0) as pbar:
                self.mass_spec.run(self.min_time, self.max_time, pbar=pbar)
        else:
            self.mass_spec.run(self.min_time, self.max_time)

    def async_run(self):
        pass

    def write_mzML(self, out_dir, out_file):
        mzml_filename = Path(out_dir, out_file)
        self.controller.write_mzML('my_analysis', mzml_filename)
        self.logger.debug('Written %s' % mzml_filename)
