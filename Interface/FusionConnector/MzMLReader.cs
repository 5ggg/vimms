using PSI_Interface.MSData;
using System;
using System.Linq;
using Thermo.Interfaces.FusionAccess_V1;
using Thermo.Interfaces.FusionAccess_V1.MsScanContainer;
using Thermo.Interfaces.InstrumentAccess_V1.MsScanContainer;
using Thermo.Interfaces.FusionAccess_V1.Control;
using Thermo.Interfaces.InstrumentAccess_V1;
using Thermo.Interfaces.InstrumentAccess_V1.AnalogTraceContainer;
using Thermo.Interfaces.InstrumentAccess_V1.Control;
using System.Collections.Generic;
using static PSI_Interface.MSData.SimpleMzMLReader;
using Thermo.Interfaces.SpectrumFormat_V1;
using System.Threading.Tasks;
using Thermo.Interfaces.FusionAccess_V1.Control.Peripherals;
using Thermo.Interfaces.InstrumentAccess_V1.Control.Acquisition;
using Thermo.Interfaces.InstrumentAccess_V1.Control.InstrumentValues;
using Thermo.Interfaces.InstrumentAccess_V1.Control.Methods;
using Thermo.Interfaces.InstrumentAccess_V1.Control.Scans;
using Thermo.Interfaces.InstrumentAccess_V1.Control.Acquisition.Modes;
using Thermo.Interfaces.InstrumentAccess_V1.Control.Acquisition.Workflow;

namespace FusionConnector
{
    public class MzMLFusionContainer : IFusionInstrumentAccessContainer
    {

        private readonly string filename;
        private readonly IEnumerable<SimpleSpectrum> _spectra;
        public bool ServiceConnected { get; } = true;
        public event EventHandler ServiceConnectionChanged;
        public event EventHandler<MessagesArrivedEventArgs> MessagesArrived;

        public MzMLFusionContainer(string filename)
        {
            this.filename = filename;
            Console.WriteLine("filename is " + filename);
            if (filename != null)
            {
                SimpleMzMLReader reader = new SimpleMzMLReader(filename);
                Console.WriteLine("NumSpectra = " + reader.NumSpectra);
                _spectra = reader.ReadAllSpectra();
            }
        }

        public void Dispose()
        {
            throw new NotImplementedException();
        }

        public IFusionInstrumentAccess Get(int index)
        {
            return new FusionAccess(_spectra);
        }

        public void StartOnlineAccess()
        {
            Console.WriteLine("Going online!");
        }

        IInstrumentAccess IInstrumentAccessContainer.Get(int index)
        {
            throw new NotImplementedException();
        }
    }

    class FusionAccess : IFusionInstrumentAccess
    {
        private IEnumerable<SimpleSpectrum> _spectra;

        public FusionAccess(IEnumerable<SimpleSpectrum> spectra)
        {
            _spectra = spectra;
        }

        public int InstrumentId => throw new NotImplementedException();

        public string InstrumentName => throw new NotImplementedException();

        public bool Connected => throw new NotImplementedException();

        public int CountMsDetectors => throw new NotImplementedException();

        public string[] DetectorClasses => throw new NotImplementedException();

        public int CountAnalogChannels => throw new NotImplementedException();

        public IFusionControl Control => new InstrumentControl();

        IControl IInstrumentAccess.Control => throw new NotImplementedException();

        public event EventHandler<ContactClosureEventArgs> ContactClosureChanged;
        public event EventHandler ConnectionChanged;
        public event EventHandler<AcquisitionErrorsArrivedEventArgs> AcquisitionErrorsArrived;

        public IAnalogTraceContainer GetAnalogTraceContainer(int analogDetectorSet)
        {
            throw new NotImplementedException();
        }

        public IFusionMsScanContainer GetMsScanContainer(int msDetectorSet)
        {
            return new ScanContainer(_spectra);
        }

        IMsScanContainer IInstrumentAccess.GetMsScanContainer(int msDetectorSet)
        {
            return new ScanContainer(_spectra);
        }
    }

    class InstrumentControl : IFusionControl
    {
        public ISyringePumpControl SyringePumpControl => throw new NotImplementedException();

        public IInstrumentValues InstrumentValues => throw new NotImplementedException();

        public IMethods Methods => throw new NotImplementedException();

        public IAcquisition Acquisition => new InstrumentControlAcquisition();

        public IScans GetScans(bool exclusiveAccess)
        {
            return new ScanControl();
        }
    }

    class InstrumentControlAcquisition : IAcquisition
    {
        public IState State => new MyAcquisitionState();

        public bool CanPause => throw new NotImplementedException();

        public bool CanResume => throw new NotImplementedException();

        public event EventHandler<StateChangedEventArgs> StateChanged;
        public event EventHandler<AcquisitionOpeningEventArgs> AcquisitionStreamOpening;
        public event EventHandler AcquisitionStreamClosing;

        public void CancelAcquisition()
        {
            throw new NotImplementedException();
        }

        public IAcquisitionLimitedByCount CreateAcquisitionLimitedByCount(int count)
        {
            throw new NotImplementedException();
        }

        public IAcquisitionLimitedByTime CreateAcquisitionLimitedByDuration(TimeSpan duration)
        {
            throw new NotImplementedException();
        }

        public IForcedOffMode CreateForcedOffMode()
        {
            throw new NotImplementedException();
        }

        public IForcedStandbyMode CreateForcedStandbyMode()
        {
            throw new NotImplementedException();
        }

        public IAcquisitionMethodRun CreateMethodAcquisition(string methodFileName)
        {
            throw new NotImplementedException();
        }

        public IAcquisitionMethodRun CreateMethodAcquisition(string methodFileName, TimeSpan duration)
        {
            throw new NotImplementedException();
        }

        public IOffMode CreateOffMode()
        {
            throw new NotImplementedException();
        }

        public IOnMode CreateOnMode()
        {
            throw new NotImplementedException();
        }

        public IAcquisitionWorkflow CreatePermanentAcquisition()
        {
            throw new NotImplementedException();
        }

        public IStandbyMode CreateStandbyMode()
        {
            throw new NotImplementedException();
        }

        public void Pause()
        {
            throw new NotImplementedException();
        }

        public void Resume()
        {
            throw new NotImplementedException();
        }

        public void SetMode(IMode newMode)
        {
            throw new NotImplementedException();
        }

        public void StartAcquisition(IAcquisitionWorkflow acquisition)
        {
            throw new NotImplementedException();
        }

        public bool WaitFor(TimeSpan duration, Func<InstrumentState, SystemMode, bool> continuation)
        {
            throw new NotImplementedException();
        }
    }

    class MyAcquisitionState : IState
    {
        public SystemMode SystemMode => SystemMode.On;

        public InstrumentState SystemState => InstrumentState.ReadyToDownload;
    }

    class ScanControl : IScans
    {
        public IParameterDescription[] PossibleParameters => new MyParameterDescription[3];
        public List<ICustomScan> placedCustomScans = new List<ICustomScan>();

        public ScanControl()
        {
            PossibleParameters[0] = new MyParameterDescription("CollisionEnergy", "string (0;200)", "", "The normalized collision " +
                "energy (NCE) It is expressed as a string of values, with each value sepearted by a ';' delimiter. A maximum of 10 values can be defined.");
            PossibleParameters[1] = new MyParameterDescription("ScanRate", "Normal,Enchanced,Zoom,Rapid,Turbo", "Normal", "The scan rate of the ion trap");
            PossibleParameters[2] = new MyParameterDescription("FirstMass", "string (50;2000)", "150", "The first mass of the scan range. It is expressed as " +
                "a string of values, with each value sepearted by a ';' delimiter. A maximum of 10 values can be defined.");
        }

        public event EventHandler PossibleParametersChanged;
        public event EventHandler CanAcceptNextCustomScan;

        public bool CancelCustomScan()
        {
            throw new NotImplementedException();
        }

        public bool CancelRepetition()
        {
            throw new NotImplementedException();
        }

        public ICustomScan CreateCustomScan()
        {
            return new MyCustomScan();
        }

        public IRepeatingScan CreateRepeatingScan()
        {
            throw new NotImplementedException();
        }

        public void Dispose()
        {
            throw new NotImplementedException();
        }

        public bool SetCustomScan(ICustomScan scan)
        {
            placedCustomScans.Add(scan);
            int milliSecondDelay = (int) 0.25 * 1000;
            Task.Delay(milliSecondDelay).ContinueWith(t => OnSingleProcessingDelay());
            return true;
        }

        private void OnSingleProcessingDelay()
        {
            EventHandler handler = CanAcceptNextCustomScan;
            if (handler != null)
            {
                handler(this, null);
            }
        }

        public bool SetRepetitionScan(IRepeatingScan scan)
        {
            throw new NotImplementedException();
        }
    }

    internal class MyParameterDescription : IParameterDescription
    {
        public MyParameterDescription(string _name, string _selection, string _defaultValue, string _help)
        {
            Name = _name;
            Selection = _selection;
            DefaultValue = _defaultValue;
            Help = _help;
        }

        public string Name { get; }

        public string Selection { get; }

        public string DefaultValue { get; }

        public string Help { get; }
    }

    class MyCustomScan : ICustomScan
    {
        public double SingleProcessingDelay { get; set; } = 0;

        public IDictionary<string, string> Values { get; } = new Dictionary<string, string>();

        public long RunningNumber { get; set; } = 1;
    }

    class ScanContainer : IFusionMsScanContainer
    {
        private SimpleSpectrum[] spectra;
        private IMsScan lastScan;

        public ScanContainer(IEnumerable<SimpleSpectrum> spectra)
        {
            this.spectra = spectra.ToArray();
            for (int i = 0; i < this.spectra.Length; i++)
            {
                // schedule events to be triggered, see https://stackoverflow.com/questions/545533/delayed-function-calls
                SimpleSpectrum current = this.spectra[i];
                int elutionTimeInMilliSecond = (int)(current.ScanStartTime * 60 * 1000);
                IMsScan msScan = new MyMsScan(current);
                MsScanEventArgs args = new MyMsScanEventArgs(msScan);
                Task.Delay(elutionTimeInMilliSecond).ContinueWith(t => OnMsScanArrived(args));
                this.lastScan = msScan;
            }
        }

        protected virtual void OnMsScanArrived(MsScanEventArgs e)
        {
            EventHandler<MsScanEventArgs> handler = MsScanArrived;
            if (handler != null)
            {
                handler(this, e);
            }
        }

        public string DetectorClass => "No detector";

        public event EventHandler<MsScanEventArgs> MsScanArrived;

        public IMsScan GetLastMsScan()
        {
            return this.lastScan;
        }
    }

    class MyMsScanEventArgs : MsScanEventArgs
    {
        private IMsScan msScan;

        public MyMsScanEventArgs(IMsScan msScan)
        {
            this.msScan = msScan;
        }

        public override IMsScan GetScan()
        {
            return this.msScan;
        }
    }

    class MyMsScan : IMsScan
    {
        public IDictionary<string, string> Header { get; } = new Dictionary<string, string>();

        public IInformationSourceAccess TuneData => throw new NotImplementedException();

        public IInformationSourceAccess Trailer => throw new NotImplementedException();

        public IInformationSourceAccess StatusLog => throw new NotImplementedException();

        public string DetectorName => throw new NotImplementedException();

        public int? NoiseCount => throw new NotImplementedException();

        public IEnumerable<INoiseNode> NoiseBand => throw new NotImplementedException();

        public int? CentroidCount { get; } = 0;

        public IEnumerable<ICentroid> Centroids { get; }

        public IChargeEnvelope[] ChargeEnvelopes => throw new NotImplementedException();

        #region IDisposable Support
        private bool disposedValue = false; // To detect redundant calls

        public MyMsScan(SimpleSpectrum scan)
        {
            this.Header["Scan"] = scan.ScanNumber.ToString();
            List<ICentroid> myList = new List<ICentroid>();
            if (scan.Centroided)
            {
                this.CentroidCount = scan.Mzs.Length;
                foreach (Peak p in scan.Peaks)
                {
                    ICentroid centroid = new MyCentroid(p);
                    myList.Add(centroid);
                }
                this.Centroids = myList;
            }
        }

        protected virtual void Dispose(bool disposing)
        {
            if (!disposedValue)
            {
                if (disposing)
                {
                    // TODO: dispose managed state (managed objects).
                }

                // TODO: free unmanaged resources (unmanaged objects) and override a finalizer below.
                // TODO: set large fields to null.

                disposedValue = true;
            }
        }

        // TODO: override a finalizer only if Dispose(bool disposing) above has code to free unmanaged resources.
        // ~MyMsScan() {
        //   // Do not change this code. Put cleanup code in Dispose(bool disposing) above.
        //   Dispose(false);
        // }

        // This code added to correctly implement the disposable pattern.
        public void Dispose()
        {
            // Do not change this code. Put cleanup code in Dispose(bool disposing) above.
            Dispose(true);
            // TODO: uncomment the following line if the finalizer is overridden above.
            // GC.SuppressFinalize(this);
        }
        #endregion

    }

    class MyCentroid : ICentroid
    {
        public MyCentroid(Peak p)
        {
            this.Mz = p.Mz;
            this.Intensity = p.Intensity;
        }

        public bool? IsExceptional => throw new NotImplementedException();

        public bool? IsReferenced => throw new NotImplementedException();

        public bool? IsMerged => throw new NotImplementedException();

        public bool? IsFragmented => throw new NotImplementedException();

        public int? Charge => throw new NotImplementedException();

        public IMassIntensity[] Profile => throw new NotImplementedException();

        public double? Resolution => throw new NotImplementedException();

        public int? ChargeEnvelopeIndex => throw new NotImplementedException();

        public bool? IsMonoisotopic => throw new NotImplementedException();

        public bool? IsClusterTop => throw new NotImplementedException();

        public double Mz { get; }

        public double Intensity { get; }
    }

}
