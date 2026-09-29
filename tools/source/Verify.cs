using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

// C# port of tools/verify_package.py. Reads the package only; changes nothing.
internal static class Verify
{
    public static string Run(string root)
    {
        root = Path.GetFullPath(root);
        string manifest = Path.Combine(root, "SHA256SUMS.txt");
        if (!File.Exists(manifest))
            throw new ToolError("SHA256SUMS.txt was not found in " + root + ". Use a complete release package.");
        int count = 0;
        HashSet<string> listed = new HashSet<string>();
        string prefix = root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        foreach (string line in Text.Lines(File.ReadAllText(manifest, Encoding.UTF8)))
        {
            int split = line.IndexOf("  ", StringComparison.Ordinal);
            if (split < 0) throw new ToolError("Invalid checksum entry: " + line);
            string expected = line.Substring(0, split), relative = line.Substring(split + 2);
            if (!Regex.IsMatch(expected, "^[0-9a-f]{64}$") || listed.Contains(relative))
                throw new ToolError("Invalid or duplicate checksum entry: " + relative);
            string path = Path.GetFullPath(Path.Combine(root, relative));
            if (!path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                throw new ToolError("Checksum entry is outside the package: " + relative);
            if (!File.Exists(path) || Text.Sha256(File.ReadAllBytes(path)) != expected)
                throw new ToolError("Missing or changed file: " + relative);
            listed.Add(relative);
            count++;
        }
        const string folder = "diff";
        Dictionary<string, object> metadata = (Dictionary<string, object>)new JavaScriptSerializer()
            .DeserializeObject(File.ReadAllText(Path.Combine(root, folder, "base.json"), Encoding.UTF8));
        byte[] patch = File.ReadAllBytes(Path.Combine(root, folder, "stylist_ui.diff"));
        Dictionary<string, byte[]> mirrors = NewFiles(patch);
        foreach (object item in (IEnumerable)metadata["new_files"])
        {
            string relative = (string)item, name = "server/" + relative;
            byte[] mirror;
            if (!listed.Contains(name) || !mirrors.TryGetValue(relative, out mirror) ||
                !mirror.SequenceEqual(File.ReadAllBytes(Path.Combine(root, name))))
                throw new ToolError("New server file differs from patch: " + relative);
        }
        List<string> required = new List<string> { "README.md", "INSTALL.md", folder + "/stylist_ui.diff",
            "patcher/StylistUIPatcher.exe", "client/data/luafiles514/lua files/stylingshop/stylingshopinfo.lub" };
        if (!required.All(listed.Contains))
            throw new ToolError("Manifest is missing a required release component");
        return "PASS: " + count + " release files verified; all " + mirrors.Count + " new server files match the diff.";
    }

    // Folders and files that .gitignore keeps out of a release. "generated" is
    // skipped only at the package root: patcher/source/generated is released.
    static readonly string[] IgnoredFolders = { "__pycache__", ".venv", ".git" };
    static readonly string[] IgnoredExtensions = { ".pyc", ".pyo", ".pyd", ".bak" };
    static readonly string[] IgnoredNames = { "SHA256SUMS.txt", "Thumbs.db", "desktop.ini" };

    // Lists every release file in SHA256SUMS.txt, then checks the result with Run.
    public static string WriteChecksums(string root)
    {
        root = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar);
        if (!File.Exists(Path.Combine(root, "diff", "stylist_ui.diff")))
            throw new ToolError("This is not a Stylist UI package folder (diff/stylist_ui.diff is missing): " + root);
        List<string> files = new List<string>();
        Collect(root, root, files);
        files.Sort(StringComparer.Ordinal);
        StringBuilder manifest = new StringBuilder();
        foreach (string relative in files)
            manifest.Append(Text.Sha256(File.ReadAllBytes(Path.Combine(root, relative)))).Append("  ").Append(relative).Append('\n');
        Text.Write(Path.Combine(root, "SHA256SUMS.txt"), manifest.ToString());
        string written = "SHA256SUMS.txt created with " + files.Count + " files.";
        try { return written + "\n" + Run(root); }
        catch (ToolError error) { throw new ToolError(written + "\nBut the package check failed: " + error.Message); }
    }

    static void Collect(string root, string folder, List<string> files)
    {
        foreach (string directory in Directory.GetDirectories(folder))
        {
            string name = Path.GetFileName(directory);
            if (IgnoredFolders.Contains(name, StringComparer.OrdinalIgnoreCase)) continue;
            if (folder == root && name.Equals("generated", StringComparison.OrdinalIgnoreCase)) continue;
            Collect(root, directory, files);
        }
        foreach (string file in Directory.GetFiles(folder))
        {
            string name = Path.GetFileName(file);
            if (IgnoredNames.Contains(name, StringComparer.OrdinalIgnoreCase) ||
                IgnoredExtensions.Contains(Path.GetExtension(name), StringComparer.OrdinalIgnoreCase)) continue;
            files.Add(file.Substring(root.Length + 1).Replace(Path.DirectorySeparatorChar, '/'));
        }
    }

    // The contents of every "new file" in a git diff, keyed by its path.
    static Dictionary<string, byte[]> NewFiles(byte[] patch)
    {
        Dictionary<string, byte[]> mirrors = new Dictionary<string, byte[]>();
        List<byte[]> chunks = Split(patch, Encoding.ASCII.GetBytes("diff --git "));
        foreach (byte[] chunk in chunks.Skip(1))
        {
            List<byte[]> lines = LinesWithEnds(chunk);
            if (!lines.Any(l => StartsWith(l, "new file mode "))) continue;
            byte[] header = lines.FirstOrDefault(l => StartsWith(l, "+++ b/"));
            if (header == null) throw new ToolError("Invalid diff: new file without a +++ header.");
            string relative = Encoding.UTF8.GetString(header, 6, header.Length - 6).Trim();
            MemoryStream content = new MemoryStream();
            foreach (byte[] line in lines)
                if (StartsWith(line, "+") && !StartsWith(line, "+++ ")) content.Write(line, 1, line.Length - 1);
            mirrors[relative] = content.ToArray();
        }
        return mirrors;
    }

    static bool StartsWith(byte[] data, string prefix)
    {
        if (data.Length < prefix.Length) return false;
        for (int i = 0; i < prefix.Length; i++) if (data[i] != prefix[i]) return false;
        return true;
    }

    static List<byte[]> Split(byte[] data, byte[] separator)
    {
        List<byte[]> parts = new List<byte[]>();
        int start = 0;
        for (int i = 0; i + separator.Length <= data.Length; i++)
        {
            bool match = true;
            for (int j = 0; j < separator.Length && match; j++) match = data[i + j] == separator[j];
            if (!match) continue;
            parts.Add(Slice(data, start, i));
            start = i + separator.Length;
            i = start - 1;
        }
        parts.Add(Slice(data, start, data.Length));
        return parts;
    }

    // Python bytes.splitlines(keepends=True): splits after \n, \r\n or a lone \r.
    static List<byte[]> LinesWithEnds(byte[] data)
    {
        List<byte[]> lines = new List<byte[]>();
        int start = 0;
        for (int i = 0; i < data.Length; i++)
        {
            if (data[i] == '\r' && i + 1 < data.Length && data[i + 1] == '\n') i++;
            else if (data[i] != '\n' && data[i] != '\r') continue;
            lines.Add(Slice(data, start, i + 1));
            start = i + 1;
        }
        if (start < data.Length) lines.Add(Slice(data, start, data.Length));
        return lines;
    }

    static byte[] Slice(byte[] data, int start, int end)
    {
        byte[] result = new byte[end - start];
        Buffer.BlockCopy(data, start, result, 0, result.Length);
        return result;
    }
}
