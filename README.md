# SubstanceMCP

A [Model Context Protocol](https://modelcontextprotocol.io/) server that gives **Claude AI** direct control over **Adobe Substance 3D Painter 2026** — manage projects, bake maps, create layers, apply smart materials, and export PBR textures.

---

## What it does

Claude connects to a live Substance Painter session via a socket plugin and can:

- Open, create, and save SP projects
- List and configure texture sets and resolutions
- Bake normal, AO, curvature, position, and thickness maps
- Create fill layers, paint layers, and folders
- Apply smart materials from the SP library
- Export textures with any preset (Unity, Unreal, Arnold, etc.)
- Run arbitrary Python code inside SP's environment
- Bridge with Maya: import SP-exported maps directly onto Arnold materials

---

## Architecture

```
Claude Desktop
     │
     ▼  MCP (stdio)
substance_painter_mcp_server.py  ──→  TCP Socket (localhost:7002)  ──→  sp_socket_plugin.py
                                                                              │
                                                                    Substance Painter 2026
                                                                    (substance_painter.* API)
```

The plugin receives Python code strings, executes them inside SP's Qt main thread (thread-safe), and returns results via the same socket.

---

## Requirements

| Requirement | Version |
|---|---|
| Windows | 10 / 11 |
| Python | 3.11+ |
| Adobe Substance 3D Painter | 2026 (Steam or standalone) |
| Claude Desktop | Latest |

---

## Quick Start

1. Clone or download this repo (e.g. `H:\Substance MCP\`)
2. Right-click **`setup_substance.bat`** → **Run as administrator**
   - Creates a Python `.venv` and installs dependencies
   - Copies `sp_socket_plugin.py` to SP's plugins folder
   - Merges the MCP server into your existing Claude Desktop config (safe — won't overwrite other servers)
3. Open **Substance Painter 2026**
4. In SP menu: **Python → Reload Plugins**
   - You should see: `[SP MCP Plugin] MCP socket plugin loaded. Listening on localhost:7002.`
5. Restart **Claude Desktop**
6. Ask Claude: *"Get SP project info"*

---

## Manual Setup

```bash
# 1. Create venv and install deps
python -m venv .venv
.venv\Scripts\pip install mcp>=1.0.0 pydantic>=2.0.0

# 2. Copy plugin to SP's plugins folder (Steam path)
copy sp_socket_plugin.py "C:\Program Files (x86)\Steam\steamapps\common\Substance 3D Painter 2026\resources\python\plugins\"

# 3. Add to Claude Desktop config (merge — do not replace existing entries)
# Path: %APPDATA%\Claude\claude_desktop_config.json
```

```json
{
  "mcpServers": {
    "substance_painter": {
      "command": "H:/Substance MCP/.venv/Scripts/python.exe",
      "args": ["H:/Substance MCP/substance_painter_mcp_server.py"]
    }
  }
}
```

---

## MCP Tools

### Project
| Tool | Description |
|---|---|
| `sp_project_info` | Get current project name, mesh, texture sets |
| `sp_open_project` | Open an existing `.spp` file |
| `sp_new_project` | Create a new project from an FBX mesh |
| `sp_save_project` | Save the current project |

### Texture Sets
| Tool | Description |
|---|---|
| `sp_list_texture_sets` | List all texture sets in the project |
| `sp_get_texture_set_info` | Get channels, resolution, UV info |
| `sp_set_resolution` | Set resolution per texture set |
| `sp_add_channel` | Add a channel (e.g. Emissive, Opacity) |

### Baking
| Tool | Description |
|---|---|
| `sp_bake_maps` | Bake normal, AO, curvature, position, thickness |
| `sp_get_baking_parameters` | Read current bake settings |

### Layers
| Tool | Description |
|---|---|
| `sp_list_layers` | List the layer stack |
| `sp_create_fill_layer` | Create a fill layer with color/metalness/roughness |
| `sp_create_paint_layer` | Create an empty paint layer |
| `sp_create_folder` | Create a folder in the layer stack |
| `sp_set_layer_properties` | Set name, visibility, opacity, blending mode |

### Materials & Export
| Tool | Description |
|---|---|
| `sp_list_resources` | List smart materials and resources |
| `sp_apply_smart_material` | Apply a smart material to a texture set |
| `sp_list_export_presets` | List available export presets |
| `sp_export_textures` | Export textures to a folder |

### Utilities
| Tool | Description |
|---|---|
| `sp_import_resource` | Import a texture or asset into the project |
| `sp_execute_python` | Run arbitrary Python inside SP |

---

## Maya → Substance Painter → Maya Pipeline

When used together with [MayaMCP](https://github.com/mdanuz/MayaMCP):

```
1. maya_export_for_substance   →  export FBX with smoothing groups
2. sp_new_project              →  open FBX in Substance Painter
3. sp_bake_maps                →  bake normal / AO / curvature
4. sp_apply_smart_material     →  apply smart material
5. sp_export_textures          →  export PBR maps
6. maya_import_sp_textures     →  connect maps to Arnold material in Maya
```

---

## Verify the Connection

After setup, run this to confirm the plugin is running:

```bash
.venv\Scripts\python test_connection.py
```

Expected output:
```
Connecting to localhost:7002...
Connected!
Response: 'hello from test'
```

---

## Troubleshooting

**Plugin not loading in SP**
- Make sure you ran `setup_substance.bat` as Administrator
- In SP: Python → Reload Plugins
- Check SP's Python console for errors

**Claude can't connect**
- Verify SP is open and the plugin is loaded (port 7002 must be listening)
- Run `test_connection.py` to isolate whether it's an SP or Claude issue

**Port 7002 already in use**
- Another process is using port 7002 — restart SP to re-bind the plugin

**MCP server not appearing in Claude Desktop**
- Fully quit Claude Desktop (system tray → right-click → Quit), then reopen
- Check `%APPDATA%\Claude\claude_desktop_config.json` has the `substance_painter` entry
