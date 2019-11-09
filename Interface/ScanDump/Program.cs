//using System;
//using IAPI_Assembly;
//using Thermo.Interfaces.FusionAccess_V1;
//using Thermo.Interfaces.FusionAccess_V1.MsScanContainer;
//using Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer;
//using Thermo.Interfaces.SpectrumFormat_V1;

//using Thermo.TNG.Factory;
//using System.Text;

using Thermo.TNG.Factory;
using Thermo.Interfaces.FusionAccess_V1;
using Thermo.Interfaces.FusionAccess_V1.MsScanContainer;
using Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer;
using System;

namespace IAPI_Console
{
    class Program
    {
        static void Main(string[] args)
        {
            // Use the Factory creation method to create a Fusion Access Container
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

            // Get the MS Scan Container from the fusion
            IFusionMsScanContainer fusionScanContainer = fusionAccess.GetMsScanContainer(0);

            // Register to MsScanArrived event
            fusionScanContainer.MsScanArrived += FusionScanContainer_MsScanArrived;
            Console.ReadLine();

        }

        private static void FusionScanContainer_MsScanArrived(object sender, MsScanEventArgs e)
        {
            Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer.IMsScan scan = e.GetScan();
            Console.WriteLine("[{0:HH:mm:ss.ffff}] Received MS Scan Number {1} -- {2} peaks",
                DateTime.Now,
                scan.Header["Scan"],
                scan.CentroidCount);

            // dump the centroids too
            foreach (ICentroid centroid in scan.Centroids)
            {
                Console.WriteLine("{0} {1}", centroid.Mz, centroid.Intensity);
            }

        }

        private void DumpScan(string intro, Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer.IMsScan scan)
        {
            StringBuilder sb = new StringBuilder();
            // sb.AppendFormat(Instrument.Now.ToString(Program.TimeFormat));
            // sb.Append(": ");
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
                string id;
                if (scan.SpecificInformation.TryGetValue("Access Id:", out id))
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

            /// <summary>
            /// Dump all variables belonging to a scan
            /// </summary>
            /// <param name="scan">the scan for which to dump all variables</param>
            void DumpVars(IMsScan scanToDump)
            {
                Console.WriteLine("  COMMON");
                DumpInfo(scanToDump.CommonInformation);
                Console.WriteLine("  SPECIFIC");
                DumpInfo(scanToDump.SpecificInformation);
            }

            /// <summary>
            /// Dump all scan variables belonging to a specific container in a scan.
            /// </summary>
            /// <param name="container">container to dump all contained variables for</param>
            void DumpInfo(IInfoContainer container)
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
            void DumpVar(IInfoContainer container, string name)
            {
                object o = null;
                string s = null;
                MsScanInformationSource i = MsScanInformationSource.Unknown;

                if (container.TryGetValue(name, out s, ref i))
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
}
