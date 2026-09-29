# Client files

`data/luafiles514/lua files/stylingshop/stylingshopinfo.lub` is the default expanded
outfit table for `stylist_class_lineage: on`. `alternatives/standard/data` contains
the mutually exclusive standard table for `off`. Both match the shipped server YAML
and **667 BodyColors / 42 HairStyles / 5 HairColors**.

Import the chosen `data` tree into the client GRF. Use the version with the highest
effective priority for that Lua path. The client patcher installs the two background
textures used by its numeric selectors when it patches the EXE.

The client needs the corresponding character PAL/SPR/ACT resources for every enabled
appearance. This update does not include a full game client or character resource pack.

`source/stylingshopinfo.lub` preserves the translated table's original attribution and
is the input template for the optional catalogue generator. Install the configured
table under `data`, rather than this source template.

To change the BodyColor, HairStyle or HairColor quantities and generate your own files,
follow [Change the appearance counts](../tools/README.md#change-the-appearance-counts).
