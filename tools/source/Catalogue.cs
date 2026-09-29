using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

// C# port of tools/catalogue/configure_catalogue.py and generate_catalogue.py.
// Output is byte-identical to the Python generator for the same inputs.
internal sealed class ToolError : Exception
{
    public ToolError(string message) : base(message) { }
}

internal sealed class Settings
{
    public const int MaxCount = 32766;
    public static readonly string[] Keys = { "max_cloth_color", "max_hair_color", "max_hair_style" };

    public int MaxClothColor, MaxHairColor, MaxHairStyle;
    public bool IncludeDoram;
    public int NewEntryPrice = 100000;

    public int Get(string key)
    {
        switch (key)
        {
            case "max_cloth_color": return MaxClothColor;
            case "max_hair_color": return MaxHairColor;
            default: return MaxHairStyle;
        }
    }

    public static int Minimum(string key) { return key == "max_hair_style" ? 1 : 0; }

    public void Validate()
    {
        foreach (string key in Keys)
        {
            int value = Get(key), minimum = Minimum(key);
            if (value < minimum || value > MaxCount)
                throw new ToolError(key + " must be an integer from " + minimum + " to " + MaxCount + ".");
        }
        if (NewEntryPrice < 0)
            throw new ToolError("new_entry_price must be an integer from 0 to 2147483647.");
    }
}

// Server-side facts the generator needs: job constants, lineage rows and item names.
// They come from a patched rAthena tree, or from the reference data built into the EXE.
internal sealed class ServerData
{
    public const int None = 0xFFFF;
    public Dictionary<string, int> Jobs = new Dictionary<string, int>();
    public Dictionary<int, string> Items = new Dictionary<int, string>();
    public string LineageHeader;
    public string Origin;

    public static bool IsServerTree(string root)
    {
        return File.Exists(Path.Combine(root, "src/common/mmo.hpp")) &&
               File.Exists(Path.Combine(root, "src/map/stylist.hpp")) &&
               Directory.Exists(Path.Combine(root, "db/re"));
    }

    public static ServerData FromServer(string root)
    {
        if (!IsServerTree(root))
            throw new ToolError("Set STYLIST_SERVER_ROOT to a patched rAthena source tree containing src and db.");
        ServerData data = new ServerData { Origin = root };
        string mmo = Text.Read(Path.Combine(root, "src/common/mmo.hpp"));
        int start = mmo.IndexOf("enum e_job {", StringComparison.Ordinal);
        if (start < 0) throw new ToolError("enum e_job was not found in src/common/mmo.hpp.");
        string body = mmo.Substring(start + "enum e_job {".Length);
        int end = body.IndexOf("};", StringComparison.Ordinal);
        if (end >= 0) body = body.Substring(0, end);
        int value = -1;
        foreach (Match m in Regex.Matches(body, @"\b(JOB_\w+)\s*(?:=\s*(\d+))?\s*,"))
        {
            value = m.Groups[2].Success ? int.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture) : value + 1;
            data.Jobs[m.Groups[1].Value] = value;
        }
        data.LineageHeader = Text.Read(Path.Combine(root, "src/map/stylist.hpp"));
        string[] files = Directory.GetFiles(Path.Combine(root, "db/re"), "item_db_*.yml")
            .Where(f => f.EndsWith(".yml", StringComparison.OrdinalIgnoreCase)).OrderBy(f => f, StringComparer.Ordinal).ToArray();
        foreach (string file in files)
            foreach (Match m in Regex.Matches(Text.Read(file), @"^  - Id: (\d+)\n    AegisName: (\S+)", RegexOptions.Multiline))
                data.Items[int.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture)] = m.Groups[2].Value;
        return data;
    }

    public static ServerData BuiltIn()
    {
        string reference = Text.Resource("StylistTools.reference");
        string header = Text.Resource("StylistTools.stylist_hpp");
        if (reference == null || header == null)
            throw new ToolError("This build has no built-in server data. Select your patched rAthena server folder.");
        ServerData data = new ServerData { Origin = null, LineageHeader = header };
        foreach (string line in Text.Lines(reference))
        {
            string[] parts = line.Split(' ');
            if (parts.Length == 3 && parts[0] == "job") data.Jobs[parts[1]] = int.Parse(parts[2], CultureInfo.InvariantCulture);
            else if (parts.Length == 3 && parts[0] == "item") data.Items[int.Parse(parts[1], CultureInfo.InvariantCulture)] = parts[2];
        }
        return data;
    }

    public int Job(string name)
    {
        if (name == "STYLIST_NONE") return None;
        int value;
        if (!Jobs.TryGetValue(name, out value)) throw new ToolError("Unknown job constant in stylist.hpp: " + name);
        return value;
    }

    public string Item(int id)
    {
        string name;
        if (Items.TryGetValue(id, out name)) return name;
        if (Origin == null)
            throw new ToolError("Item " + id + " is not in the built-in reference data. Select your patched rAthena server folder.");
        throw new ToolError("Item " + id + " was not found in " + Path.Combine(Origin, "db/re") + ".");
    }
}

internal static class Text
{
    static readonly UTF8Encoding Utf8 = new UTF8Encoding(false);

    // Like Python's read_text(encoding='utf-8-sig'): BOM removed, newlines normalized.
    public static string Read(string path) { return Normalize(File.ReadAllText(path, Encoding.UTF8)); }

    public static string Normalize(string text)
    {
        if (text.Length > 0 && text[0] == '﻿') text = text.Substring(1);
        return text.Replace("\r\n", "\n").Replace('\r', '\n');
    }

    // Python str.splitlines() for normalized text.
    public static List<string> Lines(string text)
    {
        text = Normalize(text);
        List<string> lines = new List<string>(text.Split('\n'));
        if (lines.Count > 0 && lines[lines.Count - 1].Length == 0) lines.RemoveAt(lines.Count - 1);
        return lines;
    }

    public static byte[] Bytes(string text) { return Utf8.GetBytes(text); }

    public static void Write(string path, string text) { File.WriteAllBytes(path, Bytes(text)); }

    public static string Sha256(byte[] data)
    {
        using (SHA256 sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(data)).Replace("-", "").ToLowerInvariant();
    }

    public static string Resource(string name)
    {
        using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
        {
            if (stream == null) return null;
            using (StreamReader reader = new StreamReader(stream, Encoding.UTF8))
                return Normalize(reader.ReadToEnd());
        }
    }
}

// Ordered JSON object formatted exactly like Python's json.dumps(value, indent=2).
internal sealed class JsonObject : List<KeyValuePair<string, object>>
{
    public void Add(string key, object value) { Add(new KeyValuePair<string, object>(key, value)); }

    public static string Dump(object value) { StringBuilder b = new StringBuilder(); Write(b, value, 0); return b.ToString(); }

    static void Write(StringBuilder b, object value, int depth)
    {
        string pad = new string(' ', 2 * (depth + 1)), close = new string(' ', 2 * depth);
        if (value is bool) b.Append((bool)value ? "true" : "false");
        else if (value is int || value is long) b.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
        else if (value is string) Quote(b, (string)value);
        else if (value is JsonObject)
        {
            JsonObject o = (JsonObject)value;
            if (o.Count == 0) { b.Append("{}"); return; }
            b.Append("{\n");
            for (int i = 0; i < o.Count; i++)
            {
                b.Append(pad); Quote(b, o[i].Key); b.Append(": "); Write(b, o[i].Value, depth + 1);
                b.Append(i + 1 < o.Count ? ",\n" : "\n");
            }
            b.Append(close).Append('}');
        }
        else
        {
            List<object> list = ((System.Collections.IEnumerable)value).Cast<object>().ToList();
            if (list.Count == 0) { b.Append("[]"); return; }
            b.Append("[\n");
            for (int i = 0; i < list.Count; i++)
            {
                b.Append(pad); Write(b, list[i], depth + 1);
                b.Append(i + 1 < list.Count ? ",\n" : "\n");
            }
            b.Append(close).Append(']');
        }
    }

    static void Quote(StringBuilder b, string s)
    {
        b.Append('"');
        foreach (char c in s)
        {
            switch (c)
            {
                case '"': b.Append("\\\""); break;
                case '\\': b.Append("\\\\"); break;
                case '\n': b.Append("\\n"); break;
                case '\r': b.Append("\\r"); break;
                case '\t': b.Append("\\t"); break;
                case '\b': b.Append("\\b"); break;
                case '\f': b.Append("\\f"); break;
                default:
                    if (c < 0x20 || c > 0x7e) b.Append("\\u").Append(((int)c).ToString("x4"));
                    else b.Append(c);
                    break;
            }
        }
        b.Append('"');
    }
}

internal static class Catalogue
{
    public const string ClientPath = "data/luafiles514/lua files/stylingshop/stylingshopinfo.lub";
    static readonly Regex Call = new Regex(@"^StylingShop\.(Add\w+)\((\d+),.*\)$");
    static readonly Regex AnyCall = new Regex(@"^StylingShop\.(Add\w+)\((.*?)\)$");
    const string Unsupported = "-- Not supported by this server base: ";

    static readonly Dictionary<string, string[]> Functions = new Dictionary<string, string[]>
    {
        { "AddHeadPalette", new[] { "Hair_Color", "CostsHuman" } },
        { "AddHeadStyle", new[] { "Hair", "CostsHuman" } },
        { "AddDoramHeadStyle", new[] { "Hair", "CostsDoram" } },
        { "AddBodyPalette", new[] { "Clothes_Color", "CostsHuman" } },
        { "AddDoramBodyPalette", new[] { "Clothes_Color", "CostsDoram" } },
        { "AddTopAccessory", new[] { "Head_Top", "CostsHuman" } },
        { "AddMidAccessory", new[] { "Head_Mid", "CostsHuman" } },
        { "AddBottomAccessory", new[] { "Head_Bottom", "CostsHuman" } },
    };

    // Package layout: <package>\tools\StylistTools.exe
    public static string PackageRoot
    {
        get
        {
            string exe = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            string parent = Path.GetDirectoryName(exe);
            return parent != null && File.Exists(Path.Combine(parent, "client/source/stylingshopinfo.lub")) ? parent : exe;
        }
    }

    // The credited source table: the package copy when present, otherwise the built-in copy.
    public static string DefaultSource()
    {
        string path = Path.Combine(PackageRoot, "client/source/stylingshopinfo.lub");
        if (File.Exists(path)) return Text.Read(path);
        string text = Text.Resource("StylistTools.stylingshopinfo");
        if (text == null) throw new ToolError("The source table client/source/stylingshopinfo.lub was not found.");
        return text;
    }

    public static Dictionary<string, int> DefaultCounts()
    {
        string path = Path.Combine(PackageRoot, "server/conf/battle/stylist.conf");
        if (File.Exists(path)) return ReadConf(path, null);
        string text = Text.Resource("StylistTools.stylist_conf");
        if (text == null) throw new ToolError("server/conf/battle/stylist.conf was not found.");
        return ParseConf(text, "stylist.conf", null, null, new List<string>());
    }

    // Reads the three max_* settings, honoring ordered imports/overrides like rAthena.
    public static Dictionary<string, int> ReadConf(string path, string serverRoot)
    {
        return ReadConf(path, serverRoot, new List<string>());
    }

    static Dictionary<string, int> ReadConf(string path, string serverRoot, List<string> stack)
    {
        path = Path.GetFullPath(path);
        if (stack.Any(p => string.Equals(p, path, StringComparison.OrdinalIgnoreCase)))
            throw new ToolError("Configuration import cycle: " + path);
        if (!File.Exists(path)) throw new FileNotFoundException("Configuration file not found: " + path);
        return ParseConf(Text.Read(path), path, Path.GetDirectoryName(path), serverRoot, stack);
    }

    static Dictionary<string, int> ParseConf(string text, string path, string folder, string serverRoot, List<string> stack)
    {
        Dictionary<string, int> values = new Dictionary<string, int>();
        List<string> lines = Text.Lines(text);
        for (int number = 1; number <= lines.Count; number++)
        {
            string raw = lines[number - 1];
            int comment = raw.IndexOf("//", StringComparison.Ordinal);
            string line = (comment >= 0 ? raw.Substring(0, comment) : raw).Trim();
            if (line.Length == 0 || line.StartsWith("#") || !line.Contains(":")) continue;
            int colon = line.IndexOf(':');
            string key = line.Substring(0, colon).Trim(), value = line.Substring(colon + 1).Trim();
            if (key == "import")
            {
                if (folder == null) continue;
                List<string> nested = new List<string>(stack) { path };
                foreach (KeyValuePair<string, int> pair in ReadConf(ResolveImport(value, folder, serverRoot), serverRoot, nested))
                    values[pair.Key] = pair.Value;
            }
            else if (Settings.Keys.Contains(key))
            {
                int parsed;
                if (!Regex.IsMatch(value, @"^[0-9]+$") || !int.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out parsed))
                    throw new ToolError(path + ":" + number + ": " + key + " must be a nonnegative integer.");
                values[key] = parsed;
            }
            else if (key == "min_cloth_color" || key == "min_hair_color" || key == "min_hair_style")
            {
                if (value != "0")
                    throw new ToolError(path + ":" + number + ": this generator requires " + key + ": 0 for default/reset support.");
            }
        }
        return values;
    }

    // rAthena imports are relative to the server root. Without an explicit root,
    // the folders above the importing file are searched, then its own folder.
    static string ResolveImport(string value, string folder, string serverRoot)
    {
        if (Path.IsPathRooted(value)) return value;
        if (serverRoot != null && File.Exists(Path.Combine(serverRoot, value))) return Path.Combine(serverRoot, value);
        string sibling = Path.Combine(folder, value);
        if (serverRoot != null || File.Exists(sibling)) return sibling;
        for (string dir = Path.GetDirectoryName(folder); dir != null; dir = Path.GetDirectoryName(dir))
            if (File.Exists(Path.Combine(dir, value))) return Path.Combine(dir, value);
        return sibling;
    }

    // Ordered map of int -> original line, like the Python dict with setdefault/overwrite.
    sealed class Originals
    {
        public readonly List<int> Order = new List<int>();
        public readonly Dictionary<int, string> Lines = new Dictionary<int, string>();
        public void Set(int key, string line) { if (!Lines.ContainsKey(key)) Order.Add(key); Lines[key] = line; }
    }

    public static string ConfiguredSource(Settings settings, string source)
    {
        settings.Validate();
        Dictionary<string, Originals> originals = new Dictionary<string, Originals>();
        List<string> lines = Text.Lines(source);
        foreach (string line in lines)
        {
            Match m = Call.Match(line.Trim());
            if (!m.Success) continue;
            if (!originals.ContainsKey(m.Groups[1].Value)) originals[m.Groups[1].Value] = new Originals();
            originals[m.Groups[1].Value].Set(int.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture), line);
        }
        Func<string, Originals> of = fn => originals.ContainsKey(fn) ? originals[fn] : new Originals();
        Func<string, IEnumerable<int>, List<string>> entries = (fn, ids) =>
        {
            Originals old = of(fn);
            List<string> result = new List<string>();
            foreach (int value in ids)
            {
                if (old.Lines.ContainsKey(value)) { result.Add(old.Lines[value]); continue; }
                string flags = "";
                if (fn == "AddHeadPalette") flags = ", " + (settings.IncludeDoram ? "true" : "false");
                else if (fn == "AddDoramHeadStyle") flags = ", true";
                result.Add("StylingShop." + fn + "(" + value + ", { zeny = " + settings.NewEntryPrice + " }" + flags + ")");
            }
            return result;
        };

        // Keep official clothing indices first (0,2,3,...7); append missing colors
        // afterwards, including ID 1. This retains the Doram prefix and ticket costs.
        Originals oldClothes = of("AddBodyPalette");
        List<int> clothIds = oldClothes.Order.Where(v => v <= settings.MaxClothColor).ToList();
        clothIds.AddRange(Enumerable.Range(0, settings.MaxClothColor + 1).Where(v => !oldClothes.Lines.ContainsKey(v)));
        List<int> hairIds = Enumerable.Range(1, settings.MaxHairStyle).ToList();
        List<int> paletteIds = Enumerable.Range(1, settings.MaxHairColor).ToList();
        List<int> doramHair = settings.IncludeDoram ? hairIds : of("AddDoramHeadStyle").Order.Where(i => i <= settings.MaxHairStyle).ToList();
        List<int> doramCloth = settings.IncludeDoram ? clothIds : of("AddDoramBodyPalette").Order.Where(i => i <= settings.MaxClothColor).ToList();
        Dictionary<string, List<string>> replacements = new Dictionary<string, List<string>>
        {
            { "AddHeadPalette", entries("AddHeadPalette", paletteIds) },
            { "AddHeadStyle", entries("AddHeadStyle", hairIds) },
            { "AddBodyPalette", entries("AddBodyPalette", clothIds) },
            { "AddDoramHeadStyle", entries("AddDoramHeadStyle", doramHair) },
            { "AddDoramBodyPalette", entries("AddDoramBodyPalette", doramCloth) },
        };
        HashSet<string> emitted = new HashSet<string>();
        StringBuilder output = new StringBuilder();
        foreach (string line in lines)
        {
            Match m = Call.Match(line.Trim());
            string fn = m.Success ? m.Groups[1].Value : null;
            if (fn != null && replacements.ContainsKey(fn))
            {
                if (emitted.Add(fn))
                    foreach (string entry in replacements[fn]) output.Append(entry).Append('\n');
            }
            else output.Append(line).Append('\n');
        }
        if (output.Length == 0) output.Append('\n');
        return output.ToString();
    }

    sealed class Entry
    {
        public int Value;
        public int? Job;
        public Dictionary<string, int> Human, Doram;
        public bool? ColorableDoram;
        public bool LineageOnly;
        public int RequiredSex;
    }

    static readonly string[] Fields = { "second", "trans", "third", "third_t", "alternate", "fourth" };
    static readonly string[] TierNames = { "second", "trans", "third", "third_t", "fourth" };
    static readonly int[] TierValues = { 2, 3, 4, 4, 5 };

    static long Key(int origin, int target) { return ((long)origin << 32) | (uint)target; }

    // full mirrors stylist::lineage_allows: every job of a branch wears every
    // outfit of the branch. full=false is the earlier rule (earlier tiers plus the
    // fourth job), kept only so already published indices stay in place.
    static Dictionary<long, int> LineagePairs(ServerData data, bool includeFourth, bool full)
    {
        Dictionary<string, int> sexes = new Dictionary<string, int> { { "SEX_FEMALE", 0 }, { "SEX_MALE", 1 }, { "SEX_BOTH", 2 } };
        Dictionary<long, int> pairs = new Dictionary<long, int>();
        const int NONE = ServerData.None;
        foreach (Match m in Regex.Matches(data.LineageHeader, @"^STYLIST_LINEAGE\((.*)\)$", RegexOptions.Multiline))
        {
            string[] parts = m.Groups[1].Value.Split(',').Select(p => p.Trim()).ToArray();
            if (!sexes.ContainsKey(parts[0])) throw new ToolError("Unknown lineage sex: " + parts[0]);
            if (parts.Length != Fields.Length + 1) throw new ToolError("Invalid lineage row: " + m.Groups[1].Value);
            int sex = sexes[parts[0]];
            Dictionary<string, int> row = new Dictionary<string, int>();
            for (int i = 0; i < Fields.Length; i++) row[Fields[i]] = data.Job(parts[i + 1]);
            int third = row["third_t"] != NONE ? row["third_t"] : row["third"];
            for (int t = 0; t < TierNames.Length; t++)
            {
                int tier = TierValues[t], origin = row[TierNames[t]];
                if (origin == NONE) continue;
                int[] targets = full
                    ? new[] { origin, row["second"], row["trans"], tier != 4 ? third : NONE, row["alternate"], row["fourth"] }
                    : new[] { origin,
                        tier > 2 ? row["second"] : NONE,
                        tier > 3 ? row["trans"] : NONE,
                        tier > 4 ? third : NONE,
                        tier >= 4 ? row["alternate"] : NONE,
                        includeFourth ? row["fourth"] : NONE };
                foreach (int target in targets)
                {
                    if (target == NONE) continue;
                    long key = Key(origin, target);
                    int previous;
                    pairs[key] = !pairs.TryGetValue(key, out previous) || previous == sex ? sex : 2;
                }
            }
        }
        return pairs;
    }

    static int[] Numbers(string args)
    {
        string head = args.Split('{')[0].TrimEnd(',', ' ');
        return head.Split(',').Select(v =>
        {
            int n;
            if (!int.TryParse(v.Trim(), NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out n))
                throw new ToolError("Invalid number in source table: " + v.Trim());
            return n;
        }).ToArray();
    }

    public sealed class Result { public string Yaml, Client, Lineage; public JsonObject Summary; }

    public static Result Generate(string text, ServerData data)
    {
        byte[] sourceBytes = Text.Bytes(text);
        List<string> looks = new List<string>();
        Dictionary<string, Dictionary<int, Entry>> catalog = new Dictionary<string, Dictionary<int, Entry>>();
        Func<string, Dictionary<int, Entry>> look = name =>
        {
            if (!catalog.ContainsKey(name)) { catalog[name] = new Dictionary<int, Entry>(); looks.Add(name); }
            return catalog[name];
        };
        Dictionary<string, int> counters = new Dictionary<string, int>();
        List<JsonObject> disabled = new List<JsonObject>();
        List<int> disabledIndices = new List<int>();
        List<string> clientLines = new List<string>();
        foreach (string line in Text.Lines(text))
        {
            Match m = AnyCall.Match(line.Trim());
            if (!m.Success) { clientLines.Add(line); continue; }
            string fn = m.Groups[1].Value, args = m.Groups[2].Value;
            int[] nums = Numbers(args);
            Dictionary<string, int> costs = new Dictionary<string, int>();
            foreach (Match c in Regex.Matches(args, @"(zeny|itid|boxitid)\s*=\s*(\d+)"))
                costs[c.Groups[1].Value] = int.Parse(c.Groups[2].Value, CultureInfo.InvariantCulture);
            List<string> flags = Regex.Matches(args, @"\b(true|false)\b").Cast<Match>().Select(f => f.Groups[1].Value).ToList();
            if (fn == "AddCostumeChange")
            {
                int index = nums[0], origin = nums[1], target = nums[2];
                // This upstream does not implement the 4355 playable class or 4353 sprite.
                if (origin == 4355)
                {
                    JsonObject item = new JsonObject();
                    item.Add("index", index); item.Add("origin", origin); item.Add("target", target);
                    item.Add("reason", "Original job is not implemented by this rAthena base");
                    disabled.Add(item); disabledIndices.Add(index);
                    clientLines.Add(Unsupported + line);
                    continue;
                }
                look("Body2")[index] = new Entry { Value = target, Job = origin, Human = costs, Doram = costs };
            }
            else if (Functions.ContainsKey(fn))
            {
                string name = Functions[fn][0], race = Functions[fn][1];
                int index;
                counters.TryGetValue(fn, out index);
                counters[fn] = ++index;
                Dictionary<int, Entry> entries = look(name);
                Entry entry;
                if (!entries.TryGetValue(index, out entry)) entries[index] = entry = new Entry { Value = nums[0] };
                if (entry.Value != nums[0]) throw new ToolError("Mismatched " + fn + " value at index " + index + ".");
                if (race == "CostsHuman") entry.Human = costs; else entry.Doram = costs;
                if ((fn == "AddHeadPalette" || fn.EndsWith("Accessory")) && flags.Count > 0 && flags[0] == "true") entry.Doram = costs;
                if (fn == "AddDoramHeadStyle") entry.ColorableDoram = flags.Count > 0 ? flags[0] == "true" : true;
            }
            else if (fn != "AddSecondCostume" && fn != "AddDoramSecondCostume")
                throw new ToolError("Unknown StylingShop function: " + fn);
            clientLines.Add(line);
        }
        Dictionary<string, int> free = new Dictionary<string, int> { { "zeny", 0 } };
        look("Hair_Color")[-1] = new Entry { Value = 0, Human = free, Doram = free };
        if (!catalog.ContainsKey("Clothes_Color")) throw new ToolError("The source table has no AddBodyPalette entries.");
        catalog["Clothes_Color"][-1] = new Entry { Value = 0, Human = free, Doram = free };

        // Keep all existing indices stable. The client sizes CostumeChange with Lua's
        // length operator and walks it with an index cursor, so extensions must follow
        // the official entries without gaps. Disabled official entries stay in the
        // client table (no player can hold their origin job; the server rejects them).
        List<string> lineageClient = clientLines.Select(l => l.StartsWith(Unsupported)
            ? l.Substring(Unsupported.Length) + " -- Not supported by this server base" : l).ToList();
        lineageClient.Add("");
        lineageClient.Add("-- Requires stylist_class_lineage: on on the server.");
        Dictionary<int, Entry> body2 = look("Body2");
        HashSet<long> existing = new HashSet<long>(body2.Values.Select(e => Key(e.Job.Value, e.Value)));
        int next = body2.Keys.Concat(disabledIndices).Max() + 1, lineageCount = 0;
        // Published order: earlier rule without fourth jobs, then its fourth-job
        // additions, then the full-branch additions. Existing indices never move.
        Dictionary<long, int> first = LineagePairs(data, false, false);
        Dictionary<long, int> second = LineagePairs(data, true, false);
        Dictionary<long, int> complete = LineagePairs(data, true, true);
        if (second.Keys.Any(k => !complete.ContainsKey(k))) throw new ToolError("Inconsistent lineage definitions.");
        List<long> keys = first.Keys.OrderBy(k => k).ToList();
        keys.AddRange(second.Keys.Where(k => !first.ContainsKey(k)).OrderBy(k => k));
        keys.AddRange(complete.Keys.Where(k => !second.ContainsKey(k)).OrderBy(k => k));
        foreach (long key in keys)
        {
            if (existing.Contains(key)) continue;
            int origin = (int)(key >> 32), target = (int)(key & 0xFFFFFFFF), sex = complete[key];
            Dictionary<string, int> costs = origin == target
                ? new Dictionary<string, int> { { "zeny", 0 } }
                : new Dictionary<string, int> { { "itid", 6959 }, { "boxitid", 6959 } };
            Entry entry = new Entry { Value = target, Job = origin, LineageOnly = true, RequiredSex = sex };
            if (origin == 4218 || origin == 4220 || origin == 4308) entry.Doram = costs; else entry.Human = costs;
            body2[next] = entry;
            string price = origin == target ? "zeny = 0" : "itid = 6959, boxitid = 6959";
            lineageClient.Add("StylingShop.AddCostumeChange(" + next + ", " + origin + ", " + target + ", { " + price + " })");
            next++; lineageCount++;
        }
        if (next > 32767) throw new ToolError("Stylist indices exceed the server index type");

        StringBuilder y = new StringBuilder();
        foreach (string header in new[] { "# Generated by tools/catalogue/generate_catalogue.py. Edit source Lua/lineages, then regenerate.",
            "# Client table attribution is preserved in client/stylist/source/stylingshopinfo.lub.", "Header:", "  Type: STYLIST_DB", "  Version: 2", "", "Body:" })
            y.Append(header).Append('\n');
        foreach (string name in looks)
        {
            y.Append("  - Look: ").Append(name).Append("\n    Options:\n");
            foreach (KeyValuePair<int, Entry> pair in catalog[name].OrderBy(p => p.Key))
            {
                Entry e = pair.Value;
                string value = name.StartsWith("Head_") ? data.Item(e.Value) : e.Value.ToString(CultureInfo.InvariantCulture);
                y.Append("      - Index: ").Append(pair.Key).Append('\n');
                y.Append("        Value: ").Append(value).Append('\n');
                if (e.Job.HasValue) y.Append("        RequiredJob: ").Append(e.Job.Value).Append('\n');
                if (e.ColorableDoram.HasValue) y.Append("        ColorableDoram: ").Append(e.ColorableDoram.Value ? "true" : "false").Append('\n');
                if (e.LineageOnly) y.Append("        LineageOnly: true\n        RequiredSex: ").Append(e.RequiredSex).Append('\n');
                foreach (KeyValuePair<string, Dictionary<string, int>> race in new[] {
                    new KeyValuePair<string, Dictionary<string, int>>("CostsHuman", e.Human),
                    new KeyValuePair<string, Dictionary<string, int>>("CostsDoram", e.Doram) })
                {
                    if (race.Value == null) continue;
                    int amount;
                    y.Append("        ").Append(race.Key).Append(":\n");
                    y.Append("          Price: ").Append(race.Value.TryGetValue("zeny", out amount) ? amount : 0).Append('\n');
                    if (race.Value.TryGetValue("itid", out amount) && amount != 0)
                        y.Append("          RequiredItem: ").Append(data.Item(amount)).Append('\n');
                    if (race.Value.TryGetValue("boxitid", out amount) && amount != 0)
                        y.Append("          RequiredItemBox: ").Append(data.Item(amount)).Append('\n');
                }
            }
        }
        JsonObject counts = new JsonObject();
        foreach (string name in looks) counts.Add(name, catalog[name].Count);
        JsonObject summary = new JsonObject();
        summary.Add("source_sha256", Text.Sha256(sourceBytes));
        summary.Add("counts", counts);
        summary.Add("lineage_only", lineageCount);
        summary.Add("disabled", disabled);
        return new Result
        {
            Yaml = y.ToString(),
            Client = string.Join("\n", clientLines) + "\n",
            Lineage = string.Join("\n", lineageClient) + "\n",
            Summary = summary,
        };
    }

    public static List<KeyValuePair<string, string>> BuildFiles(Settings settings, string source, ServerData data)
    {
        string configured = ConfiguredSource(settings, source);
        Result r = Generate(configured, data);
        StringBuilder config = new StringBuilder(
            "// Generated Stylist appearance limits. Import after other battle settings.\n" +
            "// Counts are maximum IDs; color 0 is the default, outside the requested count.\n" +
            "min_hair_style: 0\nmin_hair_color: 0\nmin_cloth_color: 0\n");
        foreach (string key in Settings.Keys) config.Append(key).Append(": ").Append(settings.Get(key)).Append('\n');
        config.Append("pet_hair_style: ").Append(Math.Max(100, settings.MaxHairStyle + 1)).Append('\n');
        JsonObject saved = new JsonObject();
        saved.Add("max_cloth_color", settings.MaxClothColor);
        saved.Add("max_hair_color", settings.MaxHairColor);
        saved.Add("max_hair_style", settings.MaxHairStyle);
        saved.Add("include_doram", settings.IncludeDoram);
        saved.Add("new_entry_price", settings.NewEntryPrice);
        List<KeyValuePair<string, string>> files = new List<KeyValuePair<string, string>>();
        Action<string, string> add = (name, value) => files.Add(new KeyValuePair<string, string>(name, value));
        add("db/re/stylist_modern.yml", r.Yaml);
        add("client/Files/" + ClientPath, r.Client);
        add("client/LineageFiles/" + ClientPath, r.Lineage);
        add("conf/battle/stylist_generated.conf", config.ToString());
        add("source/stylingshopinfo.lub", configured);
        add("settings.json", JsonObject.Dump(saved) + "\n");
        add("catalogue.json", JsonObject.Dump(r.Summary) + "\n");
        add("INSTALL.md", InstallText(settings));
        JsonObject manifest = new JsonObject();
        foreach (KeyValuePair<string, string> file in files) manifest.Add(file.Key, Text.Sha256(Text.Bytes(file.Value)));
        add("manifest.json", JsonObject.Dump(manifest) + "\n");
        return files;
    }

    public static string WritePackage(Settings settings, string output, string source, ServerData data)
    {
        List<KeyValuePair<string, string>> files = BuildFiles(settings, source, data);
        output = Path.GetFullPath(output);
        if (File.Exists(output) || (Directory.Exists(output) && Directory.EnumerateFileSystemEntries(output).Any()))
            throw new ToolError("Output must be a new or empty directory: " + output);
        Directory.CreateDirectory(output);
        foreach (KeyValuePair<string, string> file in files)
        {
            string target = Path.Combine(output, file.Key.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(target));
            Text.Write(target, file.Value);
        }
        return output;
    }

    public static string NewOutputFolder()
    {
        return Path.Combine(PackageRoot, "generated", DateTime.Now.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture) +
            "-" + Guid.NewGuid().ToString("N").Substring(0, 6));
    }

    static string InstallText(Settings s)
    {
        string doram = s.IncludeDoram ? "True" : "False";
        return "# Generated Stylist catalogue\n\n" +
"Clothing colors: **" + s.MaxClothColor + "** (IDs 1 through " + s.MaxClothColor + ").\n" +
"Hair colors: **" + s.MaxHairColor + "** (IDs 1 through " + s.MaxHairColor + ").\n" +
"Hairstyles: **" + s.MaxHairStyle + "** (IDs 1 through " + s.MaxHairStyle + ").\n" +
"Color 0 is the default and does not count toward either color quantity.\n" +
"Extend Doram resources: **" + doram + "**.\n\n" +
"1. Back up your installed Stylist table, server catalogue, and battle settings.\n" +
"2. Copy `db/re/stylist_modern.yml` into the same path in your server. Replace the\n" +
"   complete file: merging into `db/import` would leave stale options when shrinking.\n" +
"   Check `db/import/stylist_modern.yml` for overrides of generated entries.\n" +
"3. Copy `conf/battle/stylist_generated.conf` into your server. Add\n" +
"   `import: conf/battle/stylist_generated.conf` at the end of\n" +
"   `conf/import/battle_conf.txt`. Later overrides must not lower these limits.\n" +
"4. Choose ONE client table: `client/LineageFiles` for `stylist_class_lineage: on`,\n" +
"   or `client/Files` for `stylist_class_lineage: off`. Copy its `data` folder into\n" +
"   your client GRF at `" + ClientPath + "`. Do not install both variants.\n" +
"5. Restart the map server and client together. This requires the modern Stylist\n" +
"   server integration; deploy the compiled lineage update first if needed.\n" +
"6. Verify the highest color and hairstyle IDs, purchases, and reconnect persistence\n" +
"   for every supported sex, class and species in your actual client.\n\n" +
"Existing entries retain their ticket/zeny prices. Newly added entries cost\n" +
s.NewEntryPrice + " zeny. Returning to default color uses the free reset\n" +
"selection. Clothing keeps its original indices first, then appends missing IDs.\n" +
"The default generated package extends human options and retains available Doram\n" +
"options within the selected limits. `--include-doram` extends Doram too; existing\n" +
"non-colorable Doram hairstyles retain their restriction.\n\n" +
"This package registers resources you already have. It does not create sprite,\n" +
"ACT, or PAL assets, change hardcoded client limits, or translate the native UI.\n" +
"Install compatible resources for every enabled ID. The integer bounds protect\n" +
"server storage and purchase indices; actual client support must be verified.\n\n" +
"To reproduce this package, run `tools\\StylistTools.exe --from-conf\n" +
"<package>/conf/battle/stylist_generated.conf` (or the same options with\n" +
"`python tools/catalogue/configure_catalogue.py`) with the same `--include-doram`\n" +
"and `--new-entry-price` choices recorded in `settings.json`.\n" +
"Use `--source <package>/source/stylingshopinfo.lub` when reproducing edited source tables.\n" +
"`manifest.json` contains SHA-256 hashes of every other file.\n";
    }

    // Writes the job constants and the item names used by the source table, so the
    // EXE can generate catalogues without access to a server tree.
    public static string ExportReference(string serverRoot, string source)
    {
        ServerData data = ServerData.FromServer(serverRoot);
        SortedSet<int> items = new SortedSet<int> { 6959 };
        foreach (string line in Text.Lines(source))
        {
            Match m = AnyCall.Match(line.Trim());
            if (!m.Success) continue;
            if (m.Groups[1].Value.EndsWith("Accessory")) items.Add(Numbers(m.Groups[2].Value)[0]);
            foreach (Match c in Regex.Matches(m.Groups[2].Value, @"(itid|boxitid)\s*=\s*(\d+)"))
                items.Add(int.Parse(c.Groups[2].Value, CultureInfo.InvariantCulture));
        }
        StringBuilder b = new StringBuilder("# Stylist reference data exported from a patched rAthena tree.\n" +
            "# Rebuild with: powershell -File tools\\source\\build.ps1 -Server <rAthena folder>\n");
        foreach (KeyValuePair<string, int> job in data.Jobs.OrderBy(j => j.Value).ThenBy(j => j.Key, StringComparer.Ordinal))
            b.Append("job ").Append(job.Key).Append(' ').Append(job.Value).Append('\n');
        foreach (int id in items) b.Append("item ").Append(id).Append(' ').Append(data.Item(id)).Append('\n');
        return b.ToString();
    }
}
