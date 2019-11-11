extern alias v1;
extern alias v2;

using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

using IAPI_Assembly;

using Thermo.Interfaces.FusionAccess_V1;
using Thermo.Interfaces.FusionAccess_V1.MsScanContainer;
using Thermo.Interfaces.SpectrumFormat_V1;
using Thermo.TNG.Factory;
using v2::Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer;

using v2::Thermo.Interfaces.InstrumentAccess_V1;
using v2::Thermo.Interfaces.InstrumentAccess_V1.Control;
using v2::Thermo.Interfaces.InstrumentAccess_V1.Control.Scans;

using IInfoContainerV1 = v1::Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer.IInfoContainer;
using IMsScanV1 = v1::Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer.IMsScan;
using IMsScanV2 = v2::Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer.IMsScan;
using MsScanInformationSourceV1 = v1::Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer.MsScanInformationSource;

// using ICentroid = v2::Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer.ICentroid;

namespace ScanDump
{
    internal class ScansOutput
    {
        private List<string> Logs { get; set; }
        private IFusionMsScanContainer ScanContainer { get; set; }
        private IScans m_scans;

        static void Main(string[] args)
        {
            //// Use the Factory creation method to create a Fusion Access Container
            IFusionInstrumentAccessContainer fusionContainer = Factory<IFusionInstrumentAccessContainer>.Create();

            // Above won't work without a license! For testing, use the following FusionContainer that loads data from an mzML file.
            // string filename = "C:\\Users\\joewa\\University of Glasgow\\Vinny Davies - CLDS Metabolomics Project\\Data\\multibeers_urine_data\\beers\\fragmentation\\mzML\\Beer_multibeers_1_T10_POS.mzML";
            // IFusionInstrumentAccessContainer fusionContainer = new FusionContainer(filename);

            // Connect to the service by going 'online'
            fusionContainer.StartOnlineAccess();

            // Wait until the service is connected 
            // (better through the event, but this is nice and simple)
            while (!fusionContainer.ServiceConnected)
            {
                ;
            }

            // From the instrument container, get access to a particular instrument
            IFusionInstrumentAccess fusionAccess = fusionContainer.Get(1);

            // Dump scan output
            ScansOutput scansOutput = new ScansOutput(fusionAccess);

            // https://stackoverflow.com/questions/2555292/how-to-run-code-before-program-exit
            // https://stackoverflow.com/questions/33060838/c-sharp-processexit-event-handler-not-triggering-code
            AppDomain.CurrentDomain.ProcessExit += (sender, EventArgs) =>
            {
                scansOutput.CloseDown();
            };
            Console.ReadLine();
        }

        private ScansOutput(IFusionInstrumentAccess instrument)
        {
            Logs = new List<string>();
            ScanContainer = instrument.GetMsScanContainer(0);
            WriteLog("Detector class: " + ScanContainer.DetectorClass);

            // Dump key-value pairs in cs.Values
            WriteLog("Custom scan parameters: ");
            ICustomScan cs = m_scans.CreateCustomScan();
            foreach (KeyValuePair<string, string> kvp in cs.Values)
            {
                string msg = string.Format("cs.Values Key = {0}, Value = {1}", kvp.Key, kvp.Value);
                WriteLog(msg, true);
            }

            // Set event handler for ms scan arrived
            ScanContainer.MsScanArrived += new EventHandler<MsScanEventArgs>(ScanContainer_ScanArrived);
        }

        private void WriteLog(string msg, bool print=false)
        {
            string msgWithTimestamp = string.Format("[{0:HH:mm:ss.ffff}] {1}", DateTime.Now, msg);
            Logs.Add(msgWithTimestamp);
            if (print)
            {
                Console.WriteLine(msgWithTimestamp);
            }
        }

        private void CloseDown()
        {
            WriteLog("Goodbye Cruel World", true);

            // Be tolerant to thread-switches
            IFusionMsScanContainer scanContainer = ScanContainer;
            ScanContainer = null;

            if (scanContainer != null)
            {
                scanContainer.MsScanArrived -= new EventHandler<MsScanEventArgs>(ScanContainer_ScanArrived);
                IMsScanV2 scan = scanContainer.GetLastMsScan();
                DumpScan("GetLastScan()", scan);
            }

            // write log files to Desktop
            string docPath = Environment.GetFolderPath(Environment.SpecialFolder.Desktop);
            string fileName = "ScanDump_" + DateTime.Now.ToFileTime() + ".txt";
            using (StreamWriter outputFile = new StreamWriter(Path.Combine(docPath, fileName)))
            {
                foreach (string line in Logs)
                    outputFile.WriteLine(line);
            }
        }

        /// <summary>
        /// When a new scan arrives we dump that information in verbose mode.
        /// </summary>
        /// <param name="sender">doesn't matter</param>
        /// <param name="e">used to access the scan information</param>
        private void ScanContainer_ScanArrived(object sender, MsScanEventArgs e)
        {
            IMsScanV2 scan = e.GetScan();
            if (scan == null)
            {
                string msg = "Empty scan";
                WriteLog(msg, true);
            }
            else
            {
                string msg = string.Format("Received MS Scan Number {0} -- {1} peaks",
                    scan.Header["Scan"],
                    scan.CentroidCount);
                WriteLog(msg, true);

                // try to cast scanV2 to scanV1 and dump more information
                DumpScan("Scan arrived", scan);
            }
        }

        /// <summary>
        /// Dump a scan and prepend it with an intro string.
        /// </summary>
        /// <param name="intro">string to prepend</param>
        /// <param name="scan">thing to dump</param>
        private void DumpScan(string intro, IMsScanV2 scanV2)
        {
            // dump header
            foreach (KeyValuePair<string, string> kvp in scanV2.Header)
            {
                string msg = string.Format("Header Key = {0}, Value = {1}", kvp.Key, kvp.Value);
                WriteLog(msg);
            }

            // convert v2 scan to v1 scan and try to dump more info based on the example codes
            try
            {
                using (IMsScanV1 scanV1 = (IMsScanV1)scanV2)
                {
                    StringBuilder sb = new StringBuilder();
                    sb.AppendFormat(DateTime.Now.ToString());
                    sb.Append(": ");
                    sb.Append(intro);
                    sb.Append(", ");
                    sb.Append("detector=");
                    sb.Append(scanV1.DetectorName);
                    if (scanV1.SpecificInformation.TryGetValue("Access Id:", out string id))
                    {
                        sb.Append(", id=");
                        sb.Append(id);
                    }
                    WriteLog(sb.ToString());

                    // This is rather noisy, dump all variables:
                    DumpVars(scanV1);

                    WriteLog("  Noise: ");
                    foreach (INoiseNode noise in scanV1.NoiseBand)
                    {
                        WriteLog(string.Format("[{0}, {1}], ", noise.Mz, noise.Intensity));
                    }

                    // Not so useful:
                    string msg = string.Format("{0} centroids, {1} profile peaks", scanV1.CentroidCount ?? 0, scanV1.ProfileCount ?? 0);
                    WriteLog(msg);

                    // Iterate over all centroids and access dump all profile elements for each.
                    foreach (ICentroid centroid in scanV1.Centroids)
                    {
                        msg = string.Format(" {0,10:F5}, I={1:E5}, C={2}, E={3,-5} F={4,-5} M={5,-5} R={6,-5} Res={7}",
                                            centroid.Mz, centroid.Intensity, centroid.Charge ?? -1, centroid.IsExceptional, centroid.IsFragmented, centroid.IsMerged, centroid.IsReferenced, centroid.Resolution);
                        WriteLog(msg);
                        if (scanV1.HasProfileInformation)
                        {
                            WriteLog("    Profile:");
                            try
                            {
                                foreach (IMassIntensity profilePeak in centroid.Profile)
                                {
                                    msg = string.Format(" [{0,10:F5},{1:E5}] ", profilePeak.Mz, profilePeak.Intensity);
                                    WriteLog(msg);
                                }
                            }
                            catch
                            {
                            }
                        }
                    }

                }
            }
            catch (InvalidCastException)
            {
                WriteLog("Cannot convert scanV2 to scanV1", true);
            }
        }

        /// <summary>
        /// Dump all variables belonging to a scan
        /// </summary>
        /// <param name="scan">the scan for which to dump all variables</param>
        private void DumpVars(IMsScanV1 scan)
        {
            WriteLog("  COMMON");
            DumpScanVars(scan.CommonInformation);
            WriteLog("  SPECIFIC");
            DumpScanVars(scan.SpecificInformation);
        }

        /// <summary>
        /// Dump all scan variables belonging to a specific container in a scan.
        /// </summary>
        /// <param name="container">container to dump all contained variables for</param>
        private void DumpScanVars(IInfoContainerV1 container)
        {
            foreach (string s in container.Names)
            {
                DumpVar(container, s);
            }
        }

        /// <summary>
        /// Dump the content of a single variable to the console after testing the consistency.
        /// </summary>
        /// <param name="container">container that variable belongs to</param>
        /// <param name="name">name of the variable</param>
        /// <param name="sb">buffer to be reused for speed</param>
        private void DumpVar(IInfoContainerV1 container, string name)
        {
            object o = null;
            MsScanInformationSourceV1 i = MsScanInformationSourceV1.Unknown;

            if (container.TryGetValue(name, out string s, ref i))
            {
                // i should have a reasonable value now
                if (container.TryGetRawValue(name, out o, ref i))
                {
                    string msg = string.Format("  {0}: type={1}, text='{2}', raw='{3}'",
                        name, i, s, o);
                    WriteLog(msg);
                }
            }
        }
    }
}