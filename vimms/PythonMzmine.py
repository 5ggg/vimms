import os,glob
import xml.etree.ElementTree
import pandas as pd
import numpy as np

from vimms.Common import PROTON_MASS
from vimms.Chemicals import UnknownChemical
from vimms.PlotsForPaper import get_chem_frag_counts, match, update_matched_status, compute_pref_rec_f1, get_frag_events

def pick_peaks(file_list,
                xml_template = 'batch_files/PretermPilot2Reduced.xml',
                output_dir = '/Users/simon/git/pymzmine/output',
                mzmine_command = '/Users/simon/MZmine-2.40.1/startMZmine_MacOSX.command'):
    et = xml.etree.ElementTree.parse(xml_template)
    # Loop over files in the list (just the firts three for now)
    for filename in file_list:
        print("Creating xml batch file for {}".format(filename.split(os.sep)[-1]))
        root = et.getroot()
        for child in root:
            # Set the input filename
            if child.attrib['method'] == 'net.sf.mzmine.modules.rawdatamethods.rawdataimport.RawDataImportModule':
                for e in child:
                    for g in e:
                        g.text = filename # raw data file name
            # Set the csv export filename
            if child.attrib['method'] == 'net.sf.mzmine.modules.peaklistmethods.io.csvexport.CSVExportModule': #TODO: edit / remove
                for e in child:
                    for g in e:
                        tag = g.tag
                        text = g.text
                        if tag == 'current_file' or tag == 'last_file':
                            csv_name = os.path.join(output_dir,filename.split(os.sep)[-1].split('.')[0]+'_pp.csv')
                            g.text = csv_name
        # write the xml file for this input file
        new_xml_name = os.path.join(output_dir,filename.split(os.sep)[-1].split('.')[0]+'.xml')
        et.write(new_xml_name)
        # Run mzmine
        print("Running mzMine for {}".format(filename.split(os.sep)[-1]))
        os.system(mzmine_command + ' "{}"'.format(new_xml_name))


def pick_peaks2chems(csv_file):
    df = pd.read_csv(csv_file)
    rts = df['row retention time'] * 60
    mzs = df['row m/z'] - PROTON_MASS
    chems = []
    for i in range(len(rts)):
        chem = UnknownChemical(mzs[i], rts[i], max_intensity=0, chromatogram=None, children=None)
        chems.append(chem)
    return chems


def mzmine_score(controller, dataset, ms1_chems, ms2_chems, min_ms1_intensity, matching_mz_tol, matching_rt_tol):
    chem_to_frag_events = get_frag_events(controller, 2)

    # match with xcms peak-picked ms1 data from fullscan file
    matches_fullscan = mzmine_match(dataset, ms1_chems, matching_mz_tol, matching_rt_tol, verbose=False)

    # match with xcms peak-picked ms1 data from fragmentation file
    matches_fragfile = mzmine_match(dataset, ms2_chems, matching_mz_tol, matching_rt_tol, verbose=False)

    # check if matched and set a flag to indicate that
    update_matched_status(dataset, matches_fullscan, matches_fragfile)

    # True positive: a peak that is fragmented above the minimum MS1 intensity and is picked by XCMS from
    # the MS1 information in the DDA file and is picked in the fullscan file.
    found_in_both = list(filter(lambda x: x.found_in_fullscan and x.found_in_fragfile, dataset))
    frag_count = get_chem_frag_counts(found_in_both, chem_to_frag_events, min_ms1_intensity)
    tp = [chem for chem in found_in_both if frag_count[chem]['good'] > 0 and frag_count[chem]['bad'] == 0]
    tp = len(tp)

    # False positive: any peak that is above minimum intensity and is picked by XCMS
    # from the DDA file but is not picked from the fullscan.
    found_in_dda_only = list(filter(lambda x: not x.found_in_fullscan and x.found_in_fragfile, dataset))
    frag_count = get_chem_frag_counts(found_in_dda_only, chem_to_frag_events, min_ms1_intensity)
    fp = [chem for chem in found_in_dda_only if frag_count[chem]['good'] > 0 and frag_count[chem]['bad'] == 0]
    fp = len(fp)

    # False negative: any peak that is picked from fullscan data, and is not fragmented, or
    # is fragmented below the minimum intensity.
    found_in_fullscan = list(filter(lambda x: x.found_in_fullscan, dataset))
    fn = len(found_in_fullscan) - tp
    if tp == 0:
        prec = rec = f1 = 0
    else:
        prec, rec, f1 = compute_pref_rec_f1(tp, fp, fn)
    return tp, fp, fn, prec, rec, f1


def controller_score(controller, dataset, ms1_picked_peaks_file, ms2_picked_peaks_file, min_ms1_intensity, matching_mz_tol, matching_rt_tol):
    # convert to chemicals
    ms1_chems = pick_peaks2chems(ms1_picked_peaks_file)
    ms2_chems = pick_peaks2chems(ms2_picked_peaks_file)
    # calculate score
    tp, fp, fn, prec, rec, f1 = mzmine_score(controller, dataset, ms1_chems, ms2_chems, min_ms1_intensity, matching_mz_tol, matching_rt_tol)
    return f1


def mzmine_find_chem(to_find, min_rts, max_rts, min_mzs, max_mzs, chem_list):
    query_mz = to_find.isotopes[0][0]
    query_rt = to_find.chromatogram.rts[to_find.chromatogram.intensities.argmax()] + to_find.rt
    min_rt_check = min_rts <= query_rt
    max_rt_check = query_rt <= max_rts
    min_mz_check = min_mzs <= query_mz
    max_mz_check = query_mz <= max_mzs
    idx = np.nonzero(min_rt_check & max_rt_check & min_mz_check & max_mz_check)[0]
    matches = chem_list[idx]

    # pick a match
    if len(matches) == 0:
        return None
    elif len(matches) == 1:
        return matches[0]
    else:  # multiple matches, take the closest in rt
        diffs = [np.abs(chem.rt - to_find.rt) for chem in matches]
        idx = np.argmin(diffs)
        return matches[idx]


def mzmine_match(chemical_list_1, chemical_list_2, mz_tol, rt_tol, verbose=False):
    matches = {}
    missing = []
    chem_list = np.array(chemical_list_2)
    min_rts = np.array([chem.rt - rt_tol for chem in chem_list])
    max_rts = np.array([chem.rt + rt_tol for chem in chem_list])
    min_mzs = np.array([chem.isotopes[0][0] * (1 - mz_tol / 1e6) for chem in chem_list])
    max_mzs = np.array([chem.isotopes[0][0] * (1 + mz_tol / 1e6) for chem in chem_list])
    for i in range(len(chemical_list_1)):
        to_find = chemical_list_1[i]
        if i % 1000 == 0 and verbose:
            print('%d/%d found %d' % (i, len(chemical_list_1), len(matches)))
        match = mzmine_find_chem(to_find, min_rts, max_rts, min_mzs, max_mzs, chem_list)
        if match:
            matches[to_find] = match
    return matches
