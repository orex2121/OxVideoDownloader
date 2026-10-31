// OxVideoDownloader launcher: starts the portable app with the bundled
// Python, so the exe can carry the app icon in the taskbar / explorer.
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

class Launcher
{
    static void Main()
    {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(dir, "python", "pythonw.exe");
        if (!File.Exists(python))
            python = Path.Combine(dir, "python", "python.exe");
        if (!File.Exists(python))
        {
            string installer = Path.Combine(dir, "INSTALL.bat");
            if (File.Exists(installer) && MessageBox.Show(
                    "The portable Python environment is missing.\n\nRun INSTALL.bat now?",
                    "OxVideoDownloader", MessageBoxButtons.YesNo,
                    MessageBoxIcon.Information) == DialogResult.Yes)
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = installer,
                    WorkingDirectory = dir,
                    UseShellExecute = true,
                });
            }
            return;
        }
        string script = Path.Combine(dir, "oxvideodownloader.py");
        var psi = new ProcessStartInfo
        {
            FileName = python,
            Arguments = "\"" + script + "\"",
            WorkingDirectory = dir,
            UseShellExecute = false,
        };
        try { Process.Start(psi); }
        catch (Exception e)
        {
            Console.Error.WriteLine(e.Message);
            Environment.Exit(1);
        }
    }
}
