using System;
using System.Runtime.Serialization;

[Serializable]
public class FactoryException : Exception, ISerializable
{
	public FactoryException()
	{
	}

	public FactoryException(string message)
		: base(message)
	{
	}

	public FactoryException(string message, Exception innerException)
		: base(message, innerException)
	{
	}

	public FactoryException(SerializationInfo info, StreamingContext context)
		: base(info, context)
	{
	}

	public override void GetObjectData(SerializationInfo info, StreamingContext context)
	{
		base.GetObjectData(info, context);
	}
}
