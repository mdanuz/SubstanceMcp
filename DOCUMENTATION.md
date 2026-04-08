# Substance Painter MCP Server — Documentation

Bridges Claude AI with Adobe Substance 3D Painter (Steam or standalone) via
Substance Painter's built-in HTTP remote scripting server.

---

## Architecture

```
Claude Desktop
     │
     ├─ MCP stdio ──► Maya MCP Server (maya_mcp_server.py)
     │                      │
     │                 TCP socket · localhost:7001
     │                      │
     │                 Maya 2026 commandPort
     │
     └─ MCP stdio ──► SP MCP Server (substance_painter_mcp_server.py)
                            │
                       HTTP POST · localhost:24981/run
                            │
                       Substance Painter scripting server
```

Both servers run as separate processes and are registered in
`%APPDATA%\Claude\claude_desktop_config.json` under different keys.
Claude sees all tools from both simultaneously (prefixed `maya_` and `sp_`).

---

## Requirements

- Windows 10/11
- Python 3.11+
- Adobe Substance 3D Painter (Steam version: `steam://rungameid/3366290` or standalone)
- Claude Desktop with MCP support

---

## Quick Start

### 1. Run the setup script

```
H:\Substance MCP\setup_substance.bat
```

This will:
- Create a Python virtual environment (`.venv`)
- Install `mcp` and `pydantic`
- Merge the SP server entry into your Claude Desktop config
  (preserves the existing Maya MCP entry)

### 2. Enable remote scripting in Substance Painter

Open Substance Painter, then:
```
Edit > Settings > Scripting > Enable remote scripting server
```
The server listens on `localhost:24981`.

In Substance Painter 9.x+, this may already be enabled by default.

### 3. Restart Claude Desktop

The new `substance_painter` server will appear alongside the existing `maya` server.

### 4. Verify the connection

Ask Claude:
> "Get the current Substance Painter project info"

---

## Claude Desktop Config

After running setup, your config at `%APPDATA%\Claude\claude_desktop_config.json`
should look like:

```json
{
  "mcpServers": {
    "maya": {
      "command": "H:/Maya MCP/.venv/Scripts/python.exe",
      "args": ["H:/Maya MCP/maya_mcp_server.py"]
    },
    "substance_painter": {
      "command": "H:/Substance MCP/.venv/Scripts/python.exe",
      "args": ["H:/Substance MCP/substance_painter_mcp_server.py"]
    }
  }
}
```

---

## Tool Reference

### Project Management

| Tool | Description |
|------|-------------|
| `sp_project_info` | Get current project path, save state, normal map format |
| `sp_open_project` | Open an existing `.spp` project file |
| `sp_save_project` | Save project in-place or save-as to a new path |
| `sp_new_project` | Create a new project from an FBX/OBJ mesh file |

### Texture Sets

| Tool | Description |
|------|-------------|
| `sp_list_texture_sets` | List all texture sets (one per mesh material) |
| `sp_get_texture_set_info` | Get resolution, channels, UV tile mode |
| `sp_set_resolution` | Set output resolution: 512, 1024, 2048, 4096 |
| `sp_add_channel` | Add a channel (Emissive, Opacity, AO, etc.) |

### Baking

| Tool | Description |
|------|-------------|
| `sp_bake_maps` | Bake normal, AO, curvature, position, thickness maps |
| `sp_get_baking_parameters` | Read current bake config for a texture set |

### Layer Management

| Tool | Description |
|------|-------------|
| `sp_list_layers` | List all layers with name, type, opacity, blend mode |
| `sp_create_fill_layer` | Create a fill layer with color, roughness, metallic |
| `sp_create_paint_layer` | Create a paint layer |
| `sp_create_folder` | Create a layer group/folder |
| `sp_set_layer_properties` | Update visibility, opacity, blend mode, name |

### Materials & Resources

| Tool | Description |
|------|-------------|
| `sp_list_resources` | List smart materials, alphas, brushes, etc. |
| `sp_apply_smart_material` | Apply a smart material from the SP library |

### Export

| Tool | Description |
|------|-------------|
| `sp_list_export_presets` | List available export presets |
| `sp_export_textures` | Export texture maps (Arnold, PBR, Unreal, Unity, etc.) |

### Utilities

| Tool | Description |
|------|-------------|
| `sp_import_resource` | Import an external file as a SP resource |
| `sp_execute_python` | Run arbitrary Python in SP (full API access) |

### Maya Bridge Tools (in Maya MCP server)

| Tool | Description |
|------|-------------|
| `maya_export_for_substance` | Export FBX optimized for SP (smoothing groups, tangents, Y-up) |
| `maya_import_sp_textures` | Scan SP export folder and connect textures to a Maya material |

---

## Full Pipeline: Maya → Substance Painter → Maya

```
1. maya_scene_info
   → Check what's in the Maya scene

2. maya_export_for_substance
   → file_path: "C:/Projects/Hero/HeroMesh.fbx"
   → objects: ["hero_body", "hero_head"]

3. sp_new_project
   → mesh_path: "C:/Projects/Hero/HeroMesh.fbx"
   → normal_map_format: "DirectX"

4. sp_list_texture_sets
   → See ["hero_body_MAT", "hero_head_MAT"]

5. sp_set_resolution
   → texture_set: "hero_body_MAT", resolution: 4096

6. sp_bake_maps
   → texture_set: "hero_body_MAT"
   → maps: ["NormalWorldSpace", "AmbientOcclusion", "Curvature", "Position"]
   → high_poly_path: "C:/Projects/Hero/HeroMesh_hi.fbx"  (optional)

7. sp_apply_smart_material
   → texture_set: "hero_body_MAT"
   → material_name: "Worn Metal"

8. sp_save_project
   → file_path: "C:/Projects/Hero/Hero.spp"

9. sp_export_textures
   → output_path: "C:/Projects/Hero/Textures/"
   → preset: "Arnold 5 (AiStandard)"
   → file_format: "png"

10. maya_import_sp_textures
    → texture_dir: "C:/Projects/Hero/Textures/"
    → mesh_name: "hero_body"
    → shader_type: "aiStandardSurface"

11. maya_render_frame
    → (optional) validate result in Arnold
```

---

## Texture Channel Suffix Map

`maya_import_sp_textures` recognizes these filename suffixes automatically:

| Suffix(es) | Maya Shader Channel |
|------------|---------------------|
| `_BaseColor`, `_Base_Color`, `_Albedo`, `_Diffuse` | baseColor |
| `_Roughness`, `_Rough` | specularRoughness |
| `_Metallic`, `_Metalness`, `_Metal` | metalness |
| `_Normal`, `_NormalGL`, `_NormalDX` | normalCamera (via bump2d) |
| `_Emissive`, `_Emission` | emissionColor |
| `_Height`, `_Displacement` | displacement shader |
| `_AmbientOcclusion`, `_AO` | (skipped — baked into surface) |
| `_Opacity`, `_Alpha` | opacity |
| `_Specular`, `_SpecularColor` | specularColor |

---

## Troubleshooting

**"Cannot connect to Substance Painter on port 24981"**
→ Open SP and enable: Edit > Settings > Scripting > Enable remote scripting server

**"Smart material 'X' not found"**
→ Use `sp_list_resources` with `resource_type: "smartmaterial"` to see available names

**"Texture set not found"**
→ Use `sp_list_texture_sets` to see the exact names SP created from the mesh

**Textures imported to wrong shader channel**
→ Check the export preset used in SP — suffix conventions vary between presets.
   Use `sp_execute_python` to inspect exported files and `maya_execute_python`
   to connect channels manually.

**FBX export fails in Maya**
→ Ensure the FBX plugin is loaded: Windows > Settings/Preferences > Plug-in Manager > fbxmaya.mll

---

## Notes

- All paths should use **forward slashes** (`/`) to avoid issues across Python environments
- Substance Painter creates one texture set per material slot on the imported mesh
- Texture set names in SP match the material names assigned in Maya before FBX export
- The scripting server must be re-enabled each time SP is launched (unless SP 9.x+ auto-enables it)
