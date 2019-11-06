from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern
from scipy.stats import norm
from scipy.optimize import minimize
from itertools import product

from pyDOE import *
from pathlib import Path
import pandas as pd
import itertools as it

from vimms.Controller import *
from vimms.PythonMzmine import pick_peaks, controller_score
from vimms.Common import *
from vimms.Roi import make_roi, RoiToChemicalCreator
import os
from vimms.MassSpec import IndependentMassSpectrometer
from vimms.Environment import *


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

QCB_TOP_N_CONTROLLER_PARAM_DICT = {"ionisation_mode": POSITIVE,
                                   "mz_tol": 10,
                                   "min_ms1_intensity": 1.75E5,
                                   "rt_range": [(0, 1440)],
                                   "isolation_window": 1}

MADELEINE_TOP_N_CONTROLLER_PARAM_DICT = {"ionisation_mode": POSITIVE,
                                         "mz_tol": 10,
                                         "min_ms1_intensity": 1.75E5,
                                         "rt_range": [(0, 600)],
                                         "isolation_window": 1}

QCB_SCORE_PARAM_DICT = {'min_ms1_intensity': 0,
                        'matching_mz_tol': 30,
                        'matching_rt_tol': 10}


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


class BaseOptimiser(object):
    def __init__(self, base_dir, ps,
                 controller_method = 'TopNController',
                 chem_param_dict=QCB_MZML2CHEMS_DICT,
                 controller_param_dict=QCB_TOP_N_CONTROLLER_PARAM_DICT,
                 score_param_dict=QCB_SCORE_PARAM_DICT,
                 ms1_mzml=None,
                 ms1_picked_peaks_file=None,
                 dataset_file=None,
                 add_noise=True,
                 xml_template_ms1=XML_TEMPLATE_MS1,
                 xml_template_ms2=XML_TEMPLATE_MS2,
                 mzmine_command=MZMINE_COMMAND):

        self.xml_template_ms1 = xml_template_ms1
        self.xml_template_ms2 = xml_template_ms2
        self.mzmine_command = mzmine_command
        idx = 0

        self.method_name = self.__class__.__name__

        self.base_name = self._get_base_name(ms1_mzml, ms1_picked_peaks_file, dataset_file)
        self.output_dir, self.ms2_dir, self.picked_peaks_dir = self._get_directories(base_dir, controller_method)
        self.dataset, self.ms1_picked_peaks_file = self._get_data(ms1_mzml, ms1_picked_peaks_file, dataset_file, ps, chem_param_dict)

        # set up mass spec
        mass_spec = IndependentMassSpectrometer(POSITIVE, self.dataset, ps, add_noise=add_noise)

        # get initial params and set up pandas dataframe
        self.initial_params, self.results = self._get_initial_params()

        # run optimisation algorithm
        next_flex_param_dict = self._get_next_params(idx)
        idx += 1
        while next_flex_param_dict is not None:
            new_results = self._get_controller_score(mass_spec, ms1_picked_peaks_file, controller_method,
                                               controller_param_dict, next_flex_param_dict, score_param_dict, idx - 1)
            self.results.loc[len(self.results)] = new_results
            next_flex_param_dict = self._get_next_params(idx)
            idx += 1
        # TODO: when initial parameters have been ran go to _get_extra_results(). Just return already existing results
        #  for GridSearch. Overwrite function for BOO, so does the new BO methods and returns results _ BO results
        df_name = self.base_name + '_df_results'
        self.results.to_pickle(self.output_dir + '\\' + df_name + '.p')

    def contourplot2D(self):
        X = self.results[self.results.columns[1:]].values
        names = list(self.results[self.results.columns[1:]].keys())

        # Input space
        x1 = np.linspace(X[:, 0].min(), X[:, 0].max())
        x2 = np.linspace(X[:, 1].min(), X[:, 1].max())

        x1x2 = np.array(list(product(x1, x2)))
        y_pred, MSE = self.gpr.predict(x1x2, return_std=True)

        X0p, X1p = x1x2[:, 0].reshape(50, 50), x1x2[:, 1].reshape(50, 50)
        Zp = np.reshape(y_pred, (50, 50))

        fig, ax = plt.subplots(figsize=(6, 6))

        ax.set_aspect('equal')
        cf = ax.contourf(X0p, X1p, Zp)
        fig.colorbar(cf, ax=ax)
        plt.xlabel(names[0])
        plt.ylabel(names[1])

        plt.show()

    def BOplot(self):
        return None # TODO: plot score as points are optimised

    def _get_extra_results(self):
        return self.results # TODO: work out what I wanted to do here

    def _get_base_name(self, ms1_mzml, ms1_picked_peaks_file, dataset_file):
        if ms1_mzml is not None:
            base_name = Path(ms1_mzml).stem
        elif ms1_picked_peaks_file is not None:
            base_name = Path(ms1_picked_peaks_file).stem
        elif dataset_file is not None:
            base_name = Path(dataset_file).stem
        else:
            sys.exit('No data provided')  # TODO: Check whether this works properly
        return base_name

    def _get_directories(self, base_dir, controller_method):
        # make and set directories
        output_dir = base_dir + '\\' + self.base_name + '_' + self.method_name + '_' + controller_method
        os.mkdir(output_dir)
        ms2_dir = output_dir + '\\ms2_dir'
        os.mkdir(ms2_dir)
        picked_peaks_dir = output_dir + '//picked_peaks'
        os.mkdir(picked_peaks_dir)
        return output_dir, ms2_dir, picked_peaks_dir

    def _get_data(self, ms1_mzml, ms1_picked_peaks_file, dataset_file, ps, chem_param_dict):
        # Load data
        if dataset_file is None:
            dataset = mzml2chems(ms1_mzml, ps, chem_param_dict)
        else:
            dataset = load_obj(dataset_file)
        if ms1_picked_peaks_file is None:
            pick_peaks([ms1_mzml], xml_template=self.xml_template_ms1, output_dir=self.picked_peaks_dir,
                       mzmine_command=self.mzmine_command)
            ms1_picked_peaks_file = self.picked_peaks_dir + '\\' + self.base_name + '.csv'

        return dataset, ms1_picked_peaks_file

    def _get_initial_params(self):
        NotImplementedError()

    def _get_next_params(self):
        NotImplementedError()

    def _get_controller_score(self, mass_spec, ms1_picked_peaks_file, controller_method,
                             controller_param_dict, next_flex_param_dict, score_param_dict, idx):
        controller = self._get_controller(controller_method, controller_param_dict, next_flex_param_dict)
        env = Environment(mass_spec, controller, controller_param_dict['rt_range'][0][0],
                          controller_param_dict['rt_range'][0][1], progress_bar=True)
        env.run()
        controller_name = 'controller_' + str(idx)
        env.write_mzML(self.ms2_dir, controller_name + '.mzml')
        save_obj(controller, os.path.join(self.ms2_dir, controller_name + '.p'))

        file_list = [os.path.join(self.ms2_dir, controller_name + '.mzml')]
        pick_peaks(file_list, xml_template=self.xml_template_ms2, output_dir=self.picked_peaks_dir,
                   mzmine_command=self.mzmine_command)
        ms2_picked_peaks_file = self.picked_peaks_dir + '\\' + controller_name + '_pp.csv'

        score = controller_score(controller, self.dataset, ms1_picked_peaks_file, ms2_picked_peaks_file,
                                 score_param_dict['min_ms1_intensity'],
                                 score_param_dict['matching_mz_tol'],
                                 score_param_dict['matching_rt_tol'])

        return [score] + list(next_flex_param_dict.values())

    def _get_controller(self, controller_method, controller_param_dict, flex_controller_param_dict):
        if controller_method == 'TopNController':
            controller = TopNController(controller_param_dict["ionisation_mode"],
                                        flex_controller_param_dict['N'],
                                        controller_param_dict["isolation_window"],
                                        controller_param_dict["mz_tol"],
                                        flex_controller_param_dict['DEW'],
                                        controller_param_dict["min_ms1_intensity"])
        return controller

# TODO: add parellel option to initial params controllers

class GridSearch(BaseOptimiser):
    def __init__(self, flex_controller_param_dict, *args, **kwargs):
        self.flex_controller_param_dict = flex_controller_param_dict
        super().__init__(*args, **kwargs)

    def _get_initial_params(self):
        # gets whole parameter list
        allNames = sorted(self.flex_controller_param_dict)
        combinations = list(it.product(*(self.flex_controller_param_dict[Name] for Name in allNames)))
        dictionaries = [dict(zip(allNames, combinations[i])) for i in range(len(combinations))]
        col_names = ['F1'] + list(dictionaries[0].keys())
        df = pd.DataFrame(columns=col_names)
        return dictionaries, df # TODO: make N an exception which rounds it

    def _get_next_params(self, idx):
        if idx < len(self.initial_params):
            return self.initial_params[idx]
        else:
            return None


class BOMAS(BaseOptimiser):
    def __init__(self, N_init, N_BO, GP_param, theta_range, *args, **kwargs):
        self.N_init = N_init
        self.N_BO = N_BO
        self.GP_param = GP_param
        self.theta_range = theta_range
        super().__init__(*args, **kwargs)

    def _get_initial_params(self):
        theta_array = [list(self.theta_range[list(self.theta_range.keys())[i]][0]) for i in range(len(self.theta_range))]
        scaled_theta = lhs(len(theta_array), samples=self.N_init, criterion='center')
        scaled_theta = np.array([(
        scaled_theta[:, i] * (theta_array[i][1] - theta_array[i][0]) + theta_array[i][0]).tolist()
                                 for i in range(len(theta_array))])
        if 'N' in self.theta_range.keys():
            which_N = list(np.where(np.array(list(self.theta_range.keys())) == 'N')[0])[0]
            scaled_theta[which_N] = np.round(scaled_theta[which_N], 0)
        dictionaries = [dict(zip(self.theta_range.keys(), scaled_theta[:, i])) for i in range(len(scaled_theta[0]))]
        col_names = ['F1'] + list(dictionaries[0].keys())
        df = pd.DataFrame(columns=col_names)
        return dictionaries, df

    def _get_next_params(self, idx):
        if idx < len(self.initial_params):
            return self.initial_params[idx]
        elif idx < self.N_init + self.N_BO:
            return self._get_next_BO_params(idx)
        else:
            return None

    def _get_next_BO_params(self, idx):
        noise = 0.1 # TODO: set this up properly at the start
        bounds = np.array([list(self.theta_range[list(self.theta_range.keys())[i]][0]) for i in range(len(self.theta_range))])
        m52 = ConstantKernel(1.0) * Matern(length_scale=1.0, nu=2.5)
        self.gpr = GaussianProcessRegressor(kernel=m52, alpha=noise ** 2)
        y = self.results[self.results.columns[0]].values
        theta = self.results[self.results.columns[1:]].values
        self.gpr.fit(theta, y)
        theta_next = propose_location(expected_improvement, theta, y, self.gpr, bounds) # TODO: add bounds + other parameters to start
        theta_next_dict = dict(zip(self.theta_range.keys(), theta_next.flatten().tolist()))
        if 'N' in list(self.theta_range.keys()):
            theta_next_dict['N'] = round(theta_next_dict['N'])
        return theta_next_dict


# TODO: add multi BOMAS which is able to work in parallel


def expected_improvement(X, X_sample, Y_sample, gpr, xi=0.01):
    ''' Computes the EI at points X based on existing samples X_sample and Y_sample using a Gaussian process surrogate model. Args: X: Points at which EI shall be computed (m x d). X_sample: Sample locations (n x d). Y_sample: Sample values (n x 1). gpr: A GaussianProcessRegressor fitted to samples. xi: Exploitation-exploration trade-off parameter. Returns: Expected improvements at points X. '''
    mu, sigma = gpr.predict(X, return_std=True)
    mu_sample = gpr.predict(X_sample)

    #sigma = sigma.reshape(-1, X_sample.shape[1])  # TODO: What is this meant to do?

    # Needed for noise-based model,
    # otherwise use np.max(Y_sample).
    # See also section 2.4 in [...]
    mu_sample_opt = np.max(mu_sample)

    with np.errstate(divide='warn'):
        imp = mu - mu_sample_opt - xi
        Z = imp / sigma
        ei = imp * norm.cdf(Z) + sigma * norm.pdf(Z)
        ei[sigma == 0.0] = 0.0

    return ei


def propose_location(acquisition, X_sample, Y_sample, gpr, bounds, n_restarts=25):
    ''' Proposes the next sampling point by optimizing the acquisition function. Args: acquisition: Acquisition function. X_sample: Sample locations (n x d). Y_sample: Sample values (n x 1). gpr: A GaussianProcessRegressor fitted to samples. Returns: Location of the acquisition function maximum. '''
    dim = X_sample.shape[1]
    min_val = 1
    min_x = None

    def min_obj(X):
        # Minimization objective is the negative acquisition function
        return -acquisition(X.reshape(-1, dim), X_sample, Y_sample, gpr)

    # Find the best optimum by starting from n_restart different random points.
    for x0 in np.random.uniform(bounds[:, 0], bounds[:, 1], size=(n_restarts, dim)):
        res = minimize(min_obj, x0=x0, bounds=bounds, method='L-BFGS-B')
        if res.fun < min_val:
            min_val = res.fun[0]
            min_x = res.x

    return min_x.reshape(-1, 1)


def load_scores(colnames, peak_files,  ms2_dir, dataset_file, ms1_picked_peaks_file, score_param_dict):
    dataset = load_obj(dataset_file)
    results = pd.DataFrame(columns=colnames)
    for i in range(len(peak_files)):
        ms2_picked_peaks_file = peak_files[i]
        controller = load_obj(ms2_dir + Path(peak_files[i]).stem[:-3] + '.p')
        score = controller_score(controller, dataset, ms1_picked_peaks_file, ms2_picked_peaks_file,
                                     score_param_dict['min_ms1_intensity'],
                                     score_param_dict['matching_mz_tol'],
                                     score_param_dict['matching_rt_tol'])
        new_entry = [score, controller.N, controller.rt_tol]
        results.loc[len(results)] = new_entry
        print(i)
    return results


# def TopN_GridSearch(base_dir, ps,
#                     flex_controller_param_dict,
#                     controller_method = 'TopNController',
#                     chem_param_dict=QCB_MZML2CHEMS_DICT,
#                     controller_param_dict=QCB_TOP_N_CONTROLLER_PARAM_DICT,
#                     score_param_dict = QCB_SCORE_PARAM_DICT,
#                     ms1_mzml=None, ms1_picked_peaks_file=None, dataset_file=None,
#                     add_noise=True,
#                     xml_template_ms1=XML_TEMPLATE_MS1,
#                     xml_template_ms2=XML_TEMPLATE_MS2,
#                     mzmine_command=MZMINE_COMMAND):
#     # get a base folder name
#     if ms1_mzml is not None:
#         base_name = Path(ms1_mzml).stem
#     elif ms1_picked_peaks_file is not None:
#         base_name = Path(ms1_picked_peaks_file).stem
#     elif dataset_file is not None:
#         base_name = Path(dataset_file).stem
#     else:
#         sys.exit('No data provided')
#
#     # make and set directories
#     os.mkdir(base_dir + '\\' + base_name + '_TopN_Results')
#     output_dir = base_dir + '\\' + base_name + '_TopN_Results'
#     os.mkdir(output_dir + '//ms2_dir')
#     ms2_dir = output_dir + '//ms2_dir'
#     os.mkdir(output_dir + '//picked_peaks')
#     picked_peaks_dir = output_dir + '//picked_peaks'
#
#     # Load data
#     if dataset_file is None:
#         dataset = mzml2chems(ms1_mzml, ps, chem_param_dict)
#     else:
#         dataset = load_obj(dataset_file)
#     if ms1_picked_peaks_file is None:
#         pick_peaks([ms1_mzml], xml_template=xml_template_ms1, output_dir=picked_peaks_dir,
#                    mzmine_command=mzmine_command)
#         ms1_picked_peaks_file = picked_peaks_dir + '\\' + base_name + '.csv'
#
#     # set up mass spec
#     mass_spec = IndependentMassSpectrometer(POSITIVE, dataset, ps, add_noise=add_noise)
#
#     param_combos = get_param_combinations(flex_controller_param_dict)
#     col_names = ['F1'] + list(param_combos[0].keys())
#     results = pd.DataFrame(columns=col_names)
#
#     # run controllers
#     for current_flex_dict in param_combos:
#         new_results = run_controller_score(mass_spec, dataset, ms1_picked_peaks_file, controller_method,
#                                  controller_param_dict, current_flex_dict, score_param_dict,
#                                  ms2_dir, picked_peaks_dir, xml_template_ms2, mzmine_command)
#         results.loc[len(results)] = new_results
#     df_name = base_name + '_df_results'
#     results.to_pickle(output_dir + '\\' + df_name + '.p')
#     return results
#
#
# # def run_controller_score(mass_spec, dataset, ms1_picked_peaks_file, controller_method,
# #                          controller_param_dict, flex_controller_param_dict, score_param_dict,
# #                          ms2_dir, picked_peaks_dir, xml_template, mzmine_command):
# #
# #     controller = get_controller(controller_method, controller_param_dict, flex_controller_param_dict)
# #     env = Environment(mass_spec, controller, controller_param_dict['rt_range'][0][0],
# #                       controller_param_dict['rt_range'][0][1], progress_bar=True)
# #     env.run()
# #     controller_name = 'controller_' + '_'.join([list(flex_controller_param_dict[i].keys())[0] +
# #                                                 '_' + str(list(flex_controller_param_dict[i].values())[0])
# #                                                 for i in range(len(flex_controller_param_dict))])
# #     env.write_mzML(ms2_dir, controller_name + '.mzml')
# #     save_obj(controller, os.path.join(ms2_dir, controller_name + '.p'))
# #
# #     file_list = [os.path.join(ms2_dir, controller_name + '.mzml')]
# #     pick_peaks(file_list, xml_template=xml_template, output_dir=picked_peaks_dir,
# #                mzmine_command=mzmine_command)
# #     ms2_picked_peaks_file = picked_peaks_dir + '\\' + controller_name + '_pp.csv'
# #
# #     score = controller_score(controller, dataset, ms1_picked_peaks_file, ms2_picked_peaks_file,
# #                              score_param_dict['min_ms1_intensity'],
# #                              score_param_dict['matching_mz_tol'],
# #                              score_param_dict['matching_rt_tol'])
# #
# #     return [score] + list(flex_controller_param_dict.values())
# #
# #
# # def get_controller(controller_method, controller_param_dict, flex_controller_param_dict):
# #     if controller_method == 'TopNController':
# #         controller = TopNController(controller_param_dict["ionisation_mode"],
# #                                     flex_controller_param_dict['N'],
# #                                     controller_param_dict["isolation_window"],
# #                                     controller_param_dict["mz_tol"],
# #                                     flex_controller_param_dict['DEW'],
# #                                     controller_param_dict["min_ms1_intensity"])
# #     return controller


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


