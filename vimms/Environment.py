from pathlib import Path

from tqdm import tqdm

from vimms.Common import LoggerMixin


class Environment(LoggerMixin):
    def __init__(self, mass_spec, controller, min_time, max_time, progress_bar=True):
        self.mass_spec = mass_spec
        self.controller = controller
        self.min_time = min_time
        self.max_time = max_time
        self.progress_bar = progress_bar
        self.logger.info('Environment initialised with mass spec %s and controller %s' %
                         (self.mass_spec, self.controller))

    def run(self):
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
