using System;
using System.Reflection;

namespace TestLibrariesCore
{
    class Program
    {
        static void Main(string[] args)
        {
            //Assembly.Load("Thermo.TNG.Calcium.API");
            FusionBridge.FusionBridge.getIFusionInstrumentAccessContainer();
        }
    }
}
