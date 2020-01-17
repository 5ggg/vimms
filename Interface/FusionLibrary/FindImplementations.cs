using System;
using System.Collections.Generic;
using System.ComponentModel.Composition;
using System.ComponentModel.Composition.Hosting;
using Thermo.Interfaces.FusionAccess_V1;
using Thermo.TNG.Factory;

namespace FusionLibrary
{
    public class FindImplementations<T> where T:class
    {

		private static object _lockObj = new object();

		private static CompositionContainer _container = null;


		public FindImplementations()
        {
			IFusionInstrumentAccessContainer fusionContainer = FindImplementations<IFusionInstrumentAccessContainer>.Create();
		}

		public static T Create(params object[] args)
		{
			lock (_lockObj)
			{
				try
				{
					GetContainer();
					Parts<T> parts = new Parts<T>();
					_container.ComposeParts(parts);
					List<T> list = new List<T>();
					foreach (Lazy<T> item in parts.TContainer)
					{
						IInstrumentSupport instrumentSupport = item.Value as IInstrumentSupport;
						if (instrumentSupport != null)
						{
							if (instrumentSupport.IsSupported(RegistryHelper.GetServerModel(), RegistryHelper.GetServerVersion()))
							{
								return item.Value;
							}
						}
						else
						{
							list.Add(item.Value);
						}
					}
					if (list.Count > 0)
					{
						return list[0];
					}
				}
				catch (CompositionException)
				{
					throw;
				}
				throw new FactoryException("Implementation not found for " + typeof(T).ToString());
			}
		}


		private static void GetContainer()
		{
			if (_container == null)
			{
				string programPath = RegistryHelper.GetProgramPath(RegistryHelper.GetServerModel(), RegistryHelper.GetServerVersion());
				AggregateCatalog aggregateCatalog = new AggregateCatalog();
				aggregateCatalog.Catalogs.Add(new DirectoryCatalog(programPath, "*API.dll"));
				aggregateCatalog.Catalogs.Add(new DirectoryCatalog(programPath, "*Client*.dll"));
				aggregateCatalog.Catalogs.Add(new DirectoryCatalog(programPath, "*Export*.dll"));
				_container = new CompositionContainer(aggregateCatalog);
			}
		}

		static public void Main(String[] args)
		{

			new FindImplementations<IFusionInstrumentAccessContainer>();
		}
	}


}

