using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Thermo.Interfaces.FusionAccess_V1;
using Thermo.Interfaces.FusionAccess_V1.Control;
using Thermo.Interfaces.FusionAccess_V1.MsScanContainer;
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
                Console.WriteLine(msg);
            };

            // Turn on the instrument and wait until it is On
            fusionBridge.TurnOn();

            // Turn off the instrument and wait until it is Off
            fusionBridge.TurnOff();

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

        public void TurnOn()
        {
            IMode mode = InstrumentControl.Acquisition.CreateOnMode();
            InstrumentControl.Acquisition.SetMode(mode);
            while (SystemStateToString(InstrumentControl.Acquisition.State) != "On")
            {
                ;
            }
        }

        public void TurnOff()
        {
            IMode mode = InstrumentControl.Acquisition.CreateOffMode();
            InstrumentControl.Acquisition.SetMode(mode);
            while (SystemStateToString(InstrumentControl.Acquisition.State) != "Off")
            {
                ;
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

        private string SystemModeToString(IState state)
        {
            return Enum.GetName(typeof(SystemMode), state.SystemMode);
        }

        private string SystemStateToString(IState state)
        {
            return Enum.GetName(typeof(InstrumentState), state.SystemState);
        }

    }
}
