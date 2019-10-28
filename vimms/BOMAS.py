from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern

from pyDOE import *
from pathlib import Path

from vimms.Controller import *
from vimms.PythonMzmine import pick_peaks, controller_score
from vimms.Common import *
import os, glob


MZMINE_COMMAND = 'C:\\Users\\Vinny\\work\\MZmine-2.40.1\\MZmine-2.40.1\\startMZmine_Windows.bat'
XML_TEMPLATE_MS1 = 'C:\\Users\\Vinny\\work\\vimms\\batch_files\\mzmine_batch_ms1.xml'
XML_TEMPLATE_MS2 = 'C:\\Users\\Vinny\\work\\vimms\\batch_files\\mzmine_batch_ms2.xml'

QCB_MZML2CHEMS_DICT = {'min_ms1_intensity': 1.75E5,
                  'mz_tol': 10,
                  'mz_units':'ppm',
                  'min_length':1,
                  'min_intensity':0,
                  'start_rt':3*60,
                  'stop_rt':21*60}

MADELEINE_MZML2CHEMS_DICT = {'min_ms1_intensity': 1.75E5,
                  'mz_tol': 10,
                  'mz_units':'ppm',
                  'min_length':1,
                  'min_intensity':0,
                  'start_rt':0,
                  'stop_rt':600}

QCB_TOP_N_CONTROLLER_PARAM_DICT = {"mz_tol":10,
                                   "min_ms1_intensity":1.75E5,
                                   "rt_range":[(0, 1440)],
                                   "isolation_window":1}

MADELEINE_TOP_N_CONTROLLER_PARAM_DICT = {"mz_tol":10,
                                   "min_ms1_intensity":1.75E5,
                                   "rt_range":[(0, 600)],
                                   "isolation_window":1}

QCB_SCORE_PARAM_DICT = {'min_ms1_intensity':0,
                        'matching_mz_tol':30,
                        'matching_rt_tol':10}


def mzml2chems(mzml_file, ps, param_dict=QCB_MZML2CHEMS_DICT, output_dir = True):
    good_roi, junk = make_roi(mzml_file, mz_tol=param_dict['mz_tol'], mz_units=param_dict['mz_units'],
                              min_length=param_dict['min_length'], min_intensity=param_dict['min_intensity'],
                              start_rt=param_dict['start_rt'], stop_rt=param_dict['stop_rt'])
    all_roi = good_roi + junk
    keep = []
    for roi in all_roi:
        if np.count_nonzero(np.array(roi.intensity_list) > param_dict['min_ms1_intensity']) > 0:
            keep.append(roi)
    all_roi = keep
    rtcc = RoiToChemicalCreator(ps, all_roi)
    dataset = rtcc.chemicals
    if output_dir is True:
        dataset_name = os.path.splitext(mzml_file)[0] + '.p'
        save_obj(dataset, dataset_name)
    return dataset

class TopN_GridSearch(object):
    def __init__(self, ms1_mzml, base_dir, N, DEW, ps,
                 chem_param_dict=QCB_MZML2CHEMS_DICT,
                 controller_param_dict=QCB_TOP_N_CONTROLLER_PARAM_DICT,
                 score_param_dict = QCB_SCORE_PARAM_DICT,
                 ms1_picked_peaks_file=None, dataset_file=None, parallel=False, add_noise=True,
                 xml_template_ms1=XML_TEMPLATE_MS1,
                 xml_template_ms2=XML_TEMPLATE_MS2,
                 mzmine_command=MZMINE_COMMAND):
        # make and set directories
        os.mkdir(base_dir + '\\' + Path(ms1_mzml).stem + '_TopN_Results')
        output_dir = base_dir + '\\' + Path(ms1_mzml).stem + '_TopN_Results'
        os.mkdir(output_dir + '//ms1_dir')
        ms1_dir = output_dir + '//ms1_dir'
        os.mkdir(output_dir + '//ms2_dir')
        ms2_dir = output_dir + '//ms2_dir'
        os.mkdir(output_dir + '//picked_peaks')
        picked_peaks_dir = output_dir + '//picked_peaks'

        # Load data
        if dataset_file is None:
            dataset = mzml2chems(ms1_mzml, ps, chem_param_dict)
        else:
            dataset = load_obj(dataset_file)
        if ms1_picked_peaks_file is None:
            pick_peaks([ms1_mzml], xml_template=xml_template_ms1, output_dir=picked_peaks_dir,
                       mzmine_command=mzmine_command)
            ms1_picked_peaks_file = picked_peaks_dir + '\\' + Path(ms1_mzml).stem + '.csv'

        if parallel is False:
            # set up mass spec
            mass_spec = IndependentMassSpectrometer(POSITIVE, dataset, ps, add_noise=add_noise)

            # run controllers
            for current_N in N:
                for current_DEW in DEW:
                    controller = TopNController(mass_spec, N, controller_param_dict["isolation_window"],
                                                controller_param_dict["mz_tol"], controller_param_dict["rt_tol"],
                                                controller_param_dict["min_ms1_intensity"])
                    controller.run(controller_param_dict["rt_range"][0][0], controller_param_dict["rt_range"][0][1])

                    controller_name = 'controller_' + current_N + '_' + current_DEW
                    controller.write_mzML('my_analysis', os.path.join(ms2_dir, controller_name + '.mzml'))
                    save_obj(controller, os.path.join(ms2_dir, controller_name + '.p'))

                    file_list = [os.path.join(ms2_dir, controller_name + '.mzml')]
                    pick_peaks(file_list, xml_template=xml_template_ms2, output_dir=picked_peaks_dir,mmzmine_command=MZMINE_COMMAND)
                    ms2_picked_peaks_file = output_dir + '//' + controller_name + '.csv'

                    controller_score(controller, dataset, ms1_picked_peaks_file, ms2_picked_peaks_file,
                                     score_param_dict['min_ms1_intensity'], score_param_dict['matching_mz_tol'],
                                     score_param_dict['matching_rt_tol'])
        else:
            None

    def heat_map(self):
        return None

# class BOMAS(object):
#     def _init_(self, experiment_name, theta_range, n_init, n_BO, ps, base_folder, samples=None, ms1_mzmls=None,
#                gp_noise= 0.01, gp_kernel=None, mass_spec_add_noise=True,
#                controller_method=None, controller_settings_dict=None,
#                xml_template_ms1='C:\\Users\\Vinny\\work\\vimms\\batch_files\\mzmine_batch_ms1.xml',
#                xml_template_ms2='C:\\Users\\Vinny\\work\\vimms\\batch_files\\mzmine_batch_ms2.xml'):
#         self.theta_range = theta_range
#         self.n_init = n_init
#         self.n_BO = n_BO
#         self.ps = ps
#         self.base_folder = base_folder
#
#         self.gp_noise = gp_noise
#         self.gp_kernel = gp_kernel
#
#         self.mass_spec_add_noise = mass_spec_add_noise
#         self.controller_settings_dict = controller_settings_dict
#         self.controller_method = controller_method
#
#         # make directories here
#         os.mkdir(self.base_folder + '\\' + experiment_name)
#         os.mkdir(self.base_folder + '\\' + experiment_name + '\\fullscan_mzml')
#         os.mkdir(self.base_folder + '\\' + experiment_name + '\\frag_mzml')
#         os.mkdir(self.base_folder + '\\' + experiment_name + '\\picked_peaks')
#
#         # set them as require locations
#         self.fullscan_mzml_dir = os.path(self.base_folder + '\\' + experiment_name + '\\fullscan_mzml')
#         self.frag_mzml_dir = os.path(self.base_folder + '\\' + experiment_name + '\\frag_mzml')
#         self.picked_peaks_dir = os.path(self.base_folder + '\\' + experiment_name + '\\picked_peaks_mzml')
#
#         # convert samples to the right format
#         assert samples is not None and ms1_mzmls is not None
#         if samples is None:
#             # TODO: convert each ms1_mzml to a dataset of chemicals
#         else:
#             # TODO run an ms1 scan for each sample
#
#         for i in range(len(self.datasets)):
#             # add relevent ms1 to fullscan_mzml folder
#             # TODO: do above
#             # pick peaks of relevent mzml
#             # TODO: do above
#             results = BOMAS_optimiser() # TODO: add some params here
#             # extract and store results
#             # TODO: store results
#             # clear folders
#             self._clear_folders()
#         self.global_params = self._get_global_param()
#
#     def _clear_folders(self):
#         # TODO: make this work
#         files = glob.glob('/YOUR/PATH/*')
#         for f in files:
#             os.remove(f)
#
#     def _get_global_param(self):
#         return 1 # TODO: add this
#
#
#
# class BOMAS_optimiser(object):
#     def __init__(self, dataset, theta_range, n_init, n_BO, ps, base_folder, gp_noise, gp_kernel=None,
#                  mass_spec_add_noise=True, controller_method=None, controller_settings_dict=None):
#         # set up self.params etc
#         self.theta_range = theta_range
#         self.controller_method = controller_method
#         self.ms1_mzml = ms1_mzml
#         self.base_folder = base_folder
#         self.controller_settings_dict = controller_settings_dict
#
#         # results
#         self.scores = [[] for i in datasets]
#         self.params = [[] for i in datasets]
#         self.optimal_param = [[] for i in datasets]
#         self.gps = [None for i in datasets]  # save the GPs, may be able to use them to optimise
#
#         # create some directories - then set up input and output dir
#         self.mzml_dir = base_folder + "/mzmls"
#         self.peaks_dir = base_folder + "/peaks"
#
#         # pick ms1 peaks
#         # TODO: need to load and pick peaks of ms1 file
#
#         # peak pick the ms1_mzmls
#
#         for idx in datasets:
#
#             # set up mass_spec
#             mass_spec = IndependentMassSpectrometer(POSITIVE, datasets[idx], ps, mass_spec_add_noise)
#
#             # set up GP
#             if gp_kernel is None:
#                 m52 = ConstantKernel(1.0) * Matern(length_scale=1.0, nu=2.5)
#             self.gps[idx] = GaussianProcessRegressor(kernel=m52, alpha=gp_noise ** 2)
#
#             # Run initial samples
#             self.params[idx] = self._get_scaled_theta(n_init)
#             for i in range(n_init + n_BO):
#                 # get next params if required
#                 if i >= n_init:
#                     current_param = self._get_next_theta()
#                     self.param[idx].append(current_param)
#                 # run controller
#                 self.controller = self._get_controller(mass_spec, self.param[i])
#                 self._run_controller(idx)
#                 # update peaks
#                 self._get_pick_peaks(idx)  # TODO: work out how this is going to work
#                 # calculate scores
#                 self.scores[idx].append(self._get_score())
#                 # update GP
#                 if i >= n_init -1:
#                     self.gps[idx].fit(self.params[idx], self.scores[idx])  # probably needs reformatting
#
#         # calculate a global answer
#         self.global_param = self._get_global_param()
#
#     def _get_global_param(self):
#         # calculate this eventually
#         global_param = []
#         return global_param
#
#     def _get_next_theta(self):
#         return [0 for i in range(len(self.theta_ranges))]
#         # TODO: update this work properly
#
#     def _run_controller(self, idx):
#         # run controller
#         self.controller.run(self.controller_settings_dict["rt_range"][0][0],
#                             self.controller_settings_dict["rt_range"][0][1])
#         controller_name = '/controller' + idx
#         self.controller.write_mzML('controller', os.path.join(self.mzml_dir, controller_name))
#
#     def _get_controller(self, mass_spec, current_param):
#         if self.controller_method == "Top N":
#             controller = TopNController(mass_spec, current_param[0], self.controller_settings_dict["isolation_window"],
#                                         self.controller_settings_dict["mz_tol"], current_param[1],
#                                         self.controller_settings_dict["min_ms1_intensity"])
#         return controller
#
#     def _get_scaled_theta(self, n_init):
#         # use theta range to get scaled theta for initial samples
#         scaled_theta = lhs(len(self.theta_ranges), samples=n_init, criterion='center')
#         scaled_theta = [np.round_(
#             scaled_theta[:, i] * (self.theta_ranges[i][1] - self.theta_ranges[i][0]) + self.theta_ranges[i][0], 0) for i
#                         in range(len(self.theta_ranges))]
#         return scaled_theta
#
#     def _get_pick_peaks(self, idx):
#         new_file_list = [self.mzml_dir + '/controller_' + idx + '.mzml']
#         pick_peaks(new_file_list, output_dir=self.peaks_dir, mzmine_command=MZMINE_COMMAND)
#         align(self.peaks_dir, mzmine_command = MZMINE_COMMAND)
#
#     def _get_score(self, idx):
#         ms2_picked_csv =
#         score = self.mzmine_score(ms2_picked_csv, self.ms1_picked)
#
#         return
#         # load all the files we need
#         # calculate score
#
# def mzmine_score(ms2_picked_csv, ms1_picked_csv):
#     # load the ms1
#     score = np.random.uniform(0,1,1).tolist()
#     return score
#
