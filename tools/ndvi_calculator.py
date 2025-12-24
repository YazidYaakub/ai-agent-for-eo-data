"""
NDVI Calculator - Calculates vegetation health indices from satellite imagery
"""
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict
import io
import base64
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NDVICalculator:
    """Calculate NDVI and vegetation health metrics"""
    
    def __init__(self):
        self.ndvi_thresholds = {
            "water": (-1.0, 0.0),
            "barren": (0.0, 0.2),
            "sparse_vegetation": (0.2, 0.4),
            "moderate_vegetation": (0.4, 0.6),
            "healthy_vegetation": (0.6, 1.0)
        }
    
    def calculate_ndvi_from_scene(self, item_data: Dict) -> Dict:
        """
        Calculate NDVI from Planet scene by downloading and analyzing real satellite imagery

        Args:
            item_data: Planet API item data

        Returns:
            Dictionary with NDVI statistics and visualization from real imagery
        """
        try:
            # Always use real NDVI calculation
            return self._calculate_real_ndvi(item_data)
                
        except Exception as e:
            logger.error(f"Error calculating NDVI: {e}")
            return {"error": str(e)}
    def _calculate_real_ndvi(self, item_data: Dict) -> Dict:
        """
        Calculate NDVI from actual downloaded imagery

        This requires:
        1. Download ortho_analytic_4b asset from Planet
        2. Read NIR (band 4) and Red (band 3) with rasterio
        3. Calculate: (NIR - Red) / (NIR + Red)
        """
        try:
            import rasterio
            import requests
            import tempfile
            import os

            # Get Planet API key
            planet_api_key = os.getenv("PLANET_API_KEY")
            if not planet_api_key:
                return {"error": "Planet API key not found"}

            # Extract item info
            item_id = item_data.get("id")
            properties = item_data.get("properties", {})
            acquired = properties.get("acquired", "unknown")
            cloud_cover = properties.get("cloud_cover", 0.0)

            logger.info(f"Downloading imagery for item {item_id}")

            # Initialize requests session with Planet auth
            session = requests.Session()
            session.auth = (planet_api_key, "")

            # Get asset info
            assets_url = f"https://api.planet.com/data/v1/item-types/PSScene/items/{item_id}/assets"
            assets_response = session.get(assets_url)
            assets_response.raise_for_status()
            assets = assets_response.json()

            # Check for ortho_analytic_4b asset
            if 'ortho_analytic_4b' not in assets:
                logger.warning(f"ortho_analytic_4b asset not available for {item_id}, using ortho_analytic_sr")
                asset_type = 'ortho_analytic_sr' if 'ortho_analytic_sr' in assets else None
                if not asset_type:
                    return {"error": "No suitable analytic asset available"}
            else:
                asset_type = 'ortho_analytic_4b'

            asset = assets[asset_type]

            # Activate asset if needed
            if asset.get('status') != 'active':
                logger.info(f"Activating asset {asset_type} for item {item_id}")
                activate_url = f"https://api.planet.com/data/v1/item-types/PSScene/items/{item_id}/assets/{asset_type}/activate"
                session.post(activate_url)

                # Wait for activation (simple polling)
                import time
                for i in range(60):  # Wait up to 60 seconds
                    assets_response = session.get(assets_url)
                    assets = assets_response.json()
                    current_status = assets[asset_type].get('status')

                    if current_status == 'active':
                        asset = assets[asset_type]
                        logger.info(f"Asset activated successfully after {i+1} seconds")
                        break

                    # Log progress every 10 seconds
                    if (i + 1) % 10 == 0:
                        logger.info(f"Still waiting for activation... ({i+1}s elapsed, status: {current_status})")

                    time.sleep(1)
                else:
                    return {"error": f"Asset activation timeout after 60 seconds. Last status: {current_status}. Try again in a few minutes or try a different scene."}

            # Download imagery to temp file
            download_url = asset['location']
            logger.info(f"Downloading from {download_url}")

            with tempfile.NamedTemporaryFile(suffix='.tif', delete=False) as tmp:
                tmp_path = tmp.name
                response = session.get(download_url, stream=True)
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8192):
                    tmp.write(chunk)

            logger.info(f"Downloaded to {tmp_path}")

            # Read imagery and calculate NDVI
            with rasterio.open(tmp_path) as src:
                # For large images, downsample for faster processing
                # Read at 1/4 resolution (out_shape parameter)
                height = src.height
                width = src.width

                # Downsample to max 2000x2000 for performance
                scale_factor = 1
                if max(height, width) > 2000:
                    scale_factor = max(height, width) / 2000
                    new_height = int(height / scale_factor)
                    new_width = int(width / scale_factor)
                    logger.info(f"Downsampling from {width}x{height} to {new_width}x{new_height} for faster processing")

                    # Read bands at lower resolution
                    red = src.read(3, out_shape=(new_height, new_width)).astype(float)
                    nir = src.read(4, out_shape=(new_height, new_width)).astype(float)
                else:
                    # Read bands at full resolution
                    red = src.read(3).astype(float)
                    nir = src.read(4).astype(float)

                # Calculate NDVI
                # Avoid division by zero
                with np.errstate(divide='ignore', invalid='ignore'):
                    ndvi_array = np.where(
                        (nir + red) == 0,
                        0,
                        (nir - red) / (nir + red)
                    )

                # Clip to valid NDVI range
                ndvi_array = np.clip(ndvi_array, -1, 1)

                # Replace any remaining NaN/Inf with 0
                ndvi_array = np.nan_to_num(ndvi_array, nan=0.0, posinf=0.0, neginf=0.0)

            # Clean up temp file
            os.unlink(tmp_path)

            # Calculate statistics
            stats = self._calculate_statistics(ndvi_array)

            # Create visualization
            viz_base64 = self._create_visualization(ndvi_array, item_id, acquired)

            # Classify by health categories
            classification = self._classify_vegetation(ndvi_array)

            return {
                "item_id": item_id,
                "acquisition_date": acquired,
                "cloud_cover": round(cloud_cover, 3),
                "ndvi_statistics": stats,
                "vegetation_classification": classification,
                "visualization": viz_base64,
                "analysis_timestamp": datetime.now().isoformat(),
                "method": f"Real NDVI from {asset_type}"
            }

        except Exception as e:
            logger.error(f"Error calculating real NDVI: {e}")
            return {"error": str(e)}
    
    def _calculate_statistics(self, ndvi_array: np.ndarray) -> Dict:
        """Calculate NDVI statistics"""
        return {
            "mean": float(np.mean(ndvi_array)),
            "median": float(np.median(ndvi_array)),
            "std": float(np.std(ndvi_array)),
            "min": float(np.min(ndvi_array)),
            "max": float(np.max(ndvi_array)),
            "percentile_25": float(np.percentile(ndvi_array, 25)),
            "percentile_75": float(np.percentile(ndvi_array, 75))
        }
    
    def _classify_vegetation(self, ndvi_array: np.ndarray) -> Dict:
        """Classify pixels by vegetation health categories"""
        total_pixels = ndvi_array.size
        classification = {}
        
        for category, (min_val, max_val) in self.ndvi_thresholds.items():
            mask = (ndvi_array >= min_val) & (ndvi_array < max_val)
            pixel_count = np.sum(mask)
            percentage = (pixel_count / total_pixels) * 100
            
            classification[category] = {
                "pixel_count": int(pixel_count),
                "percentage": round(percentage, 2),
                "ndvi_range": f"{min_val} to {max_val}"
            }
        
        return classification
    
    def _create_visualization(
        self, 
        ndvi_array: np.ndarray, 
        item_id: str,
        acquired: str
    ) -> str:
        """Create NDVI visualization and return as base64 string"""
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        
        # NDVI map
        im = axes[0].imshow(ndvi_array, cmap='RdYlGn', vmin=-1, vmax=1)
        axes[0].set_title(f"NDVI Map\n{item_id[:20]}...", fontsize=10)
        axes[0].axis('off')
        plt.colorbar(im, ax=axes[0], fraction=0.046, pad=0.04, label='NDVI')
        
        # Histogram
        axes[1].hist(ndvi_array.flatten(), bins=50, color='green', alpha=0.7, edgecolor='black')
        axes[1].axvline(np.mean(ndvi_array), color='red', linestyle='--', label=f'Mean: {np.mean(ndvi_array):.3f}')
        axes[1].set_xlabel('NDVI Value')
        axes[1].set_ylabel('Frequency')
        axes[1].set_title(f"NDVI Distribution\nAcquired: {acquired[:10]}")
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Convert to base64
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        plt.close()
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        
        return f"data:image/png;base64,{img_base64}"
    
    def compare_temporal_ndvi(
        self, 
        item_data_1: Dict,
        item_data_2: Dict,
        use_mock: bool = True
    ) -> Dict:
        """
        Compare NDVI between two time periods
        
        Args:
            item_data_1: Earlier time period item
            item_data_2: Later time period item
            use_mock: Use mock data for demo
            
        Returns:
            Comparison analysis with change detection
        """
        try:
            # Calculate NDVI for both periods
            ndvi_1 = self.calculate_ndvi_from_scene(item_data_1, use_mock)
            ndvi_2 = self.calculate_ndvi_from_scene(item_data_2, use_mock)
            
            # Calculate change
            change_stats = {
                "mean_change": ndvi_2["ndvi_statistics"]["mean"] - ndvi_1["ndvi_statistics"]["mean"],
                "time_1": {
                    "date": item_data_1.get("properties", {}).get("acquired", "unknown"),
                    "mean_ndvi": ndvi_1["ndvi_statistics"]["mean"]
                },
                "time_2": {
                    "date": item_data_2.get("properties", {}).get("acquired", "unknown"),
                    "mean_ndvi": ndvi_2["ndvi_statistics"]["mean"]
                }
            }
            
            # Interpret change
            if change_stats["mean_change"] > 0.1:
                interpretation = "Significant vegetation increase"
            elif change_stats["mean_change"] < -0.1:
                interpretation = "Significant vegetation decrease"
            else:
                interpretation = "Relatively stable vegetation"
            
            return {
                "period_1": ndvi_1,
                "period_2": ndvi_2,
                "change_analysis": change_stats,
                "interpretation": interpretation
            }
            
        except Exception as e:
            logger.error(f"Error comparing temporal NDVI: {e}")
            return {"error": str(e)}


if __name__ == "__main__":
    # Test the calculator
    calculator = NDVICalculator()
    
    # Mock item data
    test_item = {
        "id": "20231015_120000_ssc1_u0003",
        "properties": {
            "acquired": "2023-10-15T12:00:00Z",
            "cloud_cover": 0.05
        }
    }
    
    result = calculator.calculate_ndvi_from_scene(test_item, use_mock=True)
    print("NDVI Analysis Results:")
    print(f"Mean NDVI: {result['ndvi_statistics']['mean']:.3f}")
    print(f"Classification: {result['vegetation_classification']}")

