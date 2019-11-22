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

namespace FusionConnector
{
    public class FusionBridge
    {
        private List<string> Logs { get; set; }
        private IFusionInstrumentAccess InstrumentAccess { get; set; }
        private IFusionMsScanContainer ScanContainer { get; set; }
        private IFusionControl InstrumentControl { get; set; }
        public IScans ScanControl { get; set; }
        private long runningNumber = 100000;    // start with an offset to make sure it's "us"

        private EventHandler<MsScanEventArgs> UserScanArriveHandler { get; set; }
        private EventHandler<StateChangedEventArgs> UserStateChangedHandler { get; set; }
        private EventHandler UserCreateCustomScanHandler { get; set; }

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

        public void SetEventHandlers(EventHandler<MsScanEventArgs> userScanArriveHandler, EventHandler<StateChangedEventArgs> userStateChangeHandler,
            EventHandler userCreateCustomScanHandler)
        {
            // if not null, save user-provided event handlers and attach the appropriate event handlers

            if (userScanArriveHandler != null)
            {
                UserScanArriveHandler = userScanArriveHandler;
                ScanContainer.MsScanArrived += ScanArriveHandler;
            }
            if (userStateChangeHandler != null)
            {
                UserStateChangedHandler = userStateChangeHandler;
                InstrumentControl.Acquisition.StateChanged += StateChangedHandler;
            }
            if (userCreateCustomScanHandler != null)
            {
                UserCreateCustomScanHandler = userCreateCustomScanHandler;
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
                WriteLog(string.Format("[{0:HH:mm:ss.ffff}] Empty scan", DateTime.Now), true);
            }
            else
            {
                WriteLog(string.Format("[{0:HH:mm:ss.ffff}] Received MS Scan Number {1} -- {2} peaks",
                DateTime.Now,
                scan.Header["Scan"],
                scan.CentroidCount), true);
            }

            // run user scan event handler
            UserScanArriveHandler(sender, e);
        }

        private void StateChangedHandler(object sender, StateChangedEventArgs e)
        {
            IState state = e.State;
            string msg = string.Format("System mode = {0}, system state = {1}", state.SystemMode,
                state.SystemState);
            WriteLog(msg, true);

            // run user state changed handler
            UserStateChangedHandler(sender, e);
        }

        private void CreateCustomScanHandlerHandler(object sender, EventArgs e)
        {
            WriteLog("UserCreateCustomScan starts", true);
            UserCreateCustomScanHandler(sender, e);
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
                    cs.Values["IsolationWidth"] = "0.7"; // default
                    cs.Values["PrecursorMass"] = ""; // default
                }
                else
                {
                    cs.Values["ScanType"] = "MSn";
                    cs.Values["IsolationWidth"] = isolationWidth.ToString();
                    cs.Values["PrecursorMass"] = precursorMass.ToString();
                }
                cs.Values["DataType"] = "Centroid";

                // Dump key-value pairs in cs.Values
                foreach (KeyValuePair<string, string> kvp in cs.Values)
                {
                    string msg = string.Format("cs.Values Key = {0}, Value = {1}", kvp.Key, kvp.Value);
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
            WriteLog("Removing event handlers", true);
            RemoveEventHandlers();

            WriteLog("Goodbye Cruel World", true);

            // write log files to Desktop
            string docPath = Environment.GetFolderPath(Environment.SpecialFolder.Desktop);
            string fileName = "FusionBridge_" + DateTime.Now.ToFileTime() + ".txt";
            using (StreamWriter outputFile = new StreamWriter(Path.Combine(docPath, fileName)))
            {
                foreach (string line in Logs)
                {
                    outputFile.WriteLine(line);
                }
            }
        }

    }
}
