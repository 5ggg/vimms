using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Thermo.Interfaces.FusionAccess_V1;
using Thermo.Interfaces.FusionAccess_V1.Control;
using Thermo.Interfaces.FusionAccess_V1.MsScanContainer;
using Thermo.Interfaces.InstrumentAccess_V1.Control;
using Thermo.Interfaces.InstrumentAccess_V1.Control.Acquisition;
using Thermo.Interfaces.InstrumentAccess_V1.Control.Scans;
using Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer;
using Thermo.TNG.Factory;

namespace FusionLibrary
{
    public class FusionBridge
    {
        // create some delegate types
        public delegate void UserScanArriveDelegate(IMsScan scan);
        public delegate void UserStateChangedDelegate(IState state);
        public delegate void UserCreateCustomScanDelegate();

        private List<string> Logs { get; set; }
        private IFusionInstrumentAccess InstrumentAccess { get; set; }
        private IFusionMsScanContainer ScanContainer { get; set; }
        private IFusionControl InstrumentControl { get; set; }
        public IScans ScanControl { get; set; }
        private long runningNumber = 100000;    // start with an offset to make sure it's "us"

        // store the user-passed callback here as delegates
        private UserScanArriveDelegate scanHandler;
        private UserStateChangedDelegate stateHandler;
        private UserCreateCustomScanDelegate customScanHandler;

        public FusionBridge(string debugMzML = null)
        {
            Logs = new List<string>();


            IFusionInstrumentAccessContainer fusionContainer = null;
            if (debugMzML != null) // create fake Fusion container that reads from mzML file
            {
                WriteLog("FusionBridge constructor called in debug mode", true);
                WriteLog(string.Format("Reading scans from {0}", debugMzML), true);
                fusionContainer = new MzMLFusionContainer(debugMzML);
            }
            else // needs license to connect to the real instrument
            {
                //// Use the Factory creation method to create a Fusion Access Container
                WriteLog("FusionBridge constructor called", true);
                fusionContainer = Factory<IFusionInstrumentAccessContainer>.Create();
            }


            // Connect to the service by going 'online'
            fusionContainer.StartOnlineAccess();

            // Wait until the service is connected 
            // (better through the event, but this is nice and simple)
            while (!fusionContainer.ServiceConnected)
            {
                ;
            }

            // From the instrument container, get access to a particular instrument
            InstrumentAccess = fusionContainer.Get(1);
            ScanContainer = InstrumentAccess.GetMsScanContainer(0);
            WriteLog("Detector class: " + ScanContainer.DetectorClass, true);

            // Dump key-value pairs in cs.Values
            WriteLog("Custom scan parameters: ");
            InstrumentControl = InstrumentAccess.Control;
            ScanControl = InstrumentControl.GetScans(false);
            ICustomScan cs = ScanControl.CreateCustomScan();
            foreach (KeyValuePair<string, string> kvp in cs.Values)
            {
                string kvpString = string.Format("cs.Values Key = {0}, Value = {1}", kvp.Key, kvp.Value);
                WriteLog(kvpString, true);
            }

            // Print instrument state
            WriteLog("FusionBridge constructor initialised", true);
            IState state = InstrumentControl.Acquisition.State;
            string msg = string.Format("System mode = {0}, system state = {1}", state.SystemMode,
                state.SystemState);
            WriteLog(msg);

        }

        public void SetEventHandlers(UserScanArriveDelegate scanArriveDelegate, 
            UserStateChangedDelegate stateChangedDelegate, UserCreateCustomScanDelegate customScanDelegate)
        {
            // if not null, save user-provided event handlers and attach the appropriate event handlers

            if (scanArriveDelegate != null)
            {
                scanHandler = scanArriveDelegate;
                ScanContainer.MsScanArrived += ScanArriveHandler;
            }
            if (stateChangedDelegate != null)
            {
                stateHandler = stateChangedDelegate;
                InstrumentControl.Acquisition.StateChanged += StateChangedHandler;
            }
            if (customScanDelegate != null)
            {
                customScanHandler = customScanDelegate;
                ScanControl.CanAcceptNextCustomScan += CreateCustomScanHandlerHandler;
            }
        }

        public void RemoveEventHandlers()
        {
            ScanContainer.MsScanArrived -= ScanArriveHandler;
            InstrumentControl.Acquisition.StateChanged -= StateChangedHandler;
            ScanControl.CanAcceptNextCustomScan -= CreateCustomScanHandlerHandler;
        }

        private void ScanArriveHandler(object sender, MsScanEventArgs e)
        {
            IMsScan scan = e.GetScan();
            if (scan == null)
            {
                WriteLog("Empty scan", true);
            }
            else
            {
                WriteLog(string.Format("Received MS Scan Number {0} -- {1} peaks",
                scan.Header["Scan"],
                scan.CentroidCount), true);

                // dump header
                foreach (KeyValuePair<string, string> kvp in scan.Header)
                {
                    string msg = string.Format("- Header Key = {0}, Value = {1}", kvp.Key, kvp.Value);
                    WriteLog(msg);
                }
            }

            // run user scan event handler
            scanHandler(scan);
        }

        private void StateChangedHandler(object sender, StateChangedEventArgs e)
        {
            IState state = e.State;
            string msg = string.Format("System mode = {0}, system state = {1}", state.SystemMode,
                state.SystemState);
            WriteLog(msg, true);

            // run user state changed handler
            stateHandler(state);
        }

        private void CreateCustomScanHandlerHandler(object sender, EventArgs e)
        {
            WriteLog("UserCreateCustomScan starts", true);
            customScanHandler();
            WriteLog("UserCreateCustomScan ends", true);
        }

        public void DumpPossibleParameters()
        {
            WriteLog("DumpPossibleParameters", true);
            IParameterDescription[] parameters = ScanControl.PossibleParameters;
            if (parameters.Length == 0)
            {
                WriteLog("No possible IScans parameters known.", true);
            }

            WriteLog("ScanControl parameters:");
            foreach (IParameterDescription parameter in parameters)
            {
                StringBuilder sb = new StringBuilder();
                sb.AppendFormat("   '{0}' ", parameter.Name);
                if (parameter.Selection == "")
                {
                    sb.AppendFormat("doesn't accept an argument, help: {0}", parameter.Help);
                }
                else
                {
                    sb.AppendFormat("accepts '{0}', default='{1}', help: {2}", parameter.Selection, parameter.DefaultValue, parameter.Help);
                }
                WriteLog(sb.ToString());
            }
        }

        public void CreateCustomScan(double precursorMass, double isolationWidth, double collisionEnergy, int msLevel,
            string polarity = "Positive", double firstMass = 50, double lastMass = 600, double singleProcessingDelay = 0.50D)
        {
            WriteLog("StartNewScan called", true);
            if (ScanControl.PossibleParameters.Length > 0)
            {
                ICustomScan cs = ScanControl.CreateCustomScan();
                cs.RunningNumber = runningNumber++;

                // Allow an extra delay of 500 ms, we will answer as fast as possible, so this is a maximum value.
                cs.SingleProcessingDelay = singleProcessingDelay;

                // Set the custom scan parameters
                cs.Values["CollisionEnergy"] = collisionEnergy.ToString();
                cs.Values["FirstMass"] = firstMass.ToString();
                cs.Values["LastMass"] = lastMass.ToString();
                cs.Values["Analyzer"] = "Orbitrap";
                cs.Values["Polarity"] = polarity;
                if (msLevel == 1)
                {
                    cs.Values["ScanType"] = "Full";
                    cs.Values["IsolationWidth"] = "0.7";
                    cs.Values["PrecursorMass"] = "";
                    cs.Values["OrbitrapResolution"] = "120000";
                }
                else
                {
                    cs.Values["ScanType"] = "MSn";
                    cs.Values["IsolationWidth"] = isolationWidth.ToString();
                    cs.Values["PrecursorMass"] = precursorMass.ToString();
                    cs.Values["OrbitrapResolution"] = "7500";
                }
                cs.Values["ActivationType"] = "HCD";
                cs.Values["DataType"] = "Centroid";
                cs.Values["AGCTarget"] = "30000";
                cs.Values["MaxIT"] = "100";
                cs.Values["Microscans"] = "3";

                // Dump key-value pairs in cs.Values
                foreach (KeyValuePair<string, string> kvp in cs.Values)
                {
                    string msg = string.Format("- cs.Values Key = {0}, Value = {1}", kvp.Key, kvp.Value);
                    WriteLog(msg);
                }

                try
                {
                    if (!ScanControl.SetCustomScan(cs))
                    {
                        WriteLog("New custom scan has not been placed, connection to service broken!!", true);
                    }
                    else
                    {
                        WriteLog("Placed a new custom scan(" + cs.RunningNumber + ") for precursor mz=" + cs.Values["PrecursorMass"], true);
                    }
                }
                catch (Exception e)
                {
                    WriteLog("Error placing a new scan: " + e.Message, true);
                }
            }
            else
            {
                WriteLog("New custom scan has not been placed, no parameters available!!", true);
            }
        }

        public void WriteLog(string msg, bool print = false)
        {
            string msgWithTimestamp = string.Format("[{0:HH:mm:ss.ffff}] {1}", DateTime.Now, msg);
            Logs.Add(msgWithTimestamp);
            if (print)
            {
                Console.WriteLine(msgWithTimestamp);
            }
        }

        public void CloseDown()
        {
            if (Logs.Count > 0)
            {
                WriteLog("Removing event handlers", true);
                RemoveEventHandlers();

                WriteLog("Goodbye Cruel World", true);

                // write log files to Desktop
                string docPath = Environment.GetFolderPath(Environment.SpecialFolder.Desktop);
                string fileName = "FusionBridge_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".txt";
                using (StreamWriter outputFile = new StreamWriter(Path.Combine(docPath, fileName)))
                {
                    foreach (string line in Logs)
                    {
                        outputFile.WriteLine(line);
                    }
                    Logs.Clear();
                }
            }
        }

    }
}
