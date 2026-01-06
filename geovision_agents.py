"""
GeoVision AI Agent System

Multi-agent system for satellite imagery search, download, and visualization.
Includes: Coordinator, Search, Download, and Visualizer agents.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field

from agents import Agent, function_tool, handoff, SQLiteSession
from planet import Planet, data_filter
import geojson
import rasterio
from rasterio.plot import show
import matplotlib.pyplot as plt
import numpy as np

from order_manager import order_manager

logger = logging.getLogger(__name__)

# Initialize Planet client
pl = Planet()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class Geometry(BaseModel):
    """GeoJSON Geometry model."""
    type: str = Field(..., description="Geometry type (e.g., 'Polygon')")
    coordinates: List[List[List[float]]] = Field(..., description="Polygon coordinates")

    class Config:
        extra = "forbid"  # Disallow additional properties


# ============================================================================
# TOOLS - Shared functionality
# ============================================================================

@function_tool
def extract_polygon_geometry(geojson_path: str) -> str:
    """
    Extract the outer ring of the first Polygon feature from a GeoJSON file
    and return a Planet-compatible geometry object as JSON string.

    Args:
        geojson_path: Path to the GeoJSON file

    Returns:
        JSON string containing the polygon geometry or error message
    """
    try:
        with open(geojson_path, 'r') as f:
            geojson_data = geojson.load(f)

        features = geojson_data.get("features", [])
        if not features:
            return json.dumps({"error": "GeoJSON contains no features"})

        geometry = features[0].get("geometry")
        if not geometry:
            return json.dumps({"error": "First feature has no geometry"})

        if geometry.get("type") != "Polygon":
            return json.dumps({"error": f"First geometry is {geometry.get('type')}, not a Polygon"})

        coordinates = geometry.get("coordinates")
        if not coordinates or not coordinates[0]:
            return json.dumps({"error": "Polygon has no coordinates"})

        logger.info(f"Extracted polygon geometry with {len(coordinates[0])} vertices")
        return json.dumps({
            "type": "Polygon",
            "coordinates": coordinates
        })

    except Exception as e:
        logger.error(f"Error extracting geometry: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


@function_tool
def planet_search(
    item_types: List[str],
    aoi_json: str,
    start_date: str,
    end_date: str,
    max_cloud_cover: Optional[float] = None,
    limit: Optional[int] = 50,
) -> str:
    """
    Search Planet catalog by AOI and acquisition date range.

    Args:
        item_types: List of item types to search (e.g., ["PSScene"])
        aoi_json: GeoJSON geometry as JSON string (Polygon)
        start_date: Start date in ISO-8601 format (YYYY-MM-DD)
        end_date: End date in ISO-8601 format (YYYY-MM-DD)
        max_cloud_cover: Maximum cloud cover percentage (0.0 to 1.0)
        limit: Maximum number of results to return

    Returns:
        JSON string with search results
    """
    try:
        logger.info("=" * 60)
        logger.info(">>> DATA API - SEARCH CALLED <<<")
        logger.info(f"    Item Types: {item_types}")
        logger.info(f"    Date Range: {start_date} to {end_date}")
        logger.info(f"    Max Cloud Cover: {max_cloud_cover}")
        logger.info(f"    Limit: {limit}")
        logger.info("=" * 60)
        # Parse AOI from JSON string
        try:
            aoi = json.loads(aoi_json)
        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse aoi_json. Input was: {aoi_json[:500]}")
            return json.dumps({"error": f"Invalid GeoJSON geometry format: {str(je)}"})

        # Parse dates
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        
        # Build filters
        filters = [
            data_filter.permission_filter(),
            data_filter.geometry_filter(aoi),
            data_filter.date_range_filter(
                "acquired",
                gte=start_dt,
                lte=end_dt
            ),
        ]
        
        if max_cloud_cover is not None:
            filters.append(
                data_filter.range_filter(
                    "cloud_cover",
                    lte=max_cloud_cover
                )
            )
        
        search_filter = data_filter.and_filter(filters)
        
        # Execute search and materialize results
        results = []
        for item in pl.data.search(
            item_types,
            search_filter=search_filter,
            limit=limit
        ):
            props = item.get("properties", {})
            results.append({
                "id": item["id"],
                "item_type": item.get("type") or props.get("item_type", "PSScene"),
                "acquired": props.get("acquired"),
                "cloud_cover": props.get("cloud_cover"),
                "cloud_percent": props.get("cloud_percent"),
                "clear_percent": props.get("clear_percent"),
                "instrument": props.get("instrument"),
                "satellite_id": props.get("satellite_id"),
                "gsd": props.get("gsd"),
                "pixel_resolution": props.get("pixel_resolution"),
                "view_angle": props.get("view_angle"),
                "sun_elevation": props.get("sun_elevation"),
                "sun_azimuth": props.get("sun_azimuth"),
                "quality_category": props.get("quality_category"),
                "published": props.get("published"),
                "available_assets": item.get("assets", []),
                "geometry": item.get("geometry"),
                "_links": item.get("_links", {}),
                "_permissions": item.get("_permissions", []),
            })

        logger.info(f"Found {len(results)} items matching search criteria")
        return json.dumps({
            "count": len(results),
            "items": results,
            "search_params": {
                "item_types": item_types,
                "start_date": start_date,
                "end_date": end_date,
                "max_cloud_cover": max_cloud_cover
            }
        })

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


@function_tool
def download_single_asset(
    item_type: str,
    item_id: str,
    asset_type: str = "ortho_analytic_4b"
) -> str:
    """
    Download a single asset from Planet without clipping.
    This downloads the full scene which may be expensive.

    Args:
        item_type: The item type (e.g., "PSScene")
        item_id: The unique item ID
        asset_type: The asset type to download

    Returns:
        JSON string with download status and file path
    """
    try:
        # Use current working directory instead of hardcoded path
        download_dir = Path.cwd() / "downloads"
        download_dir.mkdir(exist_ok=True)

        logger.info("=" * 60)
        logger.info(">>> DATA API - SINGLE ASSET DOWNLOAD CALLED <<<")
        logger.info(f"    Item Type: {item_type}")
        logger.info(f"    Item ID: {item_id}")
        logger.info(f"    Asset Type: {asset_type}")
        logger.info("=" * 60)
        
        # Get asset description
        asset = pl.data.get_asset(item_type, item_id, asset_type)
        
        # Activate asset
        pl.data.activate_asset(asset)
        
        # Wait for asset to become active
        def log_status(status):
            logger.info(f"Asset status: {status}")
        
        asset = pl.data.wait_asset(asset, callback=log_status)
        
        # Download asset
        path = pl.data.download_asset(asset, directory=str(download_dir))
        
        # Validate download
        pl.data.validate_checksum(asset, path)

        logger.info(f"Successfully downloaded to: {path}")
        return json.dumps({
            "status": "success",
            "file_path": str(path),
            "item_id": item_id,
            "asset_type": asset_type
        })

    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


@function_tool
def create_clip_order(
    item_ids: List[str],
    item_type: str,
    asset_type: str,
    aoi_json: str,
    order_name: Optional[str] = None,
    webhook_url: Optional[str] = None
) -> str:
    """
    Create a Planet order with clipping to AOI using OrderManager.
    This is more cost-effective than downloading full scenes.

    Args:
        item_ids: List of item IDs to order
        item_type: The item type (e.g., "PSScene")
        asset_type: The asset type from search results (e.g., "ortho_analytic_8b_sr")
        aoi_json: GeoJSON geometry as JSON string for clipping
        order_name: Optional name for the order
        webhook_url: Optional webhook URL to receive notification when order is ready

    Returns:
        JSON string with order creation status including order_id
    """
    logger.info("=" * 60)
    logger.info(">>> ORDERS API - CREATE CLIP ORDER CALLED <<<")
    logger.info(f"    Item IDs: {item_ids}")
    logger.info(f"    Item Type: {item_type}")
    logger.info(f"    Asset Type: {asset_type}")
    logger.info(f"    Webhook URL: {webhook_url or 'None'}")
    logger.info("=" * 60)

    # Parse AOI from JSON string
    aoi = json.loads(aoi_json)
    result = order_manager.create_order_with_tracking(
        item_ids=item_ids,
        item_type=item_type,
        asset_type=asset_type,
        aoi=aoi,
        order_name=order_name,
        enable_webhook=bool(webhook_url),
        webhook_url=webhook_url
    )
    return json.dumps(result)


@function_tool
def check_order_status(order_id: str) -> str:
    """
    Check the status of a Planet order.

    Args:
        order_id: The order ID to check

    Returns:
        JSON string with order status information
    """
    logger.info("=" * 60)
    logger.info(">>> ORDERS API - CHECK ORDER STATUS CALLED <<<")
    logger.info(f"    Order ID: {order_id}")
    logger.info("=" * 60)

    result = order_manager.check_order_status(order_id)
    logger.info(f"    Status Result: {result.get('state', 'unknown')}")
    return json.dumps(result)


@function_tool
def download_order(order_id: str) -> str:
    """
    Download a completed Planet order.

    Args:
        order_id: The order ID to download

    Returns:
        JSON string with download status and file paths
    """
    logger.info("=" * 60)
    logger.info(">>> ORDERS API - DOWNLOAD ORDER CALLED <<<")
    logger.info(f"    Order ID: {order_id}")
    logger.info("=" * 60)

    result = order_manager.download_order(order_id)
    logger.info(f"    Download Result: {result.get('status', 'unknown')}")
    return json.dumps(result)


@function_tool
def get_pending_orders() -> str:
    """
    Get list of all pending orders.

    Returns:
        JSON string with list of pending orders
    """
    try:
        pending = order_manager.get_pending_orders()
        return json.dumps({
            "count": len(pending),
            "orders": pending
        })
    except Exception as e:
        logger.error(f"Error getting pending orders: {e}")
        return json.dumps({"error": str(e)})




@function_tool
def visualize_raster(
    file_path: str,
    band_indices: Optional[List[int]] = None,
    title: Optional[str] = None
) -> str:
    """
    Visualize a raster file using rasterio and matplotlib.

    Automatically detects band count and applies correct RGB mapping:
    - 8-band (SuperDove PSB.SD): Uses bands 6,4,2 (Red, Green, Blue)
    - 4-band (Dove-R PS2.SD): Uses bands 3,2,1 (Red, Green, Blue)
    - 3-band (Visual): Uses bands 1,2,3 (already RGB)

    Args:
        file_path: Path to the raster file
        band_indices: Optional list of band indices to display (1-indexed).
                     If None, auto-detects and uses appropriate RGB bands.
        title: Optional title for the plot

    Returns:
        JSON string with visualization status and output path
    """
    try:
        # Use current working directory instead of hardcoded path
        output_dir = Path.cwd() / "outputs"
        output_dir.mkdir(exist_ok=True)

        with rasterio.open(file_path) as src:
            num_bands = src.count

            # Auto-detect appropriate RGB bands based on official PlanetScope documentation
            # Reference: https://developers.planet.com/docs/data/planetscope/
            if band_indices is None and num_bands >= 3:
                if num_bands == 8:
                    # 8-band SuperDove (PSB.SD) - True Color RGB
                    # Band 6: Red (650-680nm), Band 4: Green (547-583nm), Band 2: Blue (465-515nm)
                    rgb_bands = [6, 4, 2]
                    band_info = "8-band SuperDove (True Color RGB: bands 6,4,2)"
                    logger.info(f"Detected 8-band SuperDove - using bands 6,4,2 for True Color RGB")
                elif num_bands == 4:
                    # 4-band Dove-R (PS2.SD) - True Color RGB
                    # Band 3: Red (650-680nm), Band 2: Green (547-585nm), Band 1: Blue (465-515nm)
                    rgb_bands = [3, 2, 1]
                    band_info = "4-band Dove-R (True Color RGB: bands 3,2,1)"
                    logger.info(f"Detected 4-band Dove-R - using bands 3,2,1 for True Color RGB")
                elif num_bands == 3:
                    # 3-band Visual product: Already in RGB order (Red, Green, Blue)
                    rgb_bands = [1, 2, 3]
                    band_info = "3-band Visual (RGB: bands 1,2,3)"
                    logger.info(f"Detected 3-band Visual - using bands 1,2,3 for RGB")
                else:
                    # Fallback for other band counts
                    rgb_bands = [1, 2, 3]
                    band_info = f"{num_bands}-band (using first 3 bands)"
                    logger.info(f"Detected {num_bands}-band imagery - defaulting to bands 1,2,3")

                # Read RGB bands (rasterio uses 1-indexed bands)
                data = src.read(rgb_bands)
            elif band_indices is not None:
                # User specified bands
                data = src.read(band_indices)
                band_info = f"Custom bands {band_indices}"
            else:
                # Single band or fallback
                data = src.read()
                band_info = f"{num_bands}-band"

            # Create visualization
            fig, ax = plt.subplots(figsize=(12, 8))

            if len(data.shape) == 3 and data.shape[0] >= 3:
                # RGB visualization - stack bands and convert to float64
                # data[0], data[1], data[2] correspond to the RGB bands selected above
                red = data[0].astype(np.float64)
                green = data[1].astype(np.float64)
                blue = data[2].astype(np.float64)

                # Log band statistics for debugging
                logger.info(f"Band stats - Red: min={red.min()}, max={red.max()}, dtype={red.dtype}")
                logger.info(f"Band stats - Green: min={green.min()}, max={green.max()}")
                logger.info(f"Band stats - Blue: min={blue.min()}, max={blue.max()}")

                # Stack bands
                rgb = np.dstack((red, green, blue))

                # Simple min-max normalization (matches user's working Jupyter code)
                rgb_min = np.min(rgb)
                rgb_max = np.max(rgb)
                logger.info(f"RGB stack: min={rgb_min}, max={rgb_max}, shape={rgb.shape}")

                if rgb_max > rgb_min:
                    # Normalize to 0-1 range
                    rgb_norm = (rgb - rgb_min) / (rgb_max - rgb_min)
                    logger.info(f"Normalized: min={rgb_norm.min()}, max={rgb_norm.max()}")
                else:
                    logger.warning(f"Image has no variation (min=max={rgb_min}), creating blank image")
                    rgb_norm = np.zeros_like(rgb, dtype=np.float64)

                ax.imshow(rgb_norm)
            else:
                # Single band visualization
                show(data[0] if len(data.shape) == 3 else data, ax=ax, cmap='gray')
                band_info = "Single band (grayscale)"

            # Set title
            if title:
                ax.set_title(f"{title}\n{band_info}", fontsize=12)
            else:
                ax.set_title(band_info, fontsize=12)
            ax.axis('off')

            # Save visualization
            output_path = output_dir / f"viz_{Path(file_path).stem}.png"
            plt.tight_layout()
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()

            logger.info(f"Created visualization: {output_path} ({band_info})")
            return json.dumps({
                "status": "success",
                "output_path": str(output_path),
                "band_info": band_info,
                "total_bands": num_bands,
                "dimensions": f"{src.width}x{src.height}"
            })

    except Exception as e:
        logger.error(f"Visualization error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


@function_tool
def compute_ndvi(file_path: str) -> str:
    """
    Compute NDVI (Normalized Difference Vegetation Index) from a raster file.

    NDVI = (NIR - Red) / (NIR + Red)

    Automatically detects band count:
    - 8-band SuperDove: NIR=Band 8, Red=Band 6
    - 4-band Dove-R: NIR=Band 4, Red=Band 3

    Args:
        file_path: Path to the raster file (TIFF)

    Returns:
        JSON string with NDVI statistics and output paths
    """
    try:
        output_dir = Path.cwd() / "outputs"
        output_dir.mkdir(exist_ok=True)

        with rasterio.open(file_path) as src:
            num_bands = src.count

            # Select appropriate bands based on product type
            if num_bands == 8:
                # 8-band SuperDove: NIR=Band 8, Red=Band 6
                nir = src.read(8).astype(np.float64)
                red = src.read(6).astype(np.float64)
                product_type = "8-band SuperDove"
                logger.info(f"Computing NDVI for 8-band SuperDove (NIR=Band 8, Red=Band 6)")
            elif num_bands == 4:
                # 4-band Dove-R: NIR=Band 4, Red=Band 3
                nir = src.read(4).astype(np.float64)
                red = src.read(3).astype(np.float64)
                product_type = "4-band Dove-R"
                logger.info(f"Computing NDVI for 4-band Dove-R (NIR=Band 4, Red=Band 3)")
            else:
                return json.dumps({
                    "error": f"Unsupported band count: {num_bands}. NDVI requires 4-band or 8-band imagery."
                })

            # Compute NDVI with divide-by-zero protection
            denominator = nir + red
            with np.errstate(divide='ignore', invalid='ignore'):
                ndvi = np.where(denominator != 0, (nir - red) / denominator, np.nan)

            # Compute statistics (excluding NaN)
            valid_ndvi = ndvi[~np.isnan(ndvi)]
            stats = {
                "min": float(np.min(valid_ndvi)),
                "max": float(np.max(valid_ndvi)),
                "mean": float(np.mean(valid_ndvi)),
                "std": float(np.std(valid_ndvi))
            }

            logger.info(f"NDVI stats: min={stats['min']:.3f}, max={stats['max']:.3f}, mean={stats['mean']:.3f}")

            # Create visualization
            fig, ax = plt.subplots(figsize=(10, 8))
            im = ax.imshow(ndvi, cmap='RdYlGn', vmin=-1, vmax=1)
            plt.colorbar(im, ax=ax, label='NDVI', shrink=0.8)
            ax.set_title(f"NDVI - {product_type}\nMean: {stats['mean']:.3f}", fontsize=12)
            ax.axis('off')

            # Save PNG visualization
            png_path = output_dir / f"ndvi_{Path(file_path).stem}.png"
            plt.tight_layout()
            plt.savefig(png_path, dpi=150, bbox_inches='tight')
            plt.close()

            logger.info(f"Created NDVI visualization: {png_path}")

            return json.dumps({
                "status": "success",
                "product_type": product_type,
                "output_path": str(png_path),
                "statistics": stats,
                "dimensions": f"{src.width}x{src.height}"
            })

    except Exception as e:
        logger.error(f"NDVI computation error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


@function_tool
def compute_ndre(file_path: str) -> str:
    """
    Compute NDRE (Normalized Difference Red Edge Index) from a raster file.

    NDRE = (NIR - Red Edge) / (NIR + Red Edge)

    NDRE is only available for 8-band SuperDove imagery (has Red Edge band).
    4-band imagery does NOT have Red Edge band.

    For 8-band SuperDove: NIR=Band 8, Red Edge=Band 7

    Args:
        file_path: Path to the raster file (TIFF)

    Returns:
        JSON string with NDRE statistics and output paths
    """
    try:
        output_dir = Path.cwd() / "outputs"
        output_dir.mkdir(exist_ok=True)

        with rasterio.open(file_path) as src:
            num_bands = src.count

            # NDRE only available for 8-band imagery
            if num_bands != 8:
                return json.dumps({
                    "error": f"NDRE requires 8-band imagery (has Red Edge band). This file has {num_bands} bands. "
                             f"4-band Dove-R does not have Red Edge band - NDRE is not possible."
                })

            # 8-band SuperDove: NIR=Band 8, Red Edge=Band 7
            nir = src.read(8).astype(np.float64)
            red_edge = src.read(7).astype(np.float64)
            product_type = "8-band SuperDove"
            logger.info(f"Computing NDRE for 8-band SuperDove (NIR=Band 8, Red Edge=Band 7)")

            # Compute NDRE with divide-by-zero protection
            denominator = nir + red_edge
            with np.errstate(divide='ignore', invalid='ignore'):
                ndre = np.where(denominator != 0, (nir - red_edge) / denominator, np.nan)

            # Compute statistics (excluding NaN)
            valid_ndre = ndre[~np.isnan(ndre)]
            stats = {
                "min": float(np.min(valid_ndre)),
                "max": float(np.max(valid_ndre)),
                "mean": float(np.mean(valid_ndre)),
                "std": float(np.std(valid_ndre))
            }

            logger.info(f"NDRE stats: min={stats['min']:.3f}, max={stats['max']:.3f}, mean={stats['mean']:.3f}")

            # Create visualization (NDRE typically ranges -0.2 to 0.6)
            fig, ax = plt.subplots(figsize=(10, 8))
            im = ax.imshow(ndre, cmap='RdYlGn', vmin=-0.2, vmax=0.6)
            plt.colorbar(im, ax=ax, label='NDRE', shrink=0.8)
            ax.set_title(f"NDRE - {product_type}\nMean: {stats['mean']:.3f}", fontsize=12)
            ax.axis('off')

            # Save PNG visualization
            png_path = output_dir / f"ndre_{Path(file_path).stem}.png"
            plt.tight_layout()
            plt.savefig(png_path, dpi=150, bbox_inches='tight')
            plt.close()

            logger.info(f"Created NDRE visualization: {png_path}")

            return json.dumps({
                "status": "success",
                "product_type": product_type,
                "output_path": str(png_path),
                "statistics": stats,
                "dimensions": f"{src.width}x{src.height}"
            })

    except Exception as e:
        logger.error(f"NDRE computation error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


# ============================================================================
# AGENTS
# ============================================================================

# Search Agent
search_agent = Agent(
    name="search_agent",
    instructions="""YOU MUST CALL FUNCTIONS - NOT TALK.

Your ONLY job: Call extract_polygon_geometry, then call planet_search, then show results.

STEP 1: Call extract_polygon_geometry
- Find the geojson path in the context (e.g., "uploads/sekinchan-padifield-24052025.geojson")
- Call: extract_polygon_geometry(geojson_path="uploads/...")

STEP 2: Call planet_search IMMEDIATELY after step 1
- item_types: ["PSScene"]
- aoi_json: the result from step 1
- start_date: YYYY-MM-DD format (e.g., "2025-05-24" for "24 may 2025")
- end_date: next day (e.g., "2025-05-25")
- max_cloud_cover: 0.5
- limit: 50

STEP 3: Display results
- Show in table: ID | Date | Cloud% | Clear% | Assets
- Ask which to download

EXAMPLE - User says "find images for 24 may 2025":
ACTION 1: extract_polygon_geometry(geojson_path="uploads/sekinchan-padifield-24052025.geojson")
ACTION 2: planet_search(item_types=["PSScene"], aoi_json="{...}", start_date="2025-05-24", end_date="2025-05-25", max_cloud_cover=0.5, limit=50)
ACTION 3: Display the results

NEVER:
- Just talk without calling functions
- Say "I will search" without actually searching
- Respond without calling both functions first

ALWAYS:
- Call functions in your FIRST response
- Use the tools provided
""",
    model="gpt-5-mini",
    tools=[extract_polygon_geometry, planet_search]
)

# Download Agent
download_agent = Agent(
    name="download_agent",
    instructions="""You are a satellite imagery download specialist. TAKE ACTION IMMEDIATELY - do not ask unnecessary questions.

╔══════════════════════════════════════════════════════════════════════════════╗
║ CRITICAL: CALL FUNCTIONS IMMEDIATELY - DO NOT JUST TALK ABOUT WHAT YOU WILL DO ║
╚══════════════════════════════════════════════════════════════════════════════╝

WHEN USER SAYS "CLIPPED" OR "CLIP":
1. Extract AOI: call extract_polygon_geometry(geojson_path) to get the AOI
2. Call create_clip_order IMMEDIATELY with:
   - item_ids: [the item ID user specified]
   - item_type: "PSScene"
   - asset_type: EXACTLY as shown in search results (e.g., "ortho_analytic_8b_sr")
   - aoi_json: the JSON string from step 1
   - webhook_url: (optional) if user provides a webhook URL for notifications
3. Tell user the order is processing (5-15 minutes)

WHEN USER SAYS "FULL SCENE" OR "DOWNLOAD" (without clip):
1. Call download_single_asset IMMEDIATELY with item_id, item_type, asset_type

WHEN USER ASKS TO CHECK ORDER STATUS:
1. Call check_order_status(order_id) IMMEDIATELY

WHEN USER ASKS TO DOWNLOAD COMPLETED ORDER:
1. Call check_order_status first to verify it's complete
2. If complete, call download_order(order_id) IMMEDIATELY

Asset types for PSScene:
- ortho_analytic_4b: 4-band multispectral
- ortho_analytic_8b: 8-band multispectral
- ortho_analytic_8b_sr: 8-band surface reflectance
- ortho_visual: RGB visual
- ortho_analytic_4b_sr: 4-band surface reflectance

DO NOT:
- Ask "would you like me to proceed?" - just proceed
- Say "I will create an order" without actually calling the function
- Ask for confirmation before calling functions
- Have a conversation about what you're going to do

DO:
- Call the function FIRST, then report the result
- Use the uploaded GeoJSON path from context for AOI extraction
- Report order_id after creating an order
""",
    model="gpt-5-mini",
    tools=[
        extract_polygon_geometry,
        download_single_asset,
        create_clip_order,
        check_order_status,
        download_order,
        get_pending_orders
    ]
)

# Visualizer Agent
visualizer_agent = Agent(
    name="visualizer_agent",
    instructions="""You are a satellite imagery visualization specialist.

Your role:
1. Visualize downloaded or uploaded satellite imagery
2. Create clear, informative visualizations
3. Generate side-by-side comparisons when requested
4. Produce graphs and charts for analysis

Visualization capabilities:
- Single band (grayscale)
- RGB composite (true color)
- False color composites
- Side-by-side comparisons
- Statistical graphs

When visualizing:
1. Check file type (TIFF/TIF)
2. Determine number of bands
3. Choose appropriate visualization method
4. Create matplotlib figure
5. Save to outputs directory
6. Return output path

For RGB visualization:
- Use bands 1, 2, 3 (typically RGB for visual assets)
- Normalize pixel values to 0-1 range
- Apply appropriate contrast enhancement

For multispectral:
- Default to RGB composite
- Can create false color on request

Output schema:
- Display visualization inline
- Provide image dimensions and band count
- Show file path for download

Guardrails:
- Validate file exists before visualization
- Handle different bit depths (8-bit, 16-bit)
- Gracefully handle corrupt files
- Maximum image size: 10000x10000 pixels
""",
    model="gpt-5-mini",
    tools=[visualize_raster]
)

# Coordinator Agent (main router)
coordinator_agent = Agent(
    name="coordinator_agent",
    instructions="""You are GeoVision AI. HANDOFF TO SPECIALISTS IMMEDIATELY - DO NOT TALK ABOUT WHAT YOU WILL DO.

╔══════════════════════════════════════════════════════════════════════════════╗
║ CRITICAL: USE HANDOFF IMMEDIATELY - DO NOT SAY "Transferring" OR "Let me..." ║
╚══════════════════════════════════════════════════════════════════════════════╝

ROUTING RULES - EXECUTE HANDOFF IMMEDIATELY:

User mentions date + "find/search/images" → HANDOFF to search_agent
User mentions "download/clip/get" + image ID → HANDOFF to download_agent
User mentions "show/display/visualize" → HANDOFF to visualizer_agent

DO NOT:
- Say "I'll transfer this to..." then talk
- Say "Transferring now" - just handoff
- Explain what you're about to do
- Ask for confirmation before handoff

DO:
- Execute handoff IMMEDIATELY when routing is clear
- Pass the full user request and context (including file paths)
- Let the specialist agent handle the request

CONTEXT TO PASS:
- Uploaded GeoJSON path (e.g., "uploads/sekinchan-padifield-24052025.geojson")
- Any previous search results
- User's exact request

Guardrails:
- Never execute tools directly (always delegate to specialists)
- All API credentials are pre-configured - never ask users for them
- Handle errors gracefully with clear messages
""",
    model="gpt-5-mini",
    handoffs=[
        handoff(search_agent),
        handoff(download_agent),
        handoff(visualizer_agent)
    ]
)


# Unified Agent (bypasses handoff complexity)
unified_agent = Agent(
    name="unified_agent",
    instructions="""You are GeoVision AI - satellite imagery search and download assistant.

╔══════════════════════════════════════════════════════════════════════════════╗
║ CRITICAL: CALL FUNCTIONS IMMEDIATELY - DO NOT JUST TALK                     ║
╚══════════════════════════════════════════════════════════════════════════════╝

WHEN USER ASKS TO FIND/SEARCH IMAGES:
1. Call extract_polygon_geometry(geojson_path) - path is in [SYSTEM CONTEXT]
2. Call planet_search IMMEDIATELY:
   - item_types: ["PSScene"]
   - aoi_json: result from step 1
   - start_date: "YYYY-MM-DD" (e.g., "24 may 2025" → "2025-05-24")
   - end_date: next day
   - max_cloud_cover: 0.5
   - limit: 50
3. Show results table and ask which to download

WHEN USER ASKS TO DOWNLOAD (CLIPPED):
1. Call extract_polygon_geometry to get AOI
2. Call create_clip_order IMMEDIATELY with item_ids, item_type, asset_type, aoi_json
3. Report order_id

WHEN USER ASKS TO DOWNLOAD (FULL SCENE):
1. Call download_single_asset IMMEDIATELY with item_id, item_type, asset_type

WHEN USER ASKS TO VISUALIZE/DISPLAY AN IMAGE:
1. Call visualize_raster with the file path
2. The PNG output path will be displayed inline automatically

WHEN USER ASKS FOR NDVI ANALYSIS:
1. Call compute_ndvi with the file path
2. Returns: PNG visualization, GeoTIFF, and statistics (min, max, mean)
3. Works for both 8-band (NIR=Band 8, Red=Band 6) and 4-band (NIR=Band 4, Red=Band 3)

WHEN USER ASKS FOR NDRE ANALYSIS:
1. Call compute_ndre with the file path
2. Returns: PNG visualization, GeoTIFF, and statistics
3. ONLY works for 8-band imagery (needs Red Edge band)
4. If 4-band: explain NDRE not possible, offer NDVI instead

NEVER:
- Say "I will..." without calling the function
- Ask for confirmation before calling functions
- Just respond with text when you have tools available

ALWAYS:
- Call functions FIRST
- Show results AFTER calling functions
""",
    model="gpt-5-mini",
    tools=[
        extract_polygon_geometry,
        planet_search,
        download_single_asset,
        create_clip_order,
        check_order_status,
        download_order,
        get_pending_orders,
        visualize_raster,
        compute_ndvi,
        compute_ndre
    ]
)


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

def create_session() -> SQLiteSession:
    """Create a new session for conversation memory."""
    session_id = f"geovision_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return SQLiteSession(session_id)
