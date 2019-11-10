extern alias v1;
extern alias v2;
using System;
using System.Text;
using Thermo.Interfaces.FusionAccess_V1;
using Thermo.Interfaces.FusionAccess_V1.MsScanContainer;
using Thermo.Interfaces.SpectrumFormat_V1;
using Thermo.TNG.Factory;
using v2::Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer;
using IInfoContainerV1 = v1::Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer.IInfoContainer;
using IMsScanV1 = v1::Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer.IMsScan;
using MsScanInformationSourceV1 = v1::Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer.MsScanInformationSource;

// using ICentroid = v2::Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer.ICentroid;

namespace ScanDump
{
    /// <summary>
    /// This class presents the output of the scans being acquired by the instrument.
    /// </summary>
    internal class ScansOutput
    {
        static void Main(string[] args)
        {
            // Use the Factory creation method to create a Fusion Access Container
            IFusionInstrumentAccessContainer fusionContainer = Factory<IFusionInstrumentAccessContainer>.Create();

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

        }

        /// <summary>
        /// Crate a new <see cref="ScansOutput"/>
        /// </summary>
        /// <param name="instrument">the instrument instance</param>
        private ScansOutput(IFusionInstrumentAccess instrument)
        {
            ScanContainer = instrument.GetMsScanContainer(0);
            Console.WriteLine("Detector class: " + ScanContainer.DetectorClass);

            //ScanContainer.AcquisitionStreamOpening += new EventHandler<MsAcquisitionOpeningEventArgs>(ScanContainer_AcquisitionStarted);
            //ScanContainer.AcquisitionStreamClosing += new EventHandler(ScanContainer_AcquisitionEnded);
            ScanContainer.MsScanArrived += new EventHandler<MsScanEventArgs>(ScanContainer_ScanArrived);
        }

        /// <summary>
        /// Show the last acquired scan if that exists and cleanup.
        /// </summary>
        private void CloseDown()
        {
            // Be tolerant to thread-switches
            IFusionMsScanContainer scanContainer = ScanContainer;
            ScanContainer = null;

            if (scanContainer != null)
            {
                scanContainer.MsScanArrived -= new EventHandler<MsScanEventArgs>(ScanContainer_ScanArrived);
                //scanContainer.AcquisitionStreamClosing -= new EventHandler(ScanContainer_AcquisitionEnded);
                //scanContainer.AcquisitionStreamOpening -= new EventHandler<MsAcquisitionOpeningEventArgs>(ScanContainer_AcquisitionStarted);
                using (IMsScanV1 scan = (/* V2 */ IMsScanV1)scanContainer.GetLastMsScan())
                {
                    DumpScan("GetLastScan()", scan);
                }
            }
        }

        /// <summary>
        /// Access to the scan container hosted by this instance.
        /// </summary>
        private IFusionMsScanContainer ScanContainer { get; set; }

        /// <summary>
        /// When a new acquisition starts we dump that information.
        /// </summary>
        /// <param name="sender">doesn't matter</param>
        /// <param name="e">doesn't matter</param>
        //private void ScanContainer_AcquisitionStarted(object sender, EventArgs e)
        //{
        //    Console.WriteLine("START OF ACQUISITION");
        //}

        /// <summary>
        /// When an acquisitions ends we dump that information.
        /// </summary>
        /// <param name="sender">doesn't matter</param>
        /// <param name="e">doesn't matter</param>
        //private void ScanContainer_AcquisitionEnded(object sender, EventArgs e)
        //{
        //    Console.WriteLine("END OF ACQUISITION");
        //}

        /// <summary>
        /// When a new scan arrives we dump that information in verbose mode.
        /// </summary>
        /// <param name="sender">doesn't matter</param>
        /// <param name="e">used to access the scan information</param>
        private void ScanContainer_ScanArrived(object sender, MsScanEventArgs e)
        {
            Console.WriteLine("Scan arrived");
            // As an example we access all centroids
            using (IMsScanV1 scan = (/* V2 */ IMsScanV1)e.GetScan())
            {
                DumpScan("Scan arrived", scan);
            }
        }

        /// <summary>
        /// Dump a scan and prepend it with an intro string.
        /// </summary>
        /// <param name="intro">string to prepend</param>
        /// <param name="scan">thing to dump</param>
        private void DumpScan(string intro, IMsScanV1 scan)
        {
            StringBuilder sb = new StringBuilder();
            sb.AppendFormat(DateTime.Now.ToString());
            sb.Append(": ");
            sb.Append(intro);
            sb.Append(", ");
            if (scan == null)
            {
                sb.Append("(empty scan)");
                Console.WriteLine(sb.ToString());
                return;
            }
            else
            {
                sb.Append("detector=");
                sb.Append(scan.DetectorName);
                if (scan.SpecificInformation.TryGetValue("Access Id:", out string id))
                {
                    sb.Append(", id=");
                    sb.Append(id);
                }
                Console.WriteLine(sb.ToString());
            }

            // This is rather noisy, dump all variables:
            DumpVars(scan);

            Console.Write("  Noise: ");
            foreach (INoiseNode noise in scan.NoiseBand)
            {
                Console.Write("[{0}, {1}], ", noise.Mz, noise.Intensity);
            }
            Console.WriteLine();

            // Not so useful:
            Console.WriteLine("{0} centroids, {1} profile peaks", scan.CentroidCount ?? 0, scan.ProfileCount ?? 0);

            // Iterate over all centroids and access dump all profile elements for each.
            foreach (ICentroid centroid in scan.Centroids)
            {
                Console.WriteLine(" {0,10:F5}, I={1:E5}, C={2}, E={3,-5} F={4,-5} M={5,-5} R={6,-5} Res={7}",
                                    centroid.Mz, centroid.Intensity, centroid.Charge ?? -1, centroid.IsExceptional, centroid.IsFragmented, centroid.IsMerged, centroid.IsReferenced, centroid.Resolution);
                if (scan.HasProfileInformation)
                {
                    Console.Write("    Profile:");
                    try
                    {
                        foreach (IMassIntensity profilePeak in centroid.Profile)
                        {
                            Console.Write(" [{0,10:F5},{1:E5}] ", profilePeak.Mz, profilePeak.Intensity);
                        }
                    }
                    catch
                    {
                    }
                    Console.WriteLine();
                }
            }
        }

        /// <summary>
        /// Dump all variables belonging to a scan
        /// </summary>
        /// <param name="scan">the scan for which to dump all variables</param>
        private void DumpVars(IMsScanV1 scan)
        {
            Console.WriteLine("  COMMON");
            DumpScanVars(scan.CommonInformation);
            Console.WriteLine("  SPECIFIC");
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
                    Console.WriteLine("  {0}: type={1}, text='{2}', raw='{3}'",
                        name, i, s, o);
                }
            }
        }
    }
}