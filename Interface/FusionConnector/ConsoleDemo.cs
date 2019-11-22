using System;
using Thermo.Interfaces.InstrumentAccess_V1.Control.Acquisition;
using Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer;

namespace FusionConnector
{
    internal class ConsoleDemo
    {
        private static void Main(string[] args)
        {
            // set to null to connect to the real machine
            string debugMzML = "C:\\Users\\joewa\\University of Glasgow\\Vinny Davies - CLDS Metabolomics Project\\" +
                "Data\\multibeers_urine_data\\beers\\fragmentation\\mzML\\Beer_multibeers_1_T10_POS.mzML";

            // create a new Fusion bridge
            FusionBridge fusionBridge = new FusionBridge(debugMzML);

            // set event handler when this main process exits
            AppDomain.CurrentDomain.ProcessExit += (sender, EventArgs) =>
            {
                fusionBridge.CloseDown();
            };

            // create scan arrive user event handler
            EventHandler<MsScanEventArgs> userScanHandler = (object sender, MsScanEventArgs e) =>
            {
                fusionBridge.WriteLog("userScanHandler is called");
            };

            // create user state changed event handler
            EventHandler<StateChangedEventArgs> userStateChangeHandler = (object sender, StateChangedEventArgs e) =>
            {
                fusionBridge.WriteLog("userStateChangeHandler is called");
            };

            // create user custom scan event handler
            double startMz = 524;
            double endMz = 524.5;
            double isolationWidth = 0.7;
            double collisionEnergy = 35;
            double precursorMass = startMz;
            EventHandler userCreateCustomScanHandler = (object sender, EventArgs e) =>
            {
                if (precursorMass < endMz)
                {
                    precursorMass += 0.02;
                    fusionBridge.CreateCustomScan(precursorMass, isolationWidth, collisionEnergy, 2);
                }
            };

            // set all the event handlers to fusion bridge
            fusionBridge.SetEventHandlers(userScanHandler, userStateChangeHandler, userCreateCustomScanHandler);

            // send the initial custom scan
            fusionBridge.CreateCustomScan(precursorMass, isolationWidth, collisionEnergy, 2);
            Console.ReadLine();

        }
    }

}
