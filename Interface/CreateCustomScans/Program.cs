extern alias v1;
extern alias v2;

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading;
using System.Globalization;

using v2::Thermo.Interfaces.InstrumentAccess_V1;
using v2::Thermo.Interfaces.InstrumentAccess_V1.Control;
using v2::Thermo.Interfaces.InstrumentAccess_V1.Control.Scans;
using Thermo.Interfaces.FusionAccess_V1;
using Thermo.TNG.Factory;
using System.IO;

namespace CreateCustomScans
{
    internal class ScansTest : IDisposable
    {
        private IScans m_scans;
        private bool m_startCustomScan = true;
        private object m_lock = new object();
        private int m_disposed;
        private long m_runningNumber = 12345;    // start with an offset to make sure it's "us"
        private int m_polarity = 0;
        private List<string> Logs { get; set; }

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

            // Dump scan output
            ScansTest scansTest = new ScansTest(fusionAccess);

            // https://stackoverflow.com/questions/2555292/how-to-run-code-before-program-exit
            // https://stackoverflow.com/questions/33060838/c-sharp-processexit-event-handler-not-triggering-code
            AppDomain.CurrentDomain.ProcessExit += (sender, EventArgs) =>
            {
                scansTest.CloseDown();
            };
            Console.ReadLine();
        }

        internal ScansTest(IFusionInstrumentAccess instrument)
        {
            WriteLog("Constructor called", true);

            m_scans = instrument.Control.GetScans(false);
            m_scans.CanAcceptNextCustomScan += new EventHandler(Scans_CanAcceptNextCustomScan);
            m_scans.PossibleParametersChanged += new EventHandler(Scans_PossibleParametersChanged);

            DumpPossibleParameters();
            bool startNewScan = false;
            lock (m_lock)
            {
                if (m_scans.PossibleParameters.Length > 0)
                {
                    startNewScan = m_startCustomScan;
                    m_startCustomScan = false;
                }
            }

            if (startNewScan)
            {
                StartNewScan();
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
            string fileName = "CreateCustomScans_" + DateTime.Now.ToFileTime() + ".txt";
            using (StreamWriter outputFile = new StreamWriter(Path.Combine(docPath, fileName)))
            {
                foreach (string line in Logs)
                    outputFile.WriteLine(line);
            }
        }

        ~ScansTest()
        {
            // Let the GC dispose managed members itself.
            Dispose(false);
        }

        /// <summary>
        /// Clean up any resources being used.
        /// </summary>
        /// <param name="disposeEvenManagedStuff">true to dispose managed and unmanaged resources; false to dispose unmanaged resources</param>
        protected void Dispose(bool disposeEvenManagedStuff)
        {
            WriteLog("Dispose called", true);
            // prevent double disposing
            if (Interlocked.Exchange(ref m_disposed, 1) != 0)
            {
                return;
            }

            if (disposeEvenManagedStuff)
            {
                if (m_scans != null)
                {
                    m_scans.CanAcceptNextCustomScan -= new EventHandler(Scans_CanAcceptNextCustomScan);
                    m_scans.PossibleParametersChanged -= new EventHandler(Scans_PossibleParametersChanged);
                    m_scans.Dispose();
                    m_scans = null;
                }
            }
        }

        /// <summary>
        /// Clean up any resources being used.
        /// </summary>
        virtual public void Dispose()
        {
            // Dispose managed and unmanaged resources and tell GC we don't need the destructor getting called.
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        /// <summary>
        /// Get access to the flag whether this object is disposed.
        /// </summary>
        internal bool Disposed { get { return m_disposed != 0; } }

        /// <summary>
        /// Dump the list of possible commands.
        /// </summary>
        private bool DumpPossibleParameters()
        {
            WriteLog("DumpPossibleParameters", true);
            IParameterDescription[] parameters = m_scans.PossibleParameters;
            if (parameters.Length == 0)
            {
                WriteLog("No possible IScans parameters known.", true);
                return false;
            }

            WriteLog("IScans parameters:");
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
            return true;
        }

        /// <summary>
        /// Start a new custom scan.
        /// </summary>
        private void StartNewScan()
        {
            WriteLog("StartNewScan called", true);

            ICustomScan cs = m_scans.CreateCustomScan();
            cs.RunningNumber = m_runningNumber++;

            // Allow an extra delay of 500 ms, we will answer as fast as possible, so this is a maximum value.
            cs.SingleProcessingDelay = 0.50D;

            // Toggle the polarity:
            m_polarity = (m_polarity == 0) ? 1 : 0;
            cs.Values["Polarity"] = m_polarity.ToString(NumberFormatInfo.InvariantInfo);

            // Dump key-value pairs in cs.Values
            foreach (KeyValuePair<string, string> kvp in cs.Values)
            {
                string msg = string.Format("cs.Values Key = {0}, Value = {1}", kvp.Key, kvp.Value);
                WriteLog(msg);
            }

            try
            {
                if (!m_scans.SetCustomScan(cs))
                {
                    WriteLog("New custom scan has not been placed, connection to service broken!!", true);
                }
                else
                {
                    WriteLog("Placed a new custom scan(" + cs.RunningNumber + ")", true);
                }
            }
            catch (Exception e)
            {
                WriteLog("Error placing a new scan: " + e.Message, true);
            }
        }

        /// <summary>
        /// Called when the current custom scan has been processed and the next custom scan can be accepted.
        /// We start a new scan.
        /// </summary>
        /// <param name="sender">doesn't matter</param>
        /// <param name="e">doesn't matter</param>
        private void Scans_CanAcceptNextCustomScan(object sender, EventArgs e)
        {
            WriteLog("Scans_CanAcceptNextCustomScan called", true);
            if ((m_scans != null) && (m_scans.PossibleParameters.Length > 0))
            {
                // Assume we are able to place a new scan.
                StartNewScan();
            }
        }

        /// <summary>
        /// Called when the list of possible commands have changed we dump them.
        /// Additionally we start a new scan.
        /// </summary>
        /// <param name="sender">doesn't matter</param>
        /// <param name="e">doesn't matter</param>
        private void Scans_PossibleParametersChanged(object sender, EventArgs e)
        {
            WriteLog("Scans_PossibleParametersChanged called", true);
            if (!DumpPossibleParameters())
            {
                return;
            }

            bool startNewScan = false;
            lock (m_lock)
            {
                if (m_scans.PossibleParameters.Length > 0)
                {
                    startNewScan = m_startCustomScan;
                    m_startCustomScan = false;
                }
            }

            if (startNewScan)
            {
                StartNewScan();
            }
        }
    }
}