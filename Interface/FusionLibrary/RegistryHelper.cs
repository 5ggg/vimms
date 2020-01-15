using System;
using System.Collections.Generic;
using System.Diagnostics;
using Microsoft.Win32;

internal static class RegistryHelper
{
	private const RegistryHive registryHive = RegistryHive.LocalMachine;

	private const string registryKeyTNG = "Software\\Thermo Instruments\\TNG\\";

	private const string registryKeyServerModel = "InstrumentServerModel";

	private const string registryKeyServerVersion = "InstrumentServerVersion";

	private const string registryKeyProgramsPath = "ProgramPath";

	private const string registryKeyInstallType = "InstallType";

	public static List<string> GetInstrunmentModels()
	{
		return GetSubKeyNames("Software\\Thermo Instruments\\TNG\\");
	}

	public static List<string> GetModelVersions(string instrumentModel, bool throwException = false)
	{
		string registrySubKey = GetRegistrySubKey(instrumentModel);
		List<string> subKeyNames = GetSubKeyNames(registrySubKey);
		if (subKeyNames.Count == 0 && throwException)
		{
			Trace.WriteLine("Registry key (" + registrySubKey + ") not found. " + instrumentModel + " is not installed on this machine.");
			throw new FactoryException("Registry key (" + registrySubKey + ") not found. " + instrumentModel + " is not installed on this machine.");
		}
		return subKeyNames;
	}

	public static List<string> GetFullInstalledVersions(string instrumentModel)
	{
		List<string> retVal = new List<string>();
		List<string> modelVersions = GetModelVersions(instrumentModel);
		modelVersions.ForEach((Action<string>)delegate (string o)
		{
			if (IsFullInstall(instrumentModel, o))
			{
				retVal.Add(o);
			}
		});
		return retVal;
	}

	public static string GetProgramPath(string instrumentModel, string version)
	{
		string text = GetRegistrySubKey(instrumentModel) + "\\" + version;
		string subKeyValue = GetSubKeyValue(text, "ProgramPath");
		if (string.IsNullOrWhiteSpace(subKeyValue))
		{
			Trace.WriteLine("Registry key (" + text + ") not found. " + instrumentModel + " is not installed on this machine.");
			throw new FactoryException("Registry key (" + text + ") not found. " + instrumentModel + " is not installed on this machine.");
		}
		return subKeyValue;
	}

	public static bool IsFullInstall(string instrumentModel, string version)
	{
		string subKey = GetRegistrySubKey(instrumentModel) + "\\" + version;
		string subKeyValue = GetSubKeyValue(subKey, "InstallType");
		if (string.IsNullOrWhiteSpace(subKeyValue))
		{
			return false;
		}
		return subKeyValue == "Full";
	}

	public static string GetServerModel()
	{
		return GetSubKeyValue("Software\\Thermo Instruments\\TNG\\", "InstrumentServerModel");
	}

	public static string GetServerVersion()
	{
		return GetSubKeyValue("Software\\Thermo Instruments\\TNG\\", "InstrumentServerVersion");
	}

	public static bool IsServer(string instrumentModel, string version)
	{
		if (instrumentModel == GetServerModel())
		{
			return version == GetServerVersion();
		}
		return false;
	}

	private static string GetRegistrySubKey(string instrumentModel)
	{
		return "Software\\Thermo Instruments\\TNG\\" + instrumentModel;
	}

	private static string GetSubKeyValue(string subKey, string subValueKey)
	{
		string subKeyValue = GetSubKeyValue(RegistryView.Default, subKey, subValueKey);
		if (string.IsNullOrWhiteSpace(subKeyValue))
		{
			subKeyValue = GetSubKeyValue(RegistryView.Registry64, subKey, subValueKey);
			if (string.IsNullOrWhiteSpace(subKeyValue))
			{
				subKeyValue = GetSubKeyValue(RegistryView.Registry32, subKey, subValueKey);
			}
		}
		return subKeyValue;
	}

	private static string GetSubKeyValue(RegistryView rv, string subKey, string subValueKey)
	{
		string result = string.Empty;
		RegistryKey registryKey = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, rv);
		registryKey = registryKey.OpenSubKey(subKey);
		if (registryKey != null)
		{
			result = registryKey.GetValue(subValueKey, string.Empty).ToString();
		}
		return result;
	}

	private static List<string> GetSubKeyNames(string subKey)
	{
		List<string> subKeyNames = GetSubKeyNames(RegistryView.Default, subKey);
		if (subKeyNames.Count == 0)
		{
			subKeyNames = GetSubKeyNames(RegistryView.Registry64, subKey);
			if (subKeyNames.Count == 0)
			{
				subKeyNames = GetSubKeyNames(RegistryView.Registry32, subKey);
			}
		}
		return subKeyNames;
	}

	private static List<string> GetSubKeyNames(RegistryView rv, string subKey)
	{
		List<string> list = new List<string>();
		RegistryKey registryKey = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, rv);
		registryKey = registryKey.OpenSubKey(subKey);
		if (registryKey != null)
		{
			list.AddRange(registryKey.GetSubKeyNames());
		}
		return list;
	}
}

