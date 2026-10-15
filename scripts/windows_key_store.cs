// Credential setup only. Never put a secret in source, arguments, stdout or research payloads.
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public static class NewsKeyStore
{
    public const string Target = "AI-In-the-News/OpenAI";
    public const string NewsApiTarget = "AI-In-the-News/NewsAPI.ai";
    private const int NotFound = 1168;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct Credential
    {
        public uint Flags, Type;
        public string TargetName, Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public uint CredentialBlobSize;
        public IntPtr CredentialBlob;
        public uint Persist, AttributeCount;
        public IntPtr Attributes;
        public string TargetAlias, UserName;
    }

    [DllImport("advapi32.dll", EntryPoint = "CredWriteW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool Write(ref Credential credential, uint flags);

    [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ReadNative(string target, uint type, uint flags, out IntPtr credential);

    [DllImport("advapi32.dll", EntryPoint = "CredDeleteW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeleteNative(string target, uint type, uint flags);

    [DllImport("advapi32.dll")]
    private static extern void CredFree(IntPtr buffer);

    private static void CheckTarget(string target)
    {
        if (target != Target && target != NewsApiTarget
            && !target.StartsWith(Target + "/test/", StringComparison.Ordinal)
            && !target.StartsWith(NewsApiTarget + "/test/", StringComparison.Ordinal))
            throw new ArgumentException("Unsupported application credential target");
    }

    public static void Save(string value, string target)
    {
        CheckTarget(target);
        if (String.IsNullOrWhiteSpace(value) || value.Length > 1024)
            throw new ArgumentException("Invalid credential length");
        IntPtr blob = Marshal.StringToCoTaskMemUni(value);
        try
        {
            var credential = new Credential {
                Type = 1, TargetName = target,
                UserName = target.StartsWith(NewsApiTarget, StringComparison.Ordinal) ? "NewsAPI.ai" : "OpenAI",
                Comment = "AI In the News local API credential",
                CredentialBlobSize = (uint)Encoding.Unicode.GetByteCount(value),
                CredentialBlob = blob, Persist = 2 // CRED_PERSIST_LOCAL_MACHINE, current user's credential set.
            };
            if (!Write(ref credential, 0)) throw new Win32Exception(Marshal.GetLastWin32Error());
        }
        finally { Marshal.ZeroFreeCoTaskMemUnicode(blob); }
    }

    public static bool Exists(string target)
    {
        CheckTarget(target);
        IntPtr pointer;
        if (!ReadNative(target, 1, 0, out pointer))
        {
            int error = Marshal.GetLastWin32Error();
            if (error == NotFound) return false;
            throw new Win32Exception(error);
        }
        CredFree(pointer);
        return true;
    }

    // Only call inside the execution launcher, assigning the result without printing it.
    public static string Load(string target)
    {
        CheckTarget(target);
        IntPtr pointer;
        if (!ReadNative(target, 1, 0, out pointer)) throw new Win32Exception(Marshal.GetLastWin32Error());
        try
        {
            var credential = (Credential)Marshal.PtrToStructure(pointer, typeof(Credential));
            return Marshal.PtrToStringUni(credential.CredentialBlob, (int)credential.CredentialBlobSize / 2);
        }
        finally { CredFree(pointer); }
    }

    public static void Delete(string target)
    {
        CheckTarget(target);
        if (!DeleteNative(target, 1, 0))
        {
            int error = Marshal.GetLastWin32Error();
            if (error != NotFound) throw new Win32Exception(error);
        }
    }
}
