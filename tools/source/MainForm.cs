using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

internal sealed class MainForm : Form
{
    readonly NumericUpDown cloth = Count(0), hairColor = Count(0), hairStyle = Count(1);
    readonly NumericUpDown price = new NumericUpDown { Minimum = 0, Maximum = int.MaxValue, Value = 100000, ThousandsSeparator = true, Width = 140 };
    readonly CheckBox doram = new CheckBox { Text = "Also extend Doram options (only if your client has the Doram resources)", AutoSize = true };
    readonly CheckBox advanced = new CheckBox { Text = "Show advanced options", AutoSize = true };
    readonly TextBox server = new TextBox { Dock = DockStyle.Fill };
    readonly TextBox source = new TextBox { Dock = DockStyle.Fill };
    readonly TextBox output = new TextBox { Dock = DockStyle.Fill };
    readonly Button generate = new Button { Text = "Generate files", AutoSize = true, Padding = new Padding(16, 4, 16, 4) };
    readonly Button openFolder = new Button { Text = "Open result folder", AutoSize = true, Enabled = false };
    readonly Button openGuide = new Button { Text = "Open install steps", AutoSize = true, Enabled = false };
    readonly Label status = new Label { AutoSize = true, MaximumSize = new Size(560, 0) };
    readonly TextBox verifyResult = new TextBox { Multiline = true, ReadOnly = true, Dock = DockStyle.Fill, ScrollBars = ScrollBars.Vertical };
    readonly TableLayoutPanel advancedPanel = Grid(3);
    string lastOutput;

    static NumericUpDown Count(int minimum)
    {
        return new NumericUpDown { Minimum = minimum, Maximum = Settings.MaxCount, Width = 110, ThousandsSeparator = false };
    }

    static TableLayoutPanel Grid(int columns, bool stretch = true)
    {
        TableLayoutPanel grid = new TableLayoutPanel { ColumnCount = columns, AutoSize = true, Dock = DockStyle.Top, Padding = new Padding(0, 4, 0, 4) };
        for (int i = 0; i < columns; i++)
            grid.ColumnStyles.Add(i == 1 && stretch ? new ColumnStyle(SizeType.Percent, 100) : new ColumnStyle(SizeType.AutoSize));
        return grid;
    }

    static Label Caption(string text, bool bold = false)
    {
        return new Label
        {
            Text = text, AutoSize = true, Anchor = AnchorStyles.Left, Padding = new Padding(0, 6, 8, 0),
            Font = bold ? new Font(SystemFonts.MessageBoxFont, FontStyle.Bold) : null,
        };
    }

    static Label Hint(string text)
    {
        return new Label { Text = text, AutoSize = true, ForeColor = SystemColors.GrayText, MaximumSize = new Size(560, 0), Padding = new Padding(0, 0, 0, 6) };
    }

    public MainForm()
    {
        Text = "Stylist Tools";
        Font = SystemFonts.MessageBoxFont;
        AutoScaleMode = AutoScaleMode.Font;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(640, 600);
        MinimumSize = new Size(560, 480);

        TabControl tabs = new TabControl { Dock = DockStyle.Fill };
        tabs.TabPages.Add(CatalogueTab());
        tabs.TabPages.Add(PatcherTab());
        tabs.TabPages.Add(VerifyTab());
        Controls.Add(tabs);
        AcceptButton = generate;
        ResetCounts();
        server.Text = Program.ServerFolder(null) ?? "";
        output.Text = Catalogue.NewOutputFolder();
    }

    TabPage CatalogueTab()
    {
        TabPage page = new TabPage("1. Appearance counts") { Padding = new Padding(12), AutoScroll = true };
        FlowLayoutPanel column = new FlowLayoutPanel { FlowDirection = FlowDirection.TopDown, WrapContents = false, Dock = DockStyle.Fill, AutoScroll = true };

        column.Controls.Add(Caption("How many choices should players see in the Stylist?", true));
        column.Controls.Add(Hint("Each number is the highest ID offered. Color 0 (the original color) is always included in addition. " +
            "Your game client must already have the sprites/palettes for every ID you enable."));

        TableLayoutPanel counts = Grid(3, false);
        AddRow(counts, "Clothing colors (BodyColor):", cloth, "IDs 1 to N");
        AddRow(counts, "Hair colors (HairColor):", hairColor, "IDs 1 to N");
        AddRow(counts, "Hairstyles (HairStyle):", hairStyle, "IDs 1 to N");
        column.Controls.Add(counts);

        FlowLayoutPanel presets = new FlowLayoutPanel { AutoSize = true, WrapContents = false };
        Button reset = new Button { Text = "Use package values", AutoSize = true };
        reset.Click += delegate { Run(ResetCounts); };
        Button load = new Button { Text = "Load from a .conf file...", AutoSize = true };
        load.Click += delegate { LoadConf(); };
        presets.Controls.Add(reset);
        presets.Controls.Add(load);
        column.Controls.Add(presets);

        column.Controls.Add(Caption("Save the result in (a new, empty folder):", true));
        TableLayoutPanel outputRow = Grid(3);
        outputRow.Width = 580;
        outputRow.Controls.Add(Caption("Folder:"), 0, 0);
        outputRow.Controls.Add(output, 1, 0);
        outputRow.Controls.Add(BrowseButton(output, "Choose an empty folder for the generated files"), 2, 0);
        column.Controls.Add(outputRow);

        advanced.CheckedChanged += delegate { advancedPanel.Visible = advanced.Checked; };
        column.Controls.Add(advanced);
        advancedPanel.Visible = false;
        advancedPanel.Width = 580;
        advancedPanel.Controls.Add(Caption("Price of new entries (zeny):"), 0, 0);
        advancedPanel.Controls.Add(price, 1, 0);
        advancedPanel.Controls.Add(doram, 0, 1);
        advancedPanel.SetColumnSpan(doram, 3);
        advancedPanel.Controls.Add(Caption("rAthena folder (optional):"), 0, 2);
        advancedPanel.Controls.Add(server, 1, 2);
        advancedPanel.Controls.Add(BrowseButton(server, "Select your patched rAthena folder (the one containing src and db)"), 2, 2);
        Label serverHint = Hint("Leave empty to use the data built into this tool for the tested rAthena base. " +
            "Select your server only if you changed jobs, lineages or item names.");
        advancedPanel.Controls.Add(serverHint, 0, 3);
        advancedPanel.SetColumnSpan(serverHint, 3);
        advancedPanel.Controls.Add(Caption("Custom source table (optional):"), 0, 4);
        advancedPanel.Controls.Add(source, 1, 4);
        Button pickSource = new Button { Text = "Browse...", AutoSize = true };
        pickSource.Click += delegate
        {
            using (OpenFileDialog dialog = new OpenFileDialog { Filter = "StylingShop table (*.lub;*.lua)|*.lub;*.lua|All files (*.*)|*.*" })
                if (dialog.ShowDialog(this) == DialogResult.OK) source.Text = dialog.FileName;
        };
        advancedPanel.Controls.Add(pickSource, 2, 4);
        column.Controls.Add(advancedPanel);

        FlowLayoutPanel actions = new FlowLayoutPanel { AutoSize = true, WrapContents = false, Padding = new Padding(0, 8, 0, 4) };
        generate.Font = new Font(SystemFonts.MessageBoxFont, FontStyle.Bold);
        generate.Click += delegate { Generate(); };
        openFolder.Click += delegate { Program.Open(lastOutput); };
        openGuide.Click += delegate { Program.Open(Path.Combine(lastOutput, "INSTALL.md")); };
        actions.Controls.Add(generate);
        actions.Controls.Add(openFolder);
        actions.Controls.Add(openGuide);
        column.Controls.Add(actions);
        column.Controls.Add(status);

        page.Controls.Add(column);
        return page;
    }

    TabPage PatcherTab()
    {
        TabPage page = new TabPage("2. Patch the client") { Padding = new Padding(12) };
        FlowLayoutPanel column = new FlowLayoutPanel { FlowDirection = FlowDirection.TopDown, WrapContents = false, Dock = DockStyle.Fill };
        column.Controls.Add(Caption("Add the numeric selectors to your game client", true));
        column.Controls.Add(Hint("1. Close the game and back up your client folder.\n" +
            "2. Open the patcher and choose your client EXE. Patching starts immediately.\n" +
            "3. Backups are created beside each modified file (*.pre-stylist.bak). Restore them to undo.\n\n" +
            "Patching the client is needed once. Changing the appearance counts later does not require patching again."));
        Button open = new Button { Text = "Open client patcher", AutoSize = true, Padding = new Padding(16, 4, 16, 4) };
        open.Click += delegate
        {
            string patcher = Path.Combine(Catalogue.PackageRoot, "patcher", "StylistUIPatcher.exe");
            if (File.Exists(patcher)) Run(delegate { Program.Open(patcher); });
            else Error("StylistUIPatcher.exe was not found in " + Path.GetDirectoryName(patcher) + ".");
        };
        column.Controls.Add(open);
        page.Controls.Add(column);
        return page;
    }

    TabPage VerifyTab()
    {
        TabPage page = new TabPage("Check package") { Padding = new Padding(12) };
        TableLayoutPanel layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 3 };
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.Controls.Add(Hint("Confirms that no file in this package is missing or was changed (SHA256SUMS.txt) and that the " +
            "server files match the patch. Nothing is modified.\n\nPackage authors: after finishing every change, use Create SHA256SUMS.txt " +
            "to record the current files, then publish the package."), 0, 0);
        Button run = new Button { Text = "Check package files", AutoSize = true };
        run.Click += delegate { ShowResult(delegate { return Verify.Run(Catalogue.PackageRoot); }, "Verification failed: "); };
        Button create = new Button { Text = "Create SHA256SUMS.txt", AutoSize = true };
        create.Click += delegate
        {
            string manifest = Path.Combine(Catalogue.PackageRoot, "SHA256SUMS.txt");
            if (File.Exists(manifest) && MessageBox.Show(this, "SHA256SUMS.txt already exists. Replace it with the hashes of the current files?",
                    "Stylist Tools", MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2) != DialogResult.Yes)
                return;
            ShowResult(delegate { return Verify.WriteChecksums(Catalogue.PackageRoot); }, "");
        };
        FlowLayoutPanel buttons = new FlowLayoutPanel { AutoSize = true, WrapContents = false };
        buttons.Controls.Add(run);
        buttons.Controls.Add(create);
        layout.Controls.Add(buttons, 0, 1);
        layout.Controls.Add(verifyResult, 0, 2);
        page.Controls.Add(layout);
        return page;
    }

    void ShowResult(Func<string> action, string failurePrefix)
    {
        Cursor = Cursors.WaitCursor;
        try { verifyResult.Text = action().Replace("\n", "\r\n"); verifyResult.ForeColor = Color.DarkGreen; }
        catch (Exception error) { verifyResult.Text = (failurePrefix + error.Message).Replace("\n", "\r\n"); verifyResult.ForeColor = Color.DarkRed; }
        finally { Cursor = Cursors.Default; }
    }

    static void AddRow(TableLayoutPanel grid, string label, Control input, string hint)
    {
        int row = grid.RowCount++;
        grid.Controls.Add(Caption(label), 0, row);
        grid.Controls.Add(input, 1, row);
        grid.Controls.Add(new Label { Text = hint, AutoSize = true, ForeColor = SystemColors.GrayText, Anchor = AnchorStyles.Left }, 2, row);
    }

    Button BrowseButton(TextBox target, string description)
    {
        Button button = new Button { Text = "Browse...", AutoSize = true };
        button.Click += delegate
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog { Description = description, ShowNewFolderButton = true })
            {
                if (Directory.Exists(target.Text)) dialog.SelectedPath = target.Text;
                if (dialog.ShowDialog(this) == DialogResult.OK) target.Text = dialog.SelectedPath;
            }
        };
        return button;
    }

    void SetCounts(Dictionary<string, int> values)
    {
        Action<NumericUpDown, string> set = (box, key) =>
        {
            if (values.ContainsKey(key)) box.Value = Math.Max(box.Minimum, Math.Min(box.Maximum, values[key]));
        };
        set(cloth, "max_cloth_color");
        set(hairColor, "max_hair_color");
        set(hairStyle, "max_hair_style");
    }

    void ResetCounts() { SetCounts(Catalogue.DefaultCounts()); }

    void LoadConf()
    {
        using (OpenFileDialog dialog = new OpenFileDialog { Filter = "rAthena configuration (*.conf;*.txt)|*.conf;*.txt|All files (*.*)|*.*" })
        {
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            Run(delegate
            {
                Dictionary<string, int> values = Catalogue.ReadConf(dialog.FileName, Program.ServerFolder(server.Text));
                if (values.Count == 0) throw new ToolError("No max_cloth_color, max_hair_color or max_hair_style setting was found in that file.");
                SetCounts(values);
                status.ForeColor = SystemColors.ControlText;
                status.Text = "Loaded " + values.Count + " setting(s) from " + dialog.FileName + ".";
            });
        }
    }

    void Generate()
    {
        Cursor = Cursors.WaitCursor;
        generate.Enabled = false;
        try
        {
            Settings settings = new Settings
            {
                MaxClothColor = (int)cloth.Value, MaxHairColor = (int)hairColor.Value, MaxHairStyle = (int)hairStyle.Value,
                IncludeDoram = doram.Checked, NewEntryPrice = (int)price.Value,
            };
            if (output.Text.Trim().Length == 0) output.Text = Catalogue.NewOutputFolder();
            string text = source.Text.Trim().Length > 0 ? global::Text.Read(source.Text.Trim()) : Catalogue.DefaultSource();
            lastOutput = Catalogue.WritePackage(settings, output.Text.Trim(), text, Program.Load(Program.ServerFolder(server.Text)));
            status.ForeColor = Color.DarkGreen;
            status.Text = "Done. " + settings.MaxClothColor + " clothing colors, " + settings.MaxHairColor + " hair colors and " +
                settings.MaxHairStyle + " hairstyles were written to:\n" + lastOutput +
                "\n\nNext: open the install steps and copy the files to your server and client.";
            openFolder.Enabled = openGuide.Enabled = true;
            output.Text = Catalogue.NewOutputFolder();
        }
        catch (Exception error)
        {
            status.ForeColor = Color.DarkRed;
            status.Text = "Could not generate the files: " + error.Message;
        }
        finally
        {
            generate.Enabled = true;
            Cursor = Cursors.Default;
        }
    }

    void Run(Action action)
    {
        try { action(); }
        catch (Exception error) { Error(error.Message); }
    }

    void Error(string message) { MessageBox.Show(this, message, "Stylist Tools", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
}
