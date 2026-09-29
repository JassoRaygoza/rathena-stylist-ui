using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

internal static class Program
{
    const string Usage =
@"Stylist Tools - catalogue generator and package verifier. No Python required.

Double-click StylistTools.exe to use the window. Command line:

  StylistTools.exe --cloth-colors N --hair-colors N --hairstyles N [options]
  StylistTools.exe --from-conf FILE [--cloth-colors N] [...] [options]
  StylistTools.exe --verify
  StylistTools.exe --write-checksums

Options:
  --from-conf FILE         Read max_cloth_color, max_hair_color and max_hair_style (including imports)
  --cloth-colors N         Clothing color count (IDs 1..N; default color 0 is extra)
  --hair-colors N          Hair color count (IDs 1..N; default color 0 is extra)
  --hairstyles N           Hairstyle count (IDs 1..N)
  --include-doram          Also extend Doram options using installed Doram assets
  --new-entry-price N      Zeny price for new entries; existing prices are retained (default 100000)
  --source FILE            Custom source StylingShop Lua table
  --server FOLDER          Patched rAthena source tree (default: STYLIST_SERVER_ROOT, else built-in data)
  --output FOLDER          New or empty output directory (default: generated\<timestamp>)
  --verify                 Check SHA256SUMS.txt and the new server files against the diff
  --write-checksums        Create or replace SHA256SUMS.txt from the current package files, then check it
  --help                   Show this help";

    [DllImport("kernel32.dll")] static extern bool FreeConsole();
    [DllImport("kernel32.dll")] static extern uint GetConsoleProcessList(uint[] list, uint count);

    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length == 0)
        {
            // Started by double-click: close the console window that Windows opened for us.
            if (GetConsoleProcessList(new uint[2], 2) <= 1) FreeConsole();
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
            return 0;
        }
        try { return Cli(args); }
        catch (UsageError error)
        {
            Console.Error.WriteLine("error: " + error.Message);
            Console.Error.WriteLine("Run StylistTools.exe --help for usage.");
            return 2;
        }
    }

    sealed class UsageError : Exception { public UsageError(string message) : base(message) { } }

    static int Cli(string[] args)
    {
        Dictionary<string, string> options = new Dictionary<string, string>();
        HashSet<string> flags = new HashSet<string>();
        string[] valued = { "--from-conf", "--cloth-colors", "--hair-colors", "--hairstyles", "--new-entry-price",
            "--source", "--server", "--output" };
        for (int i = 0; i < args.Length; i++)
        {
            string arg = args[i], value = null;
            int equals = arg.IndexOf('=');
            if (arg.StartsWith("--") && equals > 0) { value = arg.Substring(equals + 1); arg = arg.Substring(0, equals); }
            if (Array.IndexOf(valued, arg) >= 0)
            {
                if (value == null)
                {
                    if (i + 1 >= args.Length) throw new UsageError("argument " + arg + ": expected one argument");
                    value = args[++i];
                }
                options[arg] = value;
            }
            else if (arg == "--include-doram" || arg == "--verify" || arg == "--write-checksums" || arg == "--help" || arg == "-h" || arg == "/?") flags.Add(arg);
            else if (arg == "--export-reference" && i + 3 < args.Length)
            {
                // Build step: --export-reference <server folder> <source table> <output file>
                Text.Write(args[i + 3], Catalogue.ExportReference(args[i + 1], Text.Read(args[i + 2])));
                return 0;
            }
            else throw new UsageError("unrecognized argument: " + args[i]);
        }
        if (flags.Contains("--help") || flags.Contains("-h") || flags.Contains("/?")) { Console.WriteLine(Usage); return 0; }
        if (flags.Contains("--write-checksums"))
        {
            try { Console.WriteLine(Verify.WriteChecksums(Catalogue.PackageRoot)); return 0; }
            catch (Exception error) { Console.Error.WriteLine("Checksum creation failed: " + error.Message); return 1; }
        }
        if (flags.Contains("--verify"))
        {
            try { Console.WriteLine(Verify.Run(Catalogue.PackageRoot)); return 0; }
            catch (Exception error) { Console.Error.WriteLine("Verification failed: " + error.Message); return 1; }
        }
        Func<string, int?> number = name =>
        {
            if (!options.ContainsKey(name)) return null;
            int parsed;
            if (!int.TryParse(options[name], NumberStyles.AllowLeadingSign | NumberStyles.AllowLeadingWhite | NumberStyles.AllowTrailingWhite,
                    CultureInfo.InvariantCulture, out parsed))
                throw new UsageError("argument " + name + ": invalid int value: '" + options[name] + "'");
            return parsed;
        };
        int?[] overrides = { number("--cloth-colors"), number("--hair-colors"), number("--hairstyles") };
        int price = number("--new-entry-price") ?? 100000;
        try
        {
            string server = ServerFolder(options.ContainsKey("--server") ? options["--server"] : null);
            Dictionary<string, int> values = options.ContainsKey("--from-conf")
                ? Catalogue.ReadConf(options["--from-conf"], server) : new Dictionary<string, int>();
            for (int i = 0; i < Settings.Keys.Length; i++)
                if (overrides[i].HasValue) values[Settings.Keys[i]] = overrides[i].Value;
            if (!options.ContainsKey("--from-conf") && Array.TrueForAll(overrides, o => !o.HasValue))
                values = Wizard();
            List<string> missing = new List<string>();
            foreach (string key in Settings.Keys) if (!values.ContainsKey(key)) missing.Add(key);
            if (missing.Count > 0)
                throw new ToolError("Missing settings: " + string.Join(", ", missing) + ". Supply all three counts or use --from-conf.");
            Settings settings = new Settings
            {
                MaxClothColor = values["max_cloth_color"], MaxHairColor = values["max_hair_color"],
                MaxHairStyle = values["max_hair_style"], IncludeDoram = flags.Contains("--include-doram"), NewEntryPrice = price,
            };
            string source = options.ContainsKey("--source") ? Text.Read(options["--source"]) : Catalogue.DefaultSource();
            string output = options.ContainsKey("--output") ? options["--output"] : Catalogue.NewOutputFolder();
            output = Catalogue.WritePackage(settings, output, source, Load(server));
            Console.WriteLine("Generated matching client tables, server catalogue, and battle limits in:\n" + output);
            Console.WriteLine("Installation instructions: " + Path.Combine(output, "INSTALL.md"));
            return 0;
        }
        catch (Exception error)
        {
            if (error is UsageError) throw;
            Console.Error.WriteLine("Generation failed: " + (error.Message.Length > 0 ? error.Message : "input cancelled"));
            return 1;
        }
    }

    static Dictionary<string, int> Wizard()
    {
        Dictionary<string, int> defaults = Catalogue.DefaultCounts();
        Console.WriteLine("Stylist Catalogue Builder\nSet clothing colors, hair colors, and hairstyles independently.");
        Console.WriteLine("Colors use IDs 1..N plus default color 0. Install the matching client assets.");
        string[] labels = { "How many clothing colors?", "How many hair colors?", "How many hairstyles?" };
        Dictionary<string, int> values = new Dictionary<string, int>();
        for (int i = 0; i < labels.Length; i++)
        {
            string key = Settings.Keys[i];
            int minimum = Settings.Minimum(key);
            while (true)
            {
                Console.Write(labels[i] + " (" + key + ", " + minimum + "-" + Settings.MaxCount + ") [" + defaults[key] + "]: ");
                string answer = Console.ReadLine();
                if (answer == null) throw new ToolError("input cancelled");
                answer = answer.Trim();
                int parsed;
                if (answer.Length == 0) { values[key] = defaults[key]; break; }
                if (int.TryParse(answer, NumberStyles.None, CultureInfo.InvariantCulture, out parsed) &&
                    parsed >= minimum && parsed <= Settings.MaxCount) { values[key] = parsed; break; }
                Console.WriteLine("Enter a whole number from " + minimum + " to " + Settings.MaxCount + ".");
            }
        }
        return values;
    }

    // Explicit folder, else STYLIST_SERVER_ROOT, else null (built-in reference data).
    public static string ServerFolder(string explicitFolder)
    {
        string folder = string.IsNullOrWhiteSpace(explicitFolder) ? Environment.GetEnvironmentVariable("STYLIST_SERVER_ROOT") : explicitFolder;
        return string.IsNullOrWhiteSpace(folder) ? null : Path.GetFullPath(folder.Trim());
    }

    public static ServerData Load(string server) { return server == null ? ServerData.BuiltIn() : ServerData.FromServer(server); }

    public static void Open(string path) { Process.Start(new ProcessStartInfo(path) { UseShellExecute = true }); }
}
