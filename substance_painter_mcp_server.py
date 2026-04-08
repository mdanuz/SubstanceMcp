#!/usr/bin/env python3
"""
Substance Painter MCP Server

Bridges Claude AI with Adobe Substance 3D Painter via a Python plugin
(sp_socket_plugin.py) that runs inside SP and listens on localhost:7002.

This uses the same TCP socket + null-terminator protocol as the Maya MCP
server (Maya uses port 7001, Substance Painter uses port 7002).

Usage:
    1. Copy sp_socket_plugin.py to your SP plugins directory:
       C:\\Users\\<YourName>\\Documents\\Adobe\\Adobe Substance 3D Painter\\python\\plugins\\
    2. Open Adobe Substance 3D Painter (Steam or standalone)
    3. Load the plugin:  Python > Reload Plugins  (or restart SP)
    4. Run this server:  python substance_painter_mcp_server.py
    5. Connect Claude Desktop via the MCP config
"""

import json
import socket
import textwrap
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Server init
# ---------------------------------------------------------------------------
mcp = FastMCP("substance_painter_mcp")

SP_HOST = "localhost"
SP_PORT = 7002          # Port opened by sp_socket_plugin.py inside SP
SOCKET_TIMEOUT = 120.0


# ---------------------------------------------------------------------------
# Substance Painter socket communication (same protocol as Maya MCP)
# ---------------------------------------------------------------------------
def _send_to_sp(code: str) -> str:
    """Send Python code to Substance Painter via the MCP socket plugin.

    Uses the same TCP + null-terminator protocol as _send_to_maya().
    sp_socket_plugin.py must be installed and loaded inside SP first.
    """
    payload = (code.strip() + "\x00").encode("utf-8")
    try:
        with socket.create_connection((SP_HOST, SP_PORT), timeout=SOCKET_TIMEOUT) as s:
            s.sendall(payload)
            chunks = []
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\x00" in chunk:
                    break
            response = b"".join(chunks).decode("utf-8", errors="replace").rstrip("\x00").strip()
            return response
    except ConnectionRefusedError:
        return (
            f"ERROR: Cannot connect to Substance Painter on port {SP_PORT}. "
            "Make sure sp_socket_plugin.py is installed in SP's plugins folder and loaded. "
            "In SP: Python > Reload Plugins  (or restart SP after copying the plugin file)."
        )
    except TimeoutError:
        return "ERROR: Connection to Substance Painter timed out. SP may be busy."
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def _sp_eval(code: str) -> str:
    """Run code in SP, wrapping in try/except.

    Code blocks must use print() for their output — the plugin captures stdout.
    """
    safe = f"""
import traceback as _tb
try:
{textwrap.indent(code.strip(), '    ')}
except Exception as _e:
    print('ERROR: ' + _tb.format_exc())
"""
    return _send_to_sp(safe)


# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------
class ExecInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    code: str = Field(..., description="Python code to execute inside Substance Painter")


class ProjectInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    file_path: Optional[str] = Field(None, description="Path to .spp project file")
    mesh_path: Optional[str] = Field(
        None,
        description="Path to mesh file (.fbx, .obj, .abc) for new project creation"
    )
    normal_map_format: str = Field(
        "DirectX",
        description="Normal map format for new project: 'DirectX' or 'OpenGL'"
    )


class SaveProjectInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    file_path: Optional[str] = Field(
        None,
        description="Save-as path (.spp). Leave empty to save in-place."
    )


class TextureSetInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., description="Texture set name (usually matches the mesh material name)")


class ResolutionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    texture_set: str = Field(..., description="Texture set name")
    resolution: int = Field(2048, description="Resolution in pixels (must be power of two): 512, 1024, 2048, 4096")


class AddChannelInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    texture_set: str = Field(..., description="Texture set name")
    channel_type: str = Field(
        ...,
        description=(
            "Channel type to add. Common types: 'BaseColor', 'Roughness', 'Metallic', "
            "'Normal', 'Height', 'Emissive', 'Opacity', 'AmbientOcclusion', 'Specular', "
            "'Glossiness', 'Displacement', 'Transmissive', 'Reflection', 'Refraction'"
        )
    )


class BakingInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    texture_set: str = Field(..., description="Texture set name to bake maps for")
    high_poly_path: Optional[str] = Field(
        None,
        description="Path to high-poly mesh .fbx for baking (leave empty to bake from low-poly itself)"
    )
    maps: list = Field(
        default=["NormalWorldSpace", "AmbientOcclusion", "Curvature", "Position", "Thickness"],
        description=(
            "List of maps to bake. Valid values: 'NormalWorldSpace', 'AmbientOcclusion', "
            "'Curvature', 'Position', 'Thickness', 'Normal' (tangent-space), 'ID', "
            "'MeshID', 'UV', 'WireframeAndMesh'"
        )
    )
    resolution: int = Field(2048, description="Bake map resolution: 512, 1024, 2048, 4096")
    antialiasing: str = Field(
        "Subsampling_2x_2",
        description="Anti-aliasing: 'None', 'Subsampling_2x_2', 'Subsampling_4x_4', 'Subsampling_8x_8'"
    )
    dilation_width: int = Field(16, description="Dilation width in pixels for baked maps")


class LayerInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    texture_set: str = Field(..., description="Texture set name to add the layer to")
    name: str = Field(..., description="Layer name")
    base_color: Optional[list] = Field(
        None,
        description="[r, g, b] base color in 0.0–1.0 range for fill layers"
    )
    roughness: Optional[float] = Field(None, description="Roughness value 0.0–1.0 for fill layers")
    metallic: Optional[float] = Field(None, description="Metallic value 0.0–1.0 for fill layers")
    opacity: float = Field(1.0, description="Layer opacity 0.0–1.0")
    blend_mode: str = Field(
        "Normal",
        description="Blend mode: 'Normal', 'Multiply', 'Screen', 'Overlay', 'SoftLight', 'Hardlight', 'ColorDodge', 'ColorBurn', 'Darken', 'Lighten', 'Difference'"
    )


class LayerPropsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    texture_set: str = Field(..., description="Texture set the layer belongs to")
    layer_name: str = Field(..., description="Layer name to modify")
    visible: Optional[bool] = Field(None, description="Set layer visibility")
    opacity: Optional[float] = Field(None, description="Set layer opacity 0.0–1.0")
    blend_mode: Optional[str] = Field(None, description="Set blend mode string")
    new_name: Optional[str] = Field(None, description="Rename the layer to this name")


class MaterialInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    texture_set: str = Field(..., description="Texture set name to apply material to")
    material_name: str = Field(
        ...,
        description="Smart material or material preset name from SP's Shelf (e.g. 'Worn Metal', 'Concrete Tiles')"
    )
    layer_name: Optional[str] = Field(None, description="Name for the new layer created. Defaults to material name.")


class ResourceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    resource_type: str = Field(
        "smartmaterial",
        description=(
            "Resource type to list: 'smartmaterial', 'material', 'alpha', 'brush', "
            "'filter', 'generator', 'texture', 'shader', 'environment'"
        )
    )
    search_query: Optional[str] = Field(None, description="Name filter / search string")


class ExportInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    output_path: str = Field(
        ...,
        description="Directory path for exported textures (use forward slashes, e.g. C:/Projects/MyAsset/Textures/)"
    )
    texture_sets: Optional[list] = Field(
        None,
        description="List of texture set names to export. None = export all texture sets."
    )
    preset: str = Field(
        "PBR Metallic Roughness",
        description=(
            "Export preset name. Common presets: 'PBR Metallic Roughness', "
            "'PBR Specular Glossiness', 'Arnold 5 (AiStandard)', 'V-Ray 5 (VRayMtl)', "
            "'Unreal Engine 4 (Packed)', 'Unity HD Render Pipeline (Metallic Standard)', "
            "'Sketchfab'"
        )
    )
    file_format: str = Field("png", description="Image format: 'png', 'exr', 'tiff', 'jpeg'")
    resolution: Optional[int] = Field(
        None,
        description="Override resolution: 512, 1024, 2048, 4096. None = use per-texture-set resolution."
    )
    bit_depth: str = Field(
        "8",
        description="Bit depth per channel: '8', '16', '16f' (16-bit float), '32f'"
    )
    padding: str = Field(
        "Dilation infinite",
        description="UV padding algorithm: 'Dilation infinite', 'Dilation', 'Transparent'"
    )


class ImportResourceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    file_path: str = Field(..., description="Path to the file to import (use forward slashes)")
    resource_type: str = Field(
        "texture",
        description="Resource type: 'texture', 'alpha', 'environment', 'font'"
    )
    name: Optional[str] = Field(None, description="Display name for the imported resource")


class ReloadMeshInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    mesh_path: Optional[str] = Field(
        None,
        description="Path to the new mesh file. Leave empty to reload from the original path."
    )
    import_cameras: bool = Field(False, description="Import cameras from the mesh file")
    preserve_strokes: bool = Field(True, description="Preserve paint strokes on reload")


class DisplaySettingsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    environment: Optional[str] = Field(
        None,
        description="HDRI environment resource name from SP shelf (e.g. 'Tomoco Studio', 'Casual Day')"
    )
    tone_mapping: Optional[str] = Field(
        None,
        description="Tone mapping function: 'None', 'Reinhard', 'ACES Filmic', 'Exposure'"
    )
    exposure: Optional[float] = Field(None, description="Exposure value in EV (e.g. 0.0, 1.0, -1.0)")


# ---------------------------------------------------------------------------
# Tools — Project Management
# ---------------------------------------------------------------------------
@mcp.tool(
    name="sp_project_info",
    annotations={"title": "Get Substance Painter Project Info", "readOnlyHint": True},
)
async def sp_project_info() -> str:
    """Get information about the currently open Substance Painter project.

    Returns JSON with:
    - is_open: whether a project is currently open
    - file_path: path to the .spp file (if saved)
    - is_saved: whether the project has unsaved changes
    - normal_map_format: 'DirectX' or 'OpenGL'
    - uv_tile_workflow: whether UV tiles (UDIMs) are enabled
    """
    code = """
import substance_painter.project as sp_project
import json

if not sp_project.is_open():
    print(json.dumps({"is_open": False, "message": "No project is currently open"}))
else:
    info = {
        "is_open": True,
        "file_path": sp_project.file_path() or "unsaved",
        "is_saved": sp_project.is_saved(),
        "normal_map_format": str(sp_project.last_imported_mesh_settings().normal_map if sp_project.last_imported_mesh_settings() else "unknown"),
    }
    try:
        info["uv_tile_workflow"] = sp_project.uv_tiles() is not None
    except Exception:
        info["uv_tile_workflow"] = "unknown"
    print(json.dumps(info))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_open_project",
    annotations={"title": "Open Substance Painter Project", "readOnlyHint": False, "destructiveHint": True},
)
async def sp_open_project(params: ProjectInput) -> str:
    """Open an existing Substance Painter project (.spp file).

    Warning: this will close the currently open project.
    Save first with sp_save_project if needed.

    Returns:
        str: Confirmation with the opened project path
    """
    code = f"""
import substance_painter.project as sp_project
file_path = {repr(params.file_path)}
sp_project.open(file_path)
print(f"Opened project: {{file_path}}")
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_save_project",
    annotations={"title": "Save Substance Painter Project", "readOnlyHint": False},
)
async def sp_save_project(params: SaveProjectInput) -> str:
    """Save the current Substance Painter project.

    If file_path is provided, saves to that location (save-as).
    If file_path is empty, saves in-place (overwrites current file).

    Returns:
        str: Confirmation with saved file path
    """
    code = f"""
import substance_painter.project as sp_project
file_path = {repr(params.file_path)}
if file_path:
    sp_project.save_as(file_path)
    print(f"Saved project to: {{file_path}}")
else:
    sp_project.save()
    print(f"Saved project in-place: {{sp_project.file_path()}}")
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_new_project",
    annotations={"title": "Create New Substance Painter Project", "readOnlyHint": False, "destructiveHint": True},
)
async def sp_new_project(params: ProjectInput) -> str:
    """Create a new Substance Painter project from a mesh file.

    This is the primary entry point for the Maya → Substance Painter workflow.
    Pass the FBX file path exported from Maya via maya_export_for_substance.

    The normal_map_format should match your renderer:
    - 'DirectX' for DirectX-based renderers (most game engines)
    - 'OpenGL' for OpenGL-based renderers (Maya viewport, Arnold, etc.)

    Returns:
        str: Confirmation with project details and texture set list
    """
    code = f"""
import substance_painter.project as sp_project
import json

mesh_path = {repr(params.mesh_path)}
normal_format = {repr(params.normal_map_format)}

settings = sp_project.Settings(
    import_cameras=False,
    normal_map_format=(
        sp_project.NormalMapFormat.DirectX
        if normal_format == "DirectX"
        else sp_project.NormalMapFormat.OpenGL
    ),
)
sp_project.create(mesh_file_path=mesh_path, settings=settings)
print(json.dumps({{
    "status": "Project created",
    "mesh": mesh_path,
    "normal_map_format": normal_format,
    "note": "Call sp_list_texture_sets to verify once SP finishes loading",
}}))
"""
    return _sp_eval(code)


# ---------------------------------------------------------------------------
# Tools — Texture Sets
# ---------------------------------------------------------------------------
@mcp.tool(
    name="sp_list_texture_sets",
    annotations={"title": "List Substance Painter Texture Sets", "readOnlyHint": True},
)
async def sp_list_texture_sets() -> str:
    """List all texture sets in the current Substance Painter project.

    Each texture set corresponds to a material slot on the imported mesh.
    After importing from Maya, texture set names match Maya material names.

    Returns:
        str: JSON array of texture set names
    """
    code = """
import substance_painter.textureset as sp_ts
import json
sets = [ts.name() for ts in sp_ts.all_texture_sets()]
print(json.dumps({"texture_sets": sets, "count": len(sets)}))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_get_texture_set_info",
    annotations={"title": "Get Texture Set Details", "readOnlyHint": True},
)
async def sp_get_texture_set_info(params: TextureSetInput) -> str:
    """Get detailed information about a specific texture set.

    Returns resolution, enabled channels, UV tile mode, and whether
    mesh maps have been baked.

    Returns:
        str: JSON with texture set details
    """
    code = f"""
import substance_painter.textureset as sp_ts
import substance_painter.baking as sp_baking
import json

ts_name = {repr(params.name)}
ts = sp_ts.TextureSet.from_name(ts_name)

res = ts.get_resolution()
channels = {{str(ch): str(ts.get_channel(ch).format()) for ch in ts.all_channels()}}

info = {{
    "name": ts_name,
    "width": res.width,
    "height": res.height,
    "channels": channels,
}}

try:
    info["uv_tiles"] = [str(t) for t in ts.all_uv_tiles()]
except Exception:
    info["uv_tiles"] = []

print(json.dumps(info))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_set_resolution",
    annotations={"title": "Set Texture Set Resolution", "readOnlyHint": False},
)
async def sp_set_resolution(params: ResolutionInput) -> str:
    """Set the output resolution for a texture set.

    Resolution must be a power of two: 512, 1024, 2048, or 4096.
    Higher resolutions produce more detailed textures but take longer to export.

    Returns:
        str: Confirmation of new resolution
    """
    code = f"""
import substance_painter.textureset as sp_ts
ts_name = {repr(params.texture_set)}
resolution = {params.resolution}
ts = sp_ts.TextureSet.from_name(ts_name)
ts.set_resolution(sp_ts.Resolution(resolution, resolution))
print(f"Set {{ts_name}} resolution to {{resolution}}x{{resolution}}")
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_add_channel",
    annotations={"title": "Add Channel to Texture Set", "readOnlyHint": False},
)
async def sp_add_channel(params: AddChannelInput) -> str:
    """Add a new channel to a texture set (e.g., Emissive, Opacity, AO).

    By default, SP creates BaseColor, Roughness, Metallic, Normal, and Height.
    Use this tool to add additional channels like Emissive or Opacity.

    Returns:
        str: Confirmation of added channel
    """
    code = f"""
import substance_painter.textureset as sp_ts
ts_name = {repr(params.texture_set)}
channel_type_str = {repr(params.channel_type)}
ts = sp_ts.TextureSet.from_name(ts_name)
channel_type = getattr(sp_ts.ChannelType, channel_type_str)
ts.add_channel(channel_type, sp_ts.ChannelFormat.sRGB8)
print(f"Added channel '{{channel_type_str}}' to texture set '{{ts_name}}'")
"""
    return _sp_eval(code)


# ---------------------------------------------------------------------------
# Tools — Baking
# ---------------------------------------------------------------------------
@mcp.tool(
    name="sp_bake_maps",
    annotations={"title": "Bake Mesh Maps in Substance Painter", "readOnlyHint": False},
)
async def sp_bake_maps(params: BakingInput) -> str:
    """Bake mesh maps (normal, AO, curvature, position, thickness) for a texture set.

    Baking is the critical step after importing from Maya. It transfers surface
    detail from the high-poly mesh to texture maps used by the material layers.

    If high_poly_path is provided, bakes from high-poly to low-poly.
    Otherwise, bakes from the low-poly mesh itself (useful for AO, curvature, etc.).

    Returns:
        str: JSON with baking status and baked map list
    """
    code = f"""
import substance_painter.baking as sp_baking
import substance_painter.textureset as sp_ts
import json

ts_name = {repr(params.texture_set)}
high_poly_path = {repr(params.high_poly_path)}
map_names = {repr(params.maps)}
resolution = {params.resolution}
antialiasing_str = {repr(params.antialiasing)}
dilation_width = {params.dilation_width}

ts = sp_ts.TextureSet.from_name(ts_name)

# Build baking parameters
bake_params = sp_baking.BakingParameters.from_texture_set(ts)

# Set resolution
bake_params.common().set("Dilation", dilation_width)

# Set high-poly mesh if provided
if high_poly_path:
    try:
        bake_params.common().set("HighDefinitionMeshes", high_poly_path)
    except Exception as e:
        pass

# Map list
maps_to_bake = []
for map_name in map_names:
    try:
        baker = bake_params.baker(map_name)
        baker.set("Enabled", True)
        maps_to_bake.append(map_name)
    except Exception as e:
        pass

# Run bake
result = sp_baking.bake_selected_textures(bake_params)
print(json.dumps({{
    "status": "Baking complete",
    "texture_set": ts_name,
    "maps_baked": maps_to_bake,
    "resolution": resolution,
}}))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_get_baking_parameters",
    annotations={"title": "Get Baking Parameters", "readOnlyHint": True},
)
async def sp_get_baking_parameters(params: TextureSetInput) -> str:
    """Read the current baking configuration for a texture set.

    Use before sp_bake_maps to verify settings are correct.

    Returns:
        str: JSON with current baking parameters
    """
    code = f"""
import substance_painter.baking as sp_baking
import substance_painter.textureset as sp_ts
import json

ts_name = {repr(params.name)}
ts = sp_ts.TextureSet.from_name(ts_name)
bake_params = sp_baking.BakingParameters.from_texture_set(ts)

result = {{"texture_set": ts_name, "bakers": []}}
try:
    common = bake_params.common()
    result["dilation"] = common.get("Dilation")
    result["high_poly_mesh"] = common.get("HighDefinitionMeshes") or "none"
except Exception:
    pass

print(json.dumps(result))
"""
    return _sp_eval(code)


# ---------------------------------------------------------------------------
# Tools — Layer Management
# ---------------------------------------------------------------------------
@mcp.tool(
    name="sp_list_layers",
    annotations={"title": "List Layers in Texture Set", "readOnlyHint": True},
)
async def sp_list_layers(params: TextureSetInput) -> str:
    """List all layers in a texture set's layer stack.

    Returns each layer's name, type (fill/paint/folder/adjustment),
    opacity, blend mode, and visibility.

    Returns:
        str: JSON array of layer objects
    """
    code = f"""
import substance_painter.layerstack as sp_ls
import substance_painter.textureset as sp_ts
import json

ts_name = {repr(params.name)}
ts = sp_ts.TextureSet.from_name(ts_name)
stack = sp_ls.get_root_layer_nodes(ts)

def node_to_dict(node):
    d = {{
        "name": node.get_name(),
        "type": str(node.get_type()),
        "visible": node.is_visible(),
        "opacity": node.get_opacity(),
    }}
    try:
        d["blend_mode"] = str(node.get_blend_mode())
    except Exception:
        d["blend_mode"] = "unknown"
    try:
        children = node.get_nodes()
        if children:
            d["children"] = [node_to_dict(c) for c in children]
    except Exception:
        pass
    return d

layers = [node_to_dict(n) for n in stack]
print(json.dumps({{"texture_set": ts_name, "layers": layers, "count": len(layers)}}))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_create_fill_layer",
    annotations={"title": "Create Fill Layer", "readOnlyHint": False},
)
async def sp_create_fill_layer(params: LayerInput) -> str:
    """Create a new fill layer in the specified texture set's layer stack.

    Fill layers apply a uniform color or procedural material across the texture set.
    They are the primary way to set base color, roughness, and metallic values.

    Returns:
        str: Confirmation with new layer name
    """
    code = f"""
import substance_painter.layerstack as sp_ls
import substance_painter.textureset as sp_ts
import json

ts_name = {repr(params.texture_set)}
layer_name = {repr(params.name)}
base_color = {repr(params.base_color)}
roughness = {repr(params.roughness)}
metallic = {repr(params.metallic)}
opacity = {params.opacity}
blend_mode_str = {repr(params.blend_mode)}

ts = sp_ts.TextureSet.from_name(ts_name)
stack = sp_ls.get_root_layer_nodes(ts)

# Create fill node at top of stack
node = sp_ls.insert_node(
    sp_ls.InsertPosition.above_node(stack[0]) if stack else sp_ls.InsertPosition.inside_node(sp_ls.get_root_layer_nodes_context(ts)),
    sp_ls.NodeType.FillLayer,
)
node.set_name(layer_name)
node.set_opacity(opacity)

# Set blend mode
try:
    blend_mode = getattr(sp_ls.BlendingMode, blend_mode_str, sp_ls.BlendingMode.Normal)
    node.set_blend_mode(blend_mode)
except Exception:
    pass

# Set fill properties
try:
    fill = node.get_fill()
    if base_color:
        fill.set_channel_value(sp_ts.ChannelType.BaseColor, {{
            "r": base_color[0], "g": base_color[1], "b": base_color[2]
        }})
    if roughness is not None:
        fill.set_channel_value(sp_ts.ChannelType.Roughness, roughness)
    if metallic is not None:
        fill.set_channel_value(sp_ts.ChannelType.Metallic, metallic)
except Exception as e:
    pass

print(json.dumps({{"status": "Fill layer created", "name": layer_name, "texture_set": ts_name}}))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_create_paint_layer",
    annotations={"title": "Create Paint Layer", "readOnlyHint": False},
)
async def sp_create_paint_layer(params: LayerInput) -> str:
    """Create a new paint layer in the texture set's layer stack.

    Paint layers support brush strokes, generators, and filters.
    They are more flexible than fill layers but start empty.

    Returns:
        str: Confirmation with new layer name
    """
    code = f"""
import substance_painter.layerstack as sp_ls
import substance_painter.textureset as sp_ts
import json

ts_name = {repr(params.texture_set)}
layer_name = {repr(params.name)}
opacity = {params.opacity}
blend_mode_str = {repr(params.blend_mode)}

ts = sp_ts.TextureSet.from_name(ts_name)
stack = sp_ls.get_root_layer_nodes(ts)

node = sp_ls.insert_node(
    sp_ls.InsertPosition.above_node(stack[0]) if stack else sp_ls.InsertPosition.inside_node(sp_ls.get_root_layer_nodes_context(ts)),
    sp_ls.NodeType.PaintLayer,
)
node.set_name(layer_name)
node.set_opacity(opacity)

try:
    blend_mode = getattr(sp_ls.BlendingMode, blend_mode_str, sp_ls.BlendingMode.Normal)
    node.set_blend_mode(blend_mode)
except Exception:
    pass

print(json.dumps({{"status": "Paint layer created", "name": layer_name, "texture_set": ts_name}}))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_create_folder",
    annotations={"title": "Create Layer Folder", "readOnlyHint": False},
)
async def sp_create_folder(params: LayerInput) -> str:
    """Create a layer group/folder in the texture set's layer stack.

    Folders are useful for organizing layers into logical groups
    (e.g., 'Metal Base', 'Wear and Tear', 'Decals').

    Returns:
        str: Confirmation with folder name
    """
    code = f"""
import substance_painter.layerstack as sp_ls
import substance_painter.textureset as sp_ts
import json

ts_name = {repr(params.texture_set)}
folder_name = {repr(params.name)}
opacity = {params.opacity}

ts = sp_ts.TextureSet.from_name(ts_name)
stack = sp_ls.get_root_layer_nodes(ts)

node = sp_ls.insert_node(
    sp_ls.InsertPosition.above_node(stack[0]) if stack else sp_ls.InsertPosition.inside_node(sp_ls.get_root_layer_nodes_context(ts)),
    sp_ls.NodeType.GroupLayer,
)
node.set_name(folder_name)
node.set_opacity(opacity)

print(json.dumps({{"status": "Folder created", "name": folder_name, "texture_set": ts_name}}))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_set_layer_properties",
    annotations={"title": "Set Layer Properties", "readOnlyHint": False},
)
async def sp_set_layer_properties(params: LayerPropsInput) -> str:
    """Update properties on an existing layer: visibility, opacity, blend mode, or name.

    Searches the layer stack by name and applies the specified changes.

    Returns:
        str: JSON with updated layer properties
    """
    code = f"""
import substance_painter.layerstack as sp_ls
import substance_painter.textureset as sp_ts
import json

ts_name = {repr(params.texture_set)}
layer_name = {repr(params.layer_name)}
visible = {repr(params.visible)}
opacity = {repr(params.opacity)}
blend_mode_str = {repr(params.blend_mode)}
new_name = {repr(params.new_name)}

ts = sp_ts.TextureSet.from_name(ts_name)

def find_node(nodes, name):
    for n in nodes:
        if n.get_name() == name:
            return n
        try:
            found = find_node(n.get_nodes(), name)
            if found:
                return found
        except Exception:
            pass
    return None

node = find_node(sp_ls.get_root_layer_nodes(ts), layer_name)
if node is None:
    print(f"ERROR: Layer '{{layer_name}}' not found in texture set '{{ts_name}}'")
else:
    changes = []
    if visible is not None:
        node.set_visible(visible)
        changes.append(f"visible={visible}")
    if opacity is not None:
        node.set_opacity(opacity)
        changes.append(f"opacity={opacity}")
    if blend_mode_str is not None:
        try:
            blend_mode = getattr(sp_ls.BlendingMode, blend_mode_str, sp_ls.BlendingMode.Normal)
            node.set_blend_mode(blend_mode)
            changes.append(f"blend_mode={blend_mode_str}")
        except Exception:
            pass
    if new_name is not None:
        node.set_name(new_name)
        changes.append(f"renamed to '{new_name}'")
    print(json.dumps({{"layer": layer_name, "changes": changes}}))
"""
    return _sp_eval(code)


# ---------------------------------------------------------------------------
# Tools — Materials & Resources
# ---------------------------------------------------------------------------
@mcp.tool(
    name="sp_list_resources",
    annotations={"title": "List Substance Painter Resources", "readOnlyHint": True},
)
async def sp_list_resources(params: ResourceInput) -> str:
    """List available resources in Substance Painter's library.

    Use this to discover smart material names before applying them
    with sp_apply_smart_material.

    Returns:
        str: JSON array of resource names matching the type and search query
    """
    code = f"""
import substance_painter.resource as sp_resource
import json

resource_type_str = {repr(params.resource_type)}
search_query = {repr(params.search_query)}

type_map = {{
    "smartmaterial": sp_resource.Usage.BASE_MATERIAL,
    "material": sp_resource.Usage.BASE_MATERIAL,
    "alpha": sp_resource.Usage.ALPHA,
    "brush": sp_resource.Usage.BRUSH,
    "filter": sp_resource.Usage.FILTER,
    "generator": sp_resource.Usage.GENERATOR,
    "texture": sp_resource.Usage.TEXTURE,
    "environment": sp_resource.Usage.ENVIRONMENT,
}}

usage = type_map.get(resource_type_str.lower(), sp_resource.Usage.BASE_MATERIAL)

resources = []
for res in sp_resource.list_layer_stacks_resources(usage):
    name = res.identifier().name
    if search_query is None or search_query.lower() in name.lower():
        resources.append({{
            "name": name,
            "location": str(res.identifier().location),
        }})

print(json.dumps({{"type": resource_type_str, "count": len(resources), "resources": resources[:100]}}))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_apply_smart_material",
    annotations={"title": "Apply Smart Material", "readOnlyHint": False},
)
async def sp_apply_smart_material(params: MaterialInput) -> str:
    """Apply a smart material from Substance Painter's library to a texture set.

    Smart materials are complete PBR setups that include base color, roughness,
    metallic, normal, and other channels pre-configured (e.g., 'Worn Metal',
    'Concrete Tiles', 'Leather Rough').

    Use sp_list_resources to find available smart material names.

    Returns:
        str: JSON with applied material details
    """
    code = f"""
import substance_painter.resource as sp_resource
import substance_painter.layerstack as sp_ls
import substance_painter.textureset as sp_ts
import json

ts_name = {repr(params.texture_set)}
material_name = {repr(params.material_name)}
layer_name = {repr(params.layer_name)} or material_name

ts = sp_ts.TextureSet.from_name(ts_name)
stack = sp_ls.get_root_layer_nodes(ts)

# Find the smart material resource
resource = None
for res in sp_resource.list_layer_stacks_resources(sp_resource.Usage.BASE_MATERIAL):
    if res.identifier().name.lower() == material_name.lower():
        resource = res
        break

if resource is None:
    print(f"ERROR: Smart material '{{material_name}}' not found. Use sp_list_resources to see available materials.")
else:
    node = sp_ls.insert_node(
        sp_ls.InsertPosition.above_node(stack[0]) if stack else sp_ls.InsertPosition.inside_node(sp_ls.get_root_layer_nodes_context(ts)),
        sp_ls.NodeType.GroupLayer,
    )
    node.set_name(layer_name)
    sp_ls.apply_smart_material(node, resource)
    print(json.dumps({{
        "status": "Smart material applied",
        "material": material_name,
        "layer": layer_name,
        "texture_set": ts_name,
    }}))
"""
    return _sp_eval(code)


# ---------------------------------------------------------------------------
# Tools — Export
# ---------------------------------------------------------------------------
@mcp.tool(
    name="sp_list_export_presets",
    annotations={"title": "List Export Presets", "readOnlyHint": True},
)
async def sp_list_export_presets() -> str:
    """List all available texture export presets in Substance Painter.

    Presets determine which channels are exported and how they are combined
    (e.g., packing Metallic/Roughness/AO into a single texture).

    Returns:
        str: JSON array of preset names
    """
    code = """
import substance_painter.export as sp_export
import json

try:
    presets = sp_export.list_export_presets()
    names = [p.name for p in presets]
except AttributeError:
    # Fallback: common preset names
    names = [
        "PBR Metallic Roughness",
        "PBR Specular Glossiness",
        "Arnold 5 (AiStandard)",
        "Arnold 6 (AiStandard)",
        "V-Ray 5 (VRayMtl)",
        "Unreal Engine 4 (Packed)",
        "Unreal Engine 5 (Packed)",
        "Unity HD Render Pipeline (Metallic Standard)",
        "Sketchfab",
        "glTF PBR Metal Roughness",
    ]

print(json.dumps({"presets": names, "count": len(names)}))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_export_textures",
    annotations={"title": "Export Textures from Substance Painter", "readOnlyHint": False},
)
async def sp_export_textures(params: ExportInput) -> str:
    """Export texture maps from Substance Painter using a named export preset.

    This is the final step in the SP workflow before importing textures back
    into Maya via maya_import_sp_textures.

    After export, the output_path directory will contain texture files named
    by convention: <TextureSetName>_<ChannelName>.<format>
    (e.g., pCube1_BaseColor.png, pCube1_Roughness.png)

    Returns:
        str: JSON with export status and list of exported file paths
    """
    code = f"""
import substance_painter.export as sp_export
import substance_painter.textureset as sp_ts
import json, os

output_path = {repr(params.output_path)}
texture_sets = {repr(params.texture_sets)}
preset = {repr(params.preset)}
file_format = {repr(params.file_format)}
resolution = {repr(params.resolution)}
bit_depth = {repr(params.bit_depth)}
padding = {repr(params.padding)}

os.makedirs(output_path, exist_ok=True)

# Build texture set list to export
all_ts_names = [ts.name() for ts in sp_ts.all_texture_sets()]
export_ts = texture_sets if texture_sets else all_ts_names

# Build export config dict
export_list = [{{"rootPath": ts_name}} for ts_name in export_ts]

params_dict = {{
    "fileFormat": file_format,
    "bitDepth": bit_depth,
    "paddingAlgorithm": padding,
}}
if resolution:
    import math
    log2_res = int(math.log2(resolution))
    params_dict["sizeLog2"] = log2_res

export_config = {{
    "exportShaderParams": False,
    "exportPath": output_path,
    "exportList": export_list,
    "defaultExportPreset": preset,
    "exportParameters": [{{"parameters": params_dict}}],
}}

result = sp_export.export_project_textures(export_config)

exported = {{}}
try:
    for ts_name, file_list in result.textures.items():
        exported[ts_name] = file_list
except Exception:
    pass

print(json.dumps({{
    "status": str(result.status),
    "output_path": output_path,
    "preset": preset,
    "exported": exported,
    "message": str(result.message) if hasattr(result, "message") else "Export complete",
}}))
"""
    return _sp_eval(code)


# ---------------------------------------------------------------------------
# Tools — Resource & Asset Management
# ---------------------------------------------------------------------------
@mcp.tool(
    name="sp_import_resource",
    annotations={"title": "Import Resource into Substance Painter", "readOnlyHint": False},
)
async def sp_import_resource(params: ImportResourceInput) -> str:
    """Import an external file as a resource into the current Substance Painter session.

    Supported resource types:
    - 'texture': Import as a paintable texture / alpha source
    - 'alpha': Import as an alpha/stencil
    - 'environment': Import as an HDRI environment

    Returns:
        str: Confirmation with imported resource details
    """
    code = f"""
import substance_painter.resource as sp_resource
import json

file_path = {repr(params.file_path)}
resource_type = {repr(params.resource_type)}
name = {repr(params.name)}

usage_map = {{
    "texture": sp_resource.Usage.TEXTURE,
    "alpha": sp_resource.Usage.ALPHA,
    "environment": sp_resource.Usage.ENVIRONMENT,
}}
usage = usage_map.get(resource_type.lower(), sp_resource.Usage.TEXTURE)

result = sp_resource.import_project_resource(file_path, usage)
print(json.dumps({{
    "status": "Resource imported",
    "file": file_path,
    "type": resource_type,
    "name": result.identifier().name if result else (name or file_path),
}}))
"""
    return _sp_eval(code)


# ---------------------------------------------------------------------------
# Tools — Mesh & Resources
# ---------------------------------------------------------------------------
@mcp.tool(
    name="sp_reload_mesh",
    annotations={"title": "Reload Mesh in Substance Painter", "readOnlyHint": False},
)
async def sp_reload_mesh(params: ReloadMeshInput) -> str:
    """Reload the project mesh, optionally from a new file path.

    Use this after updating the mesh in Maya via maya_export_for_substance —
    it updates the geometry in SP without losing your layers and paint work.

    Returns:
        str: JSON with reload status and any warnings
    """
    code = f"""
import substance_painter.project as sp_project
import json

mesh_path = {repr(params.mesh_path)}
preserve_strokes = {repr(params.preserve_strokes)}
import_cameras = {repr(params.import_cameras)}

if not sp_project.is_open():
    print(json.dumps({{"status": "error", "message": "No project is open"}}))
else:
    settings = sp_project.MeshReloadingSettings(
        import_cameras=import_cameras,
        preserve_strokes=preserve_strokes,
    )
    if mesh_path:
        status = sp_project.reload_mesh(mesh_path, settings)
    else:
        status = sp_project.reload_mesh(sp_project.last_imported_mesh_path(), settings)
    print(json.dumps({{
        "status": str(status),
        "mesh_path": sp_project.last_imported_mesh_path(),
        "warnings": [str(w) for w in sp_project.warnings()],
    }}))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_get_project_warnings",
    annotations={"title": "Get Project Warnings", "readOnlyHint": True},
)
async def sp_get_project_warnings() -> str:
    """Get any warnings on the current project (missing resources, outdated assets, etc.).

    Returns:
        str: JSON list of warning messages
    """
    code = """
import substance_painter.project as sp_project
import json

if not sp_project.is_open():
    print(json.dumps({"status": "error", "message": "No project is open"}))
else:
    warnings = [str(w) for w in sp_project.warnings()]
    print(json.dumps({"warnings": warnings, "count": len(warnings)}))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_list_project_resources",
    annotations={"title": "List Resources Used in Project", "readOnlyHint": True},
)
async def sp_list_project_resources() -> str:
    """List all resources (textures, smart materials, filters, etc.) currently used in the project.

    Useful for auditing what assets are referenced and checking for missing/outdated resources.

    Returns:
        str: JSON list of resources with name, type, and location
    """
    code = """
import substance_painter.resource as sp_resource
import json

resources = sp_resource.list_project_resources()
result = []
for r in resources:
    try:
        result.append({
            "name": r.identifier().name,
            "location": str(r.identifier().location),
            "type": str(r.type()),
            "internal_path": r.identifier().context,
        })
    except Exception:
        result.append({"name": str(r), "error": "could not read details"})

print(json.dumps({"resources": result, "count": len(result)}))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_reload_resources",
    annotations={"title": "Reload Modified External Resources", "readOnlyHint": False},
)
async def sp_reload_resources() -> str:
    """Reload any external resources (textures, etc.) that have been modified on disk.

    Use this after updating source textures externally — SP will pick up the changes
    without needing to re-import manually.

    Returns:
        str: JSON with reload status
    """
    code = """
import substance_painter.resource as sp_resource
import json

if sp_resource.is_reload_modified_resources_running():
    print(json.dumps({"status": "already_running", "message": "Resource reload already in progress"}))
else:
    sp_resource.reload_modified_resources_async()
    print(json.dumps({"status": "started", "message": "Reload of modified resources started"}))
"""
    return _sp_eval(code)


@mcp.tool(
    name="sp_set_display_settings",
    annotations={"title": "Set Viewport Display Settings", "readOnlyHint": False},
)
async def sp_set_display_settings(params: DisplaySettingsInput) -> str:
    """Set the viewport environment (HDRI) and tone mapping for accurate material preview.

    Use sp_list_resources with resource_type='environment' to find available HDRI names.

    Common tone mapping values: 'None', 'Reinhard', 'ACES Filmic', 'Exposure'

    Returns:
        str: JSON with applied settings
    """
    code = f"""
import substance_painter.display as sp_display
import substance_painter.resource as sp_resource
import json

applied = {{}}

environment = {repr(params.environment)}
tone_mapping = {repr(params.tone_mapping)}
exposure = {repr(params.exposure)}

if environment:
    results = sp_resource.search(environment)
    env_resource = None
    for r in results:
        if str(r.type()) in ("ResourceType.Environment", "environment") and environment.lower() in r.identifier().name.lower():
            env_resource = r
            break
    if env_resource:
        sp_display.set_environment_resource(env_resource)
        applied["environment"] = env_resource.identifier().name
    else:
        applied["environment_error"] = f"Environment '{{environment}}' not found"

if tone_mapping:
    for func in sp_display.ToneMappingFunction:
        if tone_mapping.lower().replace(" ", "") in str(func).lower().replace(" ", ""):
            sp_display.set_tone_mapping(func)
            applied["tone_mapping"] = str(func)
            break
    else:
        applied["tone_mapping_error"] = f"Tone mapping '{{tone_mapping}}' not found. Options: " + str([str(f) for f in sp_display.ToneMappingFunction])

print(json.dumps({{"status": "ok", "applied": applied}}))
"""
    return _sp_eval(code)


# ---------------------------------------------------------------------------
# Tools — Arbitrary Code Execution
# ---------------------------------------------------------------------------
@mcp.tool(
    name="sp_execute_python",
    annotations={"title": "Execute Python in Substance Painter", "readOnlyHint": False, "openWorldHint": True},
)
async def sp_execute_python(params: ExecInput) -> str:
    """Execute arbitrary Python code inside Substance Painter.

    Provides full access to the substance_painter Python API:
    - substance_painter.project
    - substance_painter.textureset
    - substance_painter.layerstack
    - substance_painter.export
    - substance_painter.baking
    - substance_painter.resource
    - substance_painter.logging

    Use this as an escape hatch for operations not covered by the specific tools,
    or for API calls that differ between SP versions.

    Returns:
        str: Output/result from the executed code
    """
    return _send_to_sp(params.code)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Substance Painter MCP Server starting...")
    print(f"Connecting to Substance Painter plugin on {SP_HOST}:{SP_PORT}")
    print("Make sure sp_socket_plugin.py is installed and loaded in SP:")
    print("  1. Copy sp_socket_plugin.py to SP's plugins folder")
    print("  2. In SP: Python > Reload Plugins  (or restart SP)")
    mcp.run()
