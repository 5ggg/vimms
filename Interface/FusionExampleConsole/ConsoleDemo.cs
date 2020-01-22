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
            //string debugMzML = "C:\\Users\\joewa\\University of Glasgow\\Vinny Davies - CLDS Metabolomics Project\\" +
            //    "Data\\multibeers_urine_data\\beers\\fragmentation\\mzML\\Beer_multibeers_1_T10_POS.mzML";

            string debugMzML = null;

            bool showConsoleLogs = true;

            string logDir = "C:\\Xcalibur\\data\\Joe\\logs";

            // create a new Fusion bridge
            FusionBridge fusionBridge = new FusionBridge(debugMzML, logDir, showConsoleLogs);

            // set event handler when this main process exits
            AppDomain.CurrentDomain.ProcessExit += (sender, EventArgs) =>
            {
                fusionBridge.CloseDown();
            };

            // create scan arrive user event handler
            FusionBridge.UserScanArriveDelegate userScanHandler = (IMsScan scan) =>
            {
                string runNumber = scan.Header["MasterScan"];
                string scanNumber = scan.Header["Scan"];

                fusionBridge.WriteLog(String.Format("userScanHandler (scan number={0}, runningNumber={1}) starts", 
                    scanNumber, runNumber));
                fusionBridge.WriteLog(String.Format("userScanHandler (scan number={0}, runningNumber={1}) ends",
                    scanNumber, runNumber));
            };

            // create user state changed event handler
            FusionBridge.UserStateChangedDelegate userStateChangeHandler = (IState state) =>
            {
                fusionBridge.WriteLog("userStateChangeHandler starts");
                fusionBridge.WriteLog("userStateChangeHandler ends");
            };

            // create user custom scan event handler
            double startMz = 524;
            double endMz = 526;
            double isolationWidth = 0.7;
            double collisionEnergy = 35;
            double precursorMass = startMz;
            int msLevel = 2;
            string polarity = "Positive";
            double firstMass = 50.0;
            double lastMass = 600.0;
            double singleProcessingDelay = 0.50;
            long runningNumber = 100000;
            FusionBridge.UserCreateCustomScanDelegate userCreateCustomScanHandler = () =>
            {
                fusionBridge.WriteLog("userCreateCustomScanHandler starts");
                if (precursorMass < endMz)
                {
                    precursorMass += 0.02;
                    fusionBridge.CreateCustomScan(runningNumber, precursorMass, isolationWidth, collisionEnergy, msLevel, polarity, 
                        firstMass, lastMass, singleProcessingDelay);
                    runningNumber++;
                }
                fusionBridge.WriteLog("userCreateCustomScanHandler ends");
            };

            // set all the event handlers to fusion bridge
            fusionBridge.SetEventHandlers(userScanHandler, userStateChangeHandler, userCreateCustomScanHandler);

            // send the initial custom scan
            fusionBridge.CreateCustomScan(runningNumber, precursorMass, isolationWidth, collisionEnergy, msLevel, polarity,
                firstMass, lastMass, singleProcessingDelay);
            runningNumber++;
            Console.ReadLine();

        }
    }

}
