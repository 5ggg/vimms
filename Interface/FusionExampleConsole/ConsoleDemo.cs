using System;
using FusionLibrary;
using Thermo.Interfaces.InstrumentAccess_V1.Control.Acquisition;
using Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer;
namespace FusionExampleConsole
{
    internal class ConsoleDemo
    {
        private static void Main(string[] args)
        {
            // set to null to connect to the real machine
            string debugMzML = "C:\\Users\\joewa\\University of Glasgow\\Vinny Davies - CLDS Metabolomics Project\\" +
                "Data\\multibeers_urine_data\\beers\\fragmentation\\mzML\\Beer_multibeers_1_T10_POS.mzML";

            bool showConsoleLogs = true;

            // create a new Fusion bridge
            FusionBridge fusionBridge = new FusionBridge(debugMzML, showConsoleLogs);

            // set event handler when this main process exits
            AppDomain.CurrentDomain.ProcessExit += (sender, EventArgs) =>
            {
                fusionBridge.CloseDown();
            };

            // create scan arrive user event handler
            FusionBridge.UserScanArriveDelegate userScanHandler = (IMsScan scan) =>
            {
                fusionBridge.WriteLog("userScanHandler is called");
            };

            // create user state changed event handler
            FusionBridge.UserStateChangedDelegate userStateChangeHandler = (IState state) =>
            {
                fusionBridge.WriteLog("userStateChangeHandler is called");
            };

            // create user custom scan event handler
            double startMz = 524;
            double endMz = 524.5;
            double isolationWidth = 0.7;
            double collisionEnergy = 35;
            double precursorMass = startMz;
            FusionBridge.UserCreateCustomScanDelegate userCreateCustomScanHandler = () =>
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
