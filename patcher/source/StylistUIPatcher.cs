using System;
using System.Collections.Generic;
using System.IO.Compression;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Forms;

internal static class StylistUIPatcher
{
    static string Hash(byte[] data)
    {
        using (SHA256 sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(data)).Replace("-", "").ToLowerInvariant();
    }

    static bool Matches(byte[] data, int offset, byte[] expected)
    {
        if (offset < 0 || offset + expected.Length > data.Length) return false;
        for (int i = 0; i < expected.Length; i++)
            if (data[offset + i] != expected[i]) return false;
        return true;
    }

    const int Site = 0, Section = 1, Append = 2;
    const string UpToDate = "This client already has the current Stylist UI patch. Nothing was changed.";

    sealed class Entry { public int Kind, Offset; public byte[] Old, New; }

    static Entry[] ReadRecipe(out int sourceLength, out int outputLength)
    {
        using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("StylistUI.patch"))
        using (BinaryReader reader = new BinaryReader(stream))
        {
            if (Encoding.ASCII.GetString(reader.ReadBytes(8)) != "STYNUM02")
                throw new InvalidDataException("Invalid embedded patch recipe.");
            sourceLength = reader.ReadInt32();
            outputLength = reader.ReadInt32();
            int count = reader.ReadInt32();
            if (outputLength < sourceLength || count < 1 || count > 100)
                throw new InvalidDataException("Invalid patch dimensions.");
            Entry[] entries = new Entry[count];
            for (int i = 0; i < count; i++)
            {
                Entry e = new Entry { Kind = reader.ReadInt32(), Offset = reader.ReadInt32() };
                int oldLength = reader.ReadInt32(), newLength = reader.ReadInt32();
                e.Old = reader.ReadBytes(oldLength);
                e.New = reader.ReadBytes(newLength);
                bool valid = e.Old.Length == oldLength && e.New.Length == newLength && e.Offset >= 0 &&
                    (e.Kind == Append ? oldLength == 0 && e.Offset == sourceLength && e.Offset + newLength == outputLength
                                      : (e.Kind == Site || e.Kind == Section) && oldLength == newLength && e.Offset + oldLength <= sourceLength);
                if (!valid) throw new InvalidDataException("Invalid patch bounds.");
                entries[i] = e;
            }
            if (stream.Position != stream.Length) throw new InvalidDataException("Invalid embedded patch recipe.");
            return entries;
        }
    }

    // Accepts any client whose patch sites hold either the original or the
    // patched bytes, so unrelated patches elsewhere are kept and earlier Stylist
    // patches are upgraded. Returns false when the EXE already has this patch.
    static bool PlanExe(byte[] source, out byte[] result)
    {
        int sourceLength, outputLength;
        Entry[] entries = ReadRecipe(out sourceLength, out outputLength);
        Entry section = Array.Find(entries, e => e.Kind == Section);
        Entry payload = Array.Find(entries, e => e.Kind == Append);
        if (section == null || payload == null) throw new InvalidDataException("Invalid embedded patch recipe.");
        // The .stynum section header slot tells whether a Stylist payload is present.
        bool extended = Matches(source, section.Offset, section.New);
        if (!extended && !Matches(source, section.Offset, section.Old))
            throw new InvalidOperationException("Unsupported client: unexpected PE section table. No file was changed.");
        if (source.Length != (extended ? outputLength : sourceLength))
            throw new InvalidOperationException("Unsupported client: unexpected file size " + source.Length +
                " (expected " + sourceLength + " or " + outputLength + "). No file was changed.");
        result = new byte[outputLength];
        Buffer.BlockCopy(source, 0, result, 0, source.Length);
        bool current = extended;
        foreach (Entry e in entries)
        {
            if (e.Kind == Site)
            {
                bool patched = Matches(source, e.Offset, e.New);
                if (!patched && !Matches(source, e.Offset, e.Old))
                    throw new InvalidOperationException(String.Format(
                        "Unsupported client: bytes at file offset 0x{0:X} do not match. No file was changed.", e.Offset));
                current &= patched;
            }
            else if (e.Kind == Append && extended)
                current &= Matches(source, e.Offset, e.New);
            Buffer.BlockCopy(e.New, 0, result, e.Offset, e.New.Length);
        }
        return !current;
    }

    static string BackupName(string path)
    {
        return path + "." + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".pre-stylist.bak";
    }

    static void EnsureWritable(string path)
    {
        try { using (new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { } }
        catch (IOException)
        {
            throw new IOException(Path.GetFileName(path) + " is in use. Close the game client and try again. No file was changed.");
        }
    }

    static string ReplaceExe(string input, byte[] source, byte[] result)
    {
        string backup = BackupName(input);
        string temp = input + ".stylist.tmp";
        if (File.Exists(backup) || File.Exists(temp))
            throw new IOException("A backup or temporary file already exists. The EXE was not changed.\r\n" + backup);
        string sourceHash = Hash(source), resultHash = Hash(result);
        // CreateNew refuses existing files, including hard links to the input.
        using (FileStream file = new FileStream(temp, FileMode.CreateNew, FileAccess.Write))
            file.Write(result, 0, result.Length);
        try
        {
            // Swaps the patched file in and moves the previous EXE, byte for byte, to the backup.
            File.Replace(temp, input, backup);
        }
        catch
        {
            File.Delete(temp);
            throw;
        }
        if (Hash(File.ReadAllBytes(backup)) != sourceHash || Hash(File.ReadAllBytes(input)) != resultHash)
            throw new InvalidDataException("Post-patch verification failed. The previous EXE is saved at:\r\n" + backup);
        return backup;
    }

    // ---- Selector box textures, installed into the client's top-priority GRF ----

    static KeyValuePair<byte[], byte[]>[] ReadTextures()
    {
        using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("StylistUI.textures"))
        using (BinaryReader reader = new BinaryReader(stream))
        {
            if (Encoding.ASCII.GetString(reader.ReadBytes(8)) != "STYTEX01")
                throw new InvalidDataException("Invalid embedded textures.");
            var result = new KeyValuePair<byte[], byte[]>[reader.ReadInt32()];
            for (int i = 0; i < result.Length; i++)
            {
                byte[] name = reader.ReadBytes(reader.ReadInt32());
                result[i] = new KeyValuePair<byte[], byte[]>(name, reader.ReadBytes(reader.ReadInt32()));
            }
            return result;
        }
    }

    // The lowest DATA.INI index has the highest priority.
    static string TopGrf(string clientDir)
    {
        string ini = Path.Combine(clientDir, "DATA.INI");
        if (!File.Exists(ini))
            throw new FileNotFoundException("DATA.INI was not found next to the EXE, so the selector textures cannot be installed. No file was changed.");
        int best = int.MaxValue;
        string grf = null;
        foreach (string line in File.ReadAllLines(ini))
        {
            int eq = line.IndexOf('='), key;
            if (eq > 0 && int.TryParse(line.Substring(0, eq).Trim(), out key) && key < best && line.Substring(eq + 1).Trim().Length > 0)
            {
                best = key;
                grf = Path.Combine(clientDir, line.Substring(eq + 1).Trim());
            }
        }
        if (grf == null || !File.Exists(grf))
            throw new FileNotFoundException("The first GRF listed in DATA.INI was not found. No file was changed.");
        return grf;
    }

    sealed class Grf
    {
        public byte[] Prefix;
        public List<KeyValuePair<byte[], byte[]>> Entries = new List<KeyValuePair<byte[], byte[]>>();
    }

    static uint U32(byte[] b, int i) { return BitConverter.ToUInt32(b, i); }

    static Grf ReadGrf(string path)
    {
        using (FileStream f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
        {
            byte[] header = new byte[46];
            if (f.Read(header, 0, 46) != 46) throw new InvalidDataException(path + ": not a GRF.");
            if (U32(header, 42) != 0x300)
                throw new NotSupportedException(Path.GetFileName(path) + " is GRF version 0x" + U32(header, 42).ToString("x") +
                    "; only 0x300 (GRF Editor) can be updated. No file was changed.");
            f.Seek(BitConverter.ToInt64(header, 30) + 46, SeekOrigin.Begin);
            BinaryReader reader = new BinaryReader(f);
            Grf grf = new Grf { Prefix = reader.ReadBytes(4) };
            int packed = reader.ReadInt32(), size = reader.ReadInt32();
            byte[] table = Inflate(reader.ReadBytes(packed), size);
            for (int i = 0; i < table.Length; )
            {
                int end = Array.IndexOf(table, (byte)0, i);
                if (end < 0 || end + 22 > table.Length) throw new InvalidDataException(path + ": corrupt file table.");
                byte[] name = new byte[end - i], record = new byte[21];
                Buffer.BlockCopy(table, i, name, 0, name.Length);
                Buffer.BlockCopy(table, end + 1, record, 0, 21);
                grf.Entries.Add(new KeyValuePair<byte[], byte[]>(name, record));
                i = end + 22;
            }
            if (grf.Entries.Count != U32(header, 38)) throw new InvalidDataException(path + ": corrupt file table.");
            return grf;
        }
    }

    // GRF names are case-insensitive for ASCII; multibyte (cp949) bytes compare exactly.
    static bool SameName(byte[] a, byte[] b)
    {
        if (a.Length != b.Length) return false;
        for (int i = 0; i < a.Length; i++)
        {
            byte x = a[i], y = b[i];
            if (x == y) continue;
            if (x >= 0x80 || y >= 0x80 || char.ToLowerInvariant((char)x) != char.ToLowerInvariant((char)y)) return false;
        }
        return true;
    }

    static int Find(Grf grf, byte[] name)
    {
        return grf.Entries.FindIndex(e => SameName(e.Key, name));
    }

    static byte[] ReadGrfFile(string path, byte[] record)
    {
        if (record[12] != 1) return null;
        int packed = (int)U32(record, 0), aligned = (int)U32(record, 4), size = (int)U32(record, 8);
        using (FileStream f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
        {
            f.Seek(BitConverter.ToInt64(record, 13) + 46, SeekOrigin.Begin);
            byte[] data = new byte[aligned];
            if (f.Read(data, 0, aligned) != aligned) return null;
            Array.Resize(ref data, packed);
            try { return Inflate(data, size); } catch (InvalidDataException) { return null; }
        }
    }

    static bool TexturesCurrent(string path, Grf grf, KeyValuePair<byte[], byte[]>[] textures)
    {
        foreach (var texture in textures)
        {
            int i = Find(grf, texture.Key);
            if (i < 0) return false;
            byte[] data = ReadGrfFile(path, grf.Entries[i].Value);
            if (data == null || data.Length != texture.Value.Length || !Matches(data, 0, texture.Value)) return false;
        }
        return true;
    }

    static byte[] Inflate(byte[] zlib, int size)
    {
        byte[] result = new byte[size];
        using (DeflateStream inflate = new DeflateStream(new MemoryStream(zlib, 2, zlib.Length - 2), CompressionMode.Decompress))
        {
            int read = 0, n;
            while (read < size && (n = inflate.Read(result, read, size - read)) > 0) read += n;
            if (read != size) throw new InvalidDataException("Truncated compressed data.");
        }
        return result;
    }

    static byte[] Deflate(byte[] data)
    {
        MemoryStream output = new MemoryStream();
        output.WriteByte(0x78);
        output.WriteByte(0x9C);
        using (DeflateStream deflate = new DeflateStream(output, CompressionMode.Compress, true))
            deflate.Write(data, 0, data.Length);
        uint a = 1, b = 0;
        foreach (byte x in data) { a = (a + x) % 65521; b = (b + a) % 65521; }
        uint adler = (b << 16) | a;
        output.WriteByte((byte)(adler >> 24));
        output.WriteByte((byte)(adler >> 16));
        output.WriteByte((byte)(adler >> 8));
        output.WriteByte((byte)adler);
        return output.ToArray();
    }

    // Appends the textures and a new file table after the old one; the header
    // is written last. The GRF is backed up first and restored on failure.
    static string InstallTextures(string path, Grf grf, KeyValuePair<byte[], byte[]>[] textures)
    {
        string backup = BackupName(path);
        if (File.Exists(backup)) throw new IOException("A GRF backup already exists. No file was changed.\r\n" + backup);
        File.Copy(path, backup);
        if (new FileInfo(backup).Length != new FileInfo(path).Length)
            throw new IOException("GRF backup verification failed. No file was changed.");
        try
        {
            using (FileStream f = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            {
                long position = f.Seek(0, SeekOrigin.End) - 46;
                foreach (var texture in textures)
                {
                    byte[] packed = Deflate(texture.Value);
                    int aligned = (packed.Length + 7) / 8 * 8;
                    f.Write(packed, 0, packed.Length);
                    f.Write(new byte[aligned - packed.Length], 0, aligned - packed.Length);
                    MemoryStream record = new MemoryStream();
                    BinaryWriter w = new BinaryWriter(record);
                    w.Write(packed.Length); w.Write(aligned); w.Write(texture.Value.Length); w.Write((byte)1); w.Write(position);
                    var entry = new KeyValuePair<byte[], byte[]>(texture.Key, record.ToArray());
                    int i = Find(grf, texture.Key);
                    if (i >= 0) grf.Entries[i] = entry; else grf.Entries.Add(entry);
                    position += aligned;
                }
                MemoryStream table = new MemoryStream();
                foreach (var e in grf.Entries) { table.Write(e.Key, 0, e.Key.Length); table.WriteByte(0); table.Write(e.Value, 0, 21); }
                byte[] packedTable = Deflate(table.ToArray());
                BinaryWriter writer = new BinaryWriter(f);
                writer.Write(grf.Prefix);
                writer.Write(packedTable.Length);
                writer.Write((int)table.Length);
                writer.Write(packedTable);
                writer.Flush();
                f.Seek(30, SeekOrigin.Begin);
                writer.Write(position);
                writer.Write(grf.Entries.Count);
                writer.Flush();
            }
            if (!TexturesCurrent(path, ReadGrf(path), textures))
                throw new InvalidDataException("GRF verification failed.");
        }
        catch
        {
            File.Copy(backup, path, true);
            throw;
        }
        return backup;
    }

    // Patches the EXE and installs the selector textures. Everything is
    // validated before the first write. Returns a report for the user.
    internal static string Patch(string input)
    {
        input = Path.GetFullPath(input);
        byte[] source = File.ReadAllBytes(input), result;
        bool exeChanges = PlanExe(source, out result);
        string grfPath = TopGrf(Path.GetDirectoryName(input));
        Grf grf = ReadGrf(grfPath);
        var textures = ReadTextures();
        bool grfChanges = !TexturesCurrent(grfPath, grf, textures);
        if (!exeChanges && !grfChanges) return UpToDate;
        if (exeChanges) EnsureWritable(input);
        if (grfChanges) EnsureWritable(grfPath);
        StringBuilder report = new StringBuilder("Stylist UI patch applied.\r\n");
        if (grfChanges)
            report.Append("\r\nSelector textures added to " + Path.GetFileName(grfPath) + ". GRF backup:\r\n" +
                          InstallTextures(grfPath, grf, textures) + "\r\n");
        if (exeChanges)
            report.Append("\r\nEXE patched. EXE backup:\r\n" + ReplaceExe(input, source, result) + "\r\n");
        return report.ToString();
    }

    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length != 0)
        {
            try
            {
                if (args.Length != 1) throw new ArgumentException("Usage: StylistUIPatcher.exe CLIENT.exe");
                Console.WriteLine(Patch(args[0]));
                return 0;
            }
            catch (Exception error) { Console.Error.WriteLine(error.Message); return 1; }
        }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Form form = new Form {
            Text = "Stylist UI Patcher", ClientSize = new Size(650, 255),
            FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false,
            StartPosition = FormStartPosition.CenterScreen, Font = new Font("Segoe UI", 10)
        };
        Label heading = new Label {
            Text = "Numeric appearance selectors", AutoSize = true,
            Location = new Point(20, 18), Font = new Font("Segoe UI", 15, FontStyle.Bold)
        };
        Label description = new Label {
            Text = "Hairstyle X/Y  |  Clothing Color X/Y  |  Hair Color X/Y\r\n" +
                   "Uses your loaded catalogues and preserves native Doram restrictions.\r\n" +
                   "Select the client EXE and it is patched right away (original or earlier Stylist patch).\r\n" +
                   "Also installs the selector box textures into the client GRF. Backups are saved first.",
            Location = new Point(20, 58), Size = new Size(610, 86)
        };
        TextBox path = new TextBox { Location = new Point(20, 150), Size = new Size(465, 28), ReadOnly = true };
        Button browse = new Button { Text = "Select EXE...", Location = new Point(495, 148), Size = new Size(135, 32) };
        Label status = new Label { Text = "Select the client EXE to patch it.", Location = new Point(20, 196), Size = new Size(610, 50) };
        browse.Click += delegate {
            using (OpenFileDialog dialog = new OpenFileDialog { Title = "Select client EXE", Filter = "Client executable (*.exe)|*.exe" })
            {
                if (dialog.ShowDialog(form) != DialogResult.OK) return;
                path.Text = dialog.FileName;
            }
            try {
                string report = Patch(path.Text);
                status.Text = report == UpToDate ? UpToDate : "Patched. The backups are listed in the message.";
                MessageBox.Show(form, report, "Stylist UI Patcher", MessageBoxButtons.OK, MessageBoxIcon.Information);
            } catch (Exception error) {
                status.Text = "No patch was applied.";
                MessageBox.Show(form, error.Message, "Stylist UI Patcher", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        };
        form.Controls.AddRange(new Control[] { heading, description, path, browse, status });
        Application.Run(form);
        return 0;
    }
}
