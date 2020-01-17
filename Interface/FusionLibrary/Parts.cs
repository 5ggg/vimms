using System;
using System.Collections.Generic;
using System.ComponentModel.Composition;

internal class Parts<T>
{
	[ImportMany]
	public List<Lazy<T>> TContainer;
}