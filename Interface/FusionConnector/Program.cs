using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Thermo.Interfaces.FusionAccess_V1;
using Thermo.Interfaces.FusionAccess_V1.Control;
using Thermo.Interfaces.FusionAccess_V1.MsScanContainer;
using Thermo.Interfaces.InstrumentAccess_V1.Control;
using Thermo.Interfaces.InstrumentAccess_V1.Control.Acquisition;
using Thermo.Interfaces.InstrumentAccess_V1.Control.Acquisition.Modes;
using Thermo.Interfaces.InstrumentAccess_V1.Control.Scans;
using Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer;
using Thermo.TNG.Factory;

namespace FusionConnector
{
    class FusionBridge
    {
        private List<string> Logs { get; set; }
        private IFusionInstrumentAccess InstrumentAccess { get; set; }
        private IFusionMsScanContainer ScanContainer { get; set; }
        private IFusionControl InstrumentControl { get; set; }
        private IScans ScanControl { get; set; }
        private long runningNumber = 100000;    // start with an offset to make sure it's "us"

        static void Main(string[] args)
        {
            Console.WriteLine("Hello World!");
            FusionBridge fusionBridge = new FusionBridge();

            // Register system mode and state changed event
            fusionBridge.InstrumentControl.Acquisition.StateChanged += (object sender, StateChangedEventArgs e) =>
            {
                IState state = e.State;
                string msg = string.Format("System mode = {0}, system state = {1}", state.SystemMode,
                    state.SystemState);
                fusionBridge.WriteLog(msg);
            };

            // Register scan arrival event handler
            fusionBridge.ScanContainer.MsScanArrived += (object sender, MsScanEventArgs e) =>
            {
                IMsScan scan = e.GetScan();
                if (scan == null)
                {
                    fusionBridge.WriteLog(string.Format("[{0:HH:mm:ss.ffff}] Empty scan", DateTime.Now));
                }
                else
                {
                    fusionBridge.WriteLog(string.Format("[{0:HH:mm:ss.ffff}] Received MS Scan Number {1} -- {2} peaks",
                    DateTime.Now,
                    scan.Header["Scan"],
                    scan.CentroidCount));
                }
            };

            // send the initial custom scan
            double startMz = 524;
            double endMz = 524.5;
            double isolationWidth = 0.7;
            double collisionEnergy = 35;

            double precursorMass = startMz;
            fusionBridge.CreateCustomScan(precursorMass, isolationWidth, collisionEnergy, 2);
            fusionBridge.ScanControl.CanAcceptNextCustomScan += (object sender, EventArgs e) =>
            {
                if (precursorMass < endMz)
                {
                    precursorMass += 0.02;
                    fusionBridge.CreateCustomScan(precursorMass, isolationWidth, collisionEnergy, 2);
                }
            };

            // https://stackoverflow.com/questions/2555292/how-to-run-code-before-program-exit
            // https://stackoverflow.com/questions/33060838/c-sharp-processexit-event-handler-not-triggering-code
            AppDomain.CurrentDomain.ProcessExit += (sender, EventArgs) =>
            {
                fusionBridge.CloseDown();
            };
            Console.ReadLine();

        }

        FusionBridge()
        {
            Logs = new List<string>();
            WriteLog("FusionBridge constructor called", true);

            //// Use the Factory creation method to create a Fusion Access Container
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
            string polarity="Positive", double firstMass=50, double lastMass=600, double singleProcessingDelay=0.50D)
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

        private void WriteLog(string msg, bool print = false)
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

            // write log files to Desktop
            string docPath = Environment.GetFolderPath(Environment.SpecialFolder.Desktop);
            string fileName = "FusionBridge_" + DateTime.Now.ToFileTime() + ".txt";
            using (StreamWriter outputFile = new StreamWriter(Path.Combine(docPath, fileName)))
            {
                foreach (string line in Logs)
                    outputFile.WriteLine(line);
            }
        }

    }
}
