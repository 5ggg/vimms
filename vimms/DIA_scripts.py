from vimms.Common import POSITIVE
from vimms.Controller import TreeController
from vimms.MassSpec import IndependentMassSpectrometer

# maybe this function can be deleted and just be defined in a notebook
def DiaRestrictedScanner(dataset, ps, dia_design, window_type, kaufmann_design, extra_bins, num_windows=None,
                         pbar=False):
    mass_spec = IndependentMassSpectrometer(POSITIVE, dataset, ps)
    controller = TreeController(mass_spec, dia_design, window_type, kaufmann_design, extra_bins, num_windows)
    controller.run(10, 20, pbar)
    controller.scans[2] = controller.scans[2][0:(controller.scans[1][1].scan_id - 1)]
    controller.scans[1] = controller.scans[1][0:2]
    return controller
