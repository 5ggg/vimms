import sys
import unittest

sys.path.append('..')

from pathlib import Path

from vimms.Chemicals import ChemicalCreator, GET_MS2_BY_PEAKS, GET_MS2_BY_SPECTRA
from vimms.MassSpec import IndependentMassSpectrometer
from vimms.Controller import SimpleMs1Controller, TopNController, HybridController, RoiController
from vimms.Environment import Environment
from vimms.Common import *

dir_path = os.path.dirname(os.path.realpath(__file__))
base_dir = os.path.abspath(Path(dir_path, 'fixtures'))
hmdb = load_obj(Path(base_dir, 'hmdb_compounds.p'))
out_dir = Path(dir_path, 'results')

ROI_Sources = [str(Path(base_dir, 'beer_t10_simulator_files'))]
min_ms1_intensity = 1.75E5
rt_range = [(0, 1200)]
min_rt = rt_range[0][0]
max_rt = rt_range[0][1]
mz_range = [(0, 1050)]
n_chems = 500


class TestMS1Controller(unittest.TestCase):
    """
    Tests the MS1 controller that does MS1 full-scans only with the simulated mass spec class.
    """
    def setUp(self):
        self.ps = load_obj(Path(base_dir, 'peak_sampler_mz_rt_int_beerqcb_fullscan.p'))
        self.ms_level = 1

    def test_ms1_controller_can_run(self):
        logger.info('Testing MS1 Controller')

        # create some chemical objects
        chems = ChemicalCreator(self.ps, ROI_Sources, hmdb)
        dataset = chems.sample(mz_range, rt_range, min_ms1_intensity, n_chems, self.ms_level)
        self.assertEqual(len(dataset), n_chems)

        # create a simulated mass spec and MS1 controller
        mass_spec = IndependentMassSpectrometer(POSITIVE, dataset, self.ps)
        controller = SimpleMs1Controller()

        # create an environment to run both the mass spec and controller
        env = Environment(mass_spec, controller, min_rt, max_rt, progress_bar=True)

        # set the log level to WARNING so we don't see too many messages when environment is running
        set_log_level_warning()

        # run the simulation
        env.run()

        # set the log level back to DEBUG
        set_log_level_debug()

        # write simulated output to mzML file
        filename = 'multibeer_ms1.mzML'
        out_file = os.path.join(out_dir, filename)
        env.write_mzML(out_dir, filename)
        self.assertTrue(os.path.exists(out_file))
        print()


class TestTopNController(unittest.TestCase):
    """
    Tests the Top-N controller that does standard DDA Top-N fragmentation scans with the simulated mass spec class.
    """

    def setUp(self):
        self.ps = load_obj(Path(base_dir, 'peak_sampler_mz_rt_int_beerqcb_fragmentation.p'))
        self.ms_level = 1

    def test_TopN_controller_can_run(self):
        logger.info('Testing Top-N Controller')

        # create some chemical objects
        chems = ChemicalCreator(self.ps, ROI_Sources, hmdb)
        dataset = chems.sample(mz_range, rt_range, min_ms1_intensity, n_chems, self.ms_level,
                               get_children_method=GET_MS2_BY_PEAKS)
        self.assertEqual(len(dataset), n_chems)

        isolation_width = 1
        N = 10
        rt_tol = 15
        mz_tol = 10
        ionisation_mode = POSITIVE

        # create a simulated mass spec without noise and Top-N controller
        logger.info('Without noise')
        mass_spec = IndependentMassSpectrometer(ionisation_mode, dataset, self.ps, add_noise=False)
        controller = TopNController(ionisation_mode, N, isolation_width, mz_tol, rt_tol, min_ms1_intensity)

        # create an environment to run both the mass spec and controller
        env = Environment(mass_spec, controller, min_rt, max_rt, progress_bar=True)

        # set the log level to WARNING so we don't see too many messages when environment is running
        set_log_level_warning()

        # run the simulation
        env.run()

        # set the log level back to DEBUG
        set_log_level_debug()

        # write simulated output to mzML file
        filename = 'multibeer_TopN_ms2Peaks_noNoise.mzML'
        out_file = os.path.join(out_dir, filename)
        env.write_mzML(out_dir, filename)
        self.assertTrue(os.path.exists(out_file))

        # create a simulated mass spec with noise and Top-N controller
        logger.info('With noise')
        mass_spec = IndependentMassSpectrometer(ionisation_mode, dataset, self.ps, add_noise=True)
        controller = TopNController(ionisation_mode, N, isolation_width, mz_tol, rt_tol, min_ms1_intensity)

        # create an environment to run both the mass spec and controller
        env = Environment(mass_spec, controller, min_rt, max_rt, progress_bar=True)

        # set the log level to WARNING so we don't see too many messages when environment is running
        set_log_level_warning()

        # run the simulation
        env.run()

        # set the log level back to DEBUG
        set_log_level_debug()

        # write simulated output to mzML file
        filename = 'multibeer_TopN_ms2Peaks_withNoise.mzML'
        out_file = os.path.join(out_dir, filename)
        env.write_mzML(out_dir, filename)
        self.assertTrue(os.path.exists(out_file))
        print()


class TestHybridController(unittest.TestCase):
    """
    Tests the Hybrid controller that does many things, including:
    - standard DDA Top-N fragmentation scans
    - work in progress for Bayesian optimisation for Top-N parameters in real-time
    - purity experiments
    """

    def setUp(self):
        self.ps = load_obj(Path(base_dir, 'peak_sampler_mz_rt_int_beerqcb_fragmentation.p'))
        self.ms_level = 1

    def test_hybrid_controller_can_run(self):
        logger.info('Testing Hybrid Controller')

        # create some chemical objects
        chems = ChemicalCreator(self.ps, ROI_Sources, hmdb)
        dataset = chems.sample(mz_range, rt_range, min_ms1_intensity, n_chems, self.ms_level,
                               get_children_method=GET_MS2_BY_PEAKS)
        self.assertEqual(len(dataset), n_chems)

        # set different isolation widths, Ns, dynamic exclusion RT and mz tolerances at different timepoints
        isolation_widths = [1, 1, 1, 1]
        N = [5, 10, 15, 20]
        rt_tol = [15, 30, 60, 120]
        mz_tol = [10, 5, 15, 20]
        scan_param_changepoints = [300, 600, 900] # the timepoints when we will change the 4 parameters above
        ionisation_mode = POSITIVE

        # create a simulated mass spec with noise and Hybrid controller
        mass_spec = IndependentMassSpectrometer(ionisation_mode, dataset, self.ps, add_noise=True)
        controller = HybridController(ionisation_mode, N, scan_param_changepoints, isolation_widths, mz_tol, rt_tol,
                                      min_ms1_intensity)

        # create an environment to run both the mass spec and controller
        env = Environment(mass_spec, controller, min_rt, max_rt, progress_bar=True)

        # set the log level to WARNING so we don't see too many messages when environment is running
        set_log_level_warning()

        # run the simulation
        env.run()

        # set the log level back to DEBUG
        set_log_level_debug()

        # write simulated output to mzML file
        filename = 'QCB_Hybrid_ms2Spectra.mzML'
        out_file = os.path.join(out_dir, filename)
        env.write_mzML(out_dir, filename)
        self.assertTrue(os.path.exists(out_file))
        print()


class TestROIController(unittest.TestCase):
    """
    Tests the ROI controller that performs fragmentations and dynamic exclusions based on selecting regions of interests
    (rather than the top-N most intense peaks)
    """
    def setUp(self):
        self.ps = load_obj(Path(base_dir, 'peak_sampler_mz_rt_int_beerqcb_fragmentation.p'))
        self.ms_level = 1

    def test_roi_controller_can_run(self):
        logger.info('Testing ROI Controller')

        # create some chemical objects
        chems = ChemicalCreator(self.ps, ROI_Sources, hmdb)
        dataset = chems.sample(mz_range, rt_range, min_ms1_intensity, n_chems, self.ms_level,
                               get_children_method=GET_MS2_BY_SPECTRA)
        self.assertEqual(len(dataset), n_chems)

        isolation_width = 1  # the isolation window in Dalton around a selected precursor ion
        N = 10
        rt_tol = 15
        mz_tol = 10
        min_roi_intensity = 5000
        min_roi_length = 10
        ionisation_mode = POSITIVE

        # create a simulated mass spec with noise and ROI controller
        mass_spec = IndependentMassSpectrometer(ionisation_mode, dataset, self.ps, add_noise=True)
        controller = RoiController(ionisation_mode, isolation_width, mz_tol, min_ms1_intensity,
                                   min_roi_intensity, min_roi_length, "Top N", N, rt_tol)

        # create an environment to run both the mass spec and controller
        env = Environment(mass_spec, controller, min_rt, max_rt, progress_bar=True)

        # set the log level to WARNING so we don't see too many messages when environment is running
        set_log_level_warning()

        # run the simulation
        env.run()

        # set the log level back to DEBUG
        set_log_level_debug()

        # write simulated output to mzML file
        filename = 'QCB_ROIController.mzML'
        out_file = os.path.join(out_dir, filename)
        env.write_mzML(out_dir, filename)
        self.assertTrue(os.path.exists(out_file))
        print()


if __name__ == '__main__':
    unittest.main()
