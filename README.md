# LLM-Powered Satellite Imagery Analysis

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![OpenAI](https://img.shields.io/badge/OpenAI_Agents_SDK-Latest-purple)](https://openai.com/)
[![Planet](https://img.shields.io/badge/Planet_API-Integrated-green)](https://www.planet.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

> A conversational AI system that integrates Large Language Models with Planet's satellite imagery APIs, enabling natural language interactions for searching, downloading, and analyzing Earth observation data.

---

## Overview

This project demonstrates the integration of **OpenAI's Agents SDK** with **Planet's Data and Orders APIs** to create an intelligent satellite imagery analysis platform. Users interact through natural language to:

- **Search** for PlanetScope satellite imagery by location and date
- **Download** clipped imagery using Areas of Interest (AOI)
- **Visualize** multi-band imagery with automatic RGB band mapping
- **Analyze** vegetation indices (NDVI, NDRE) from 4-band and 8-band imagery

The system automatically handles the complexity of satellite data formats, band configurations, and API interactions - users simply describe what they need in plain English.

---

## Key Features

### Natural Language Interface
- Conversational queries like *"Find imagery for this area from May 2025"*
- Context-aware follow-up questions with session memory
- Automatic parameter extraction from natural language

### Planet API Integration
- **Data API**: Search PlanetScope imagery with filters (cloud cover, date range, AOI)
- **Orders API**: Create clipped orders with webhook notification support
- **Asset Management**: Download full scenes or AOI-clipped imagery

### Multi-Band Imagery Support
Automatic band detection and RGB mapping based on PlanetScope product specifications:

| Product | Bands | True Color RGB |
|---------|-------|----------------|
| 8-band SuperDove (PSB.SD) | Coastal Blue, Blue, Green-I, Green, Yellow, Red, Red Edge, NIR | Bands 6, 4, 2 |
| 4-band Dove-R (PS2.SD) | Blue, Green, Red, NIR | Bands 3, 2, 1 |
| 3-band Visual | Red, Green, Blue | Bands 1, 2, 3 |

### Vegetation Index Analysis
- **NDVI** (Normalized Difference Vegetation Index)
  - 8-band: (Band 8 - Band 6) / (Band 8 + Band 6)
  - 4-band: (Band 4 - Band 3) / (Band 4 + Band 3)
- **NDRE** (Normalized Difference Red Edge Index)
  - 8-band only: (Band 8 - Band 7) / (Band 8 + Band 7)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Streamlit Chat Interface                    │
│              (Real-time image display inline)                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  OpenAI Agents SDK                           │
│           (Unified Agent + Function Tools)                   │
│              SQLiteSession for memory                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Search     │  │   Orders     │  │  Analysis    │
│   Tools      │  │   Tools      │  │   Tools      │
├──────────────┤  ├──────────────┤  ├──────────────┤
│ planet_search│  │ create_order │  │ visualize_   │
│ extract_aoi  │  │ check_status │  │   raster     │
│              │  │ download     │  │ compute_ndvi │
│              │  │              │  │ compute_ndre │
└──────┬───────┘  └──────┬───────┘  └──────────────┘
       │                 │
       ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│                    Planet SDK for Python                     │
│         Data API (Search) │ Orders API (Clip & Download)     │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites
- Python 3.12
- [uv](https://docs.astral.sh/uv/) package manager
- Planet account ([Sign up here](https://www.planet.com/explorer/))
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/llm-satellite-imagery.git
cd llm-satellite-imagery

# Install dependencies
uv sync

# Authenticate with Planet (saves credentials to ~/.planet.json)
planet auth login

# Set OpenAI API key
export OPENAI_API_KEY="sk-..."

# Run the application
uv run streamlit run app.py
```

---

## Usage Examples

### Search for Imagery
```
User: "Find satellite images for the uploaded AOI from May 24, 2025"

Agent: Searches Planet Data API, returns available scenes with metadata
       (cloud cover, acquisition time, satellite ID)
```

### Download Clipped Imagery
```
User: "Download the first 3 results clipped to my AOI"

Agent: Creates an order via Orders API, clips imagery to AOI,
       provides order ID for tracking
```

### Visualize Imagery
```
User: "Display this image as RGB"

Agent: Auto-detects band count (8-band/4-band/3-band),
       applies correct RGB mapping, displays inline
```

### Vegetation Analysis
```
User: "Run NDVI analysis on this image"

Agent: Computes NDVI using appropriate bands,
       generates colorized visualization with statistics
```

---

## Project Structure

```
├── app.py                    # Streamlit chat interface
├── geovision_agents.py       # Agent definition and function tools
│   ├── unified_agent         # Main conversational agent
│   ├── extract_polygon_geometry  # Extract geometry from GeoJSON
│   ├── planet_search         # Search Planet Data API
│   ├── download_single_asset # Download full scene assets
│   ├── create_clip_order     # Create Orders API request
│   ├── check_order_status    # Check order processing status
│   ├── download_order        # Download completed orders
│   ├── get_pending_orders    # List pending orders
│   ├── visualize_raster      # RGB visualization with auto band detection
│   ├── compute_ndvi          # NDVI calculation (4-band & 8-band)
│   └── compute_ndre          # NDRE calculation (8-band only)
├── order_manager.py          # Order tracking and webhook support
├── WEBHOOK_USAGE.md          # Webhook setup documentation
├── outputs/                  # Generated visualizations (PNG)
├── uploads/                  # Uploaded GeoJSON and TIFF files
├── downloads/                # Downloaded satellite imagery
└── README.md
```

---

## Technical Implementation

### Agent Configuration (OpenAI Agents SDK)

```python
from agents import Agent, Runner, function_tool, SQLiteSession

unified_agent = Agent(
    name="unified_agent",
    instructions="""...""",
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

# Run with session memory
session = SQLiteSession(session_id)
result = await Runner.run(unified_agent, input=user_message, session=session)
```

### Planet SDK Integration

```python
from planet import Planet, data_filter

pl = Planet()  # Uses credentials from `planet auth login`

# Build search filter
search_filter = data_filter.and_filter([
    data_filter.permission_filter(),
    data_filter.geometry_filter(aoi),
    data_filter.date_range_filter("acquired", gte=start_dt, lte=end_dt),
    data_filter.range_filter("cloud_cover", lte=max_cloud_cover)
])

# Search for imagery
for item in pl.data.search(["PSScene"], search_filter=search_filter, limit=50):
    # Process results...

# Create clipped order
order = pl.orders.create_order(order_request)
```

### Band-Aware Visualization

```python
with rasterio.open(file_path) as src:
    num_bands = src.count

    if num_bands == 8:
        # SuperDove: Red=6, Green=4, Blue=2
        rgb_bands = [6, 4, 2]
    elif num_bands == 4:
        # Dove-R: Red=3, Green=2, Blue=1
        rgb_bands = [3, 2, 1]

    data = src.read(rgb_bands)
    # Normalize and display...
```

---

## API Reference

### Function Tools

| Tool | Description | Input |
|------|-------------|-------|
| `extract_polygon_geometry` | Extract geometry from GeoJSON | File path |
| `planet_search` | Search PlanetScope imagery | AOI, date range, cloud cover |
| `download_single_asset` | Download full scene asset | Item ID, item type, asset type |
| `create_clip_order` | Create clipped imagery order | Item IDs, AOI, asset type |
| `check_order_status` | Check order processing status | Order ID |
| `download_order` | Download completed order | Order ID |
| `get_pending_orders` | List pending orders | None |
| `visualize_raster` | Display imagery as RGB | File path |
| `compute_ndvi` | Calculate NDVI | File path |
| `compute_ndre` | Calculate NDRE (8-band only) | File path |

---

## Webhook Support

The system supports webhook notifications for order completion:

```python
create_clip_order(
    item_ids=["..."],
    item_type="PSScene",
    asset_type="ortho_analytic_8b_sr",
    aoi_json=geometry,
    webhook_url="https://your-server.com/webhook"  # Optional
)
```

See `WEBHOOK_USAGE.md` for detailed setup instructions.

---

## Dependencies

- **streamlit** - Chat interface
- **openai-agents** - OpenAI Agents SDK
- **planet** - Planet SDK for Python
- **rasterio** - Geospatial raster I/O
- **numpy** - Numerical operations
- **matplotlib** - Visualization
- **geojson** - GeoJSON parsing

---

## Limitations

- Requires active Planet API subscription with download quota
- NDRE analysis only available for 8-band SuperDove imagery
- Order processing time varies (typically 5-15 minutes)
- Large imagery files may take time to download

---

## Acknowledgments

- [Planet Labs](https://www.planet.com/) for satellite imagery API access
- [OpenAI](https://openai.com/) for the Agents SDK
- [Rasterio](https://rasterio.readthedocs.io/) for geospatial raster processing

---

## License

MIT License - See [LICENSE](LICENSE) for details.

---

*This project demonstrates the integration of Large Language Models with Earth Observation APIs for natural language-driven satellite imagery analysis.*
