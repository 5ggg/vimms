extern alias v2;

using System;
using System.IO;
using IAPI_Assembly;
using Thermo.Interfaces.FusionAccess_V1;
using Thermo.Interfaces.FusionAccess_V1.MsScanContainer;
using Thermo.Interfaces.SpectrumFormat_V1;
using Thermo.TNG.Factory;
using v2::Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer;

namespace mzMLReader
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
            IMsScan scan = e.GetScan();
            if (scan == null)
            {
                Console.WriteLine("[{0:HH:mm:ss.ffff}] Empty scan", DateTime.Now);
            }
            else
            {
                Console.WriteLine("[{0:HH:mm:ss.ffff}] Received MS Scan Number {1} -- {2} peaks",
                DateTime.Now,
                scan.Header["Scan"],
                scan.CentroidCount);
            }

            //foreach (ICentroid centroid in scan.Centroids)
            //{
            //    Console.WriteLine("- mz {0} intensity {1}", centroid.Mz, centroid.Intensity);
            //}
        }

    }
}
