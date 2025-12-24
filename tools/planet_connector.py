"""
Planet API Connector - Handles all Planet API interactions
"""
import os
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PlanetConnector:
    """Connect to Planet API and search for imagery"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("PLANET_API_KEY")
        if not self.api_key:
            raise ValueError("Planet API key not found. Set PLANET_API_KEY environment variable.")
        
        self.base_url = "https://api.planet.com/data/v1"
        self.session = requests.Session()
        self.session.auth = (self.api_key, "")
        
    def search_imagery(
        self, 
        geometry: Dict,
        start_date: str,
        end_date: str,
        cloud_cover_max: float = 0.2,
        item_type: str = "PSScene",
        limit: int = 10
    ) -> List[Dict]:
        """
        Search for Planet imagery matching criteria
        
        Args:
            geometry: GeoJSON geometry (e.g., {"type": "Point", "coordinates": [lon, lat]})
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            cloud_cover_max: Maximum cloud cover (0.0 to 1.0)
            item_type: Type of imagery (default: PSScene for PlanetScope)
            limit: Maximum number of results
            
        Returns:
            List of imagery items with metadata
        """
        try:
            # Build search filter
            search_filter = {
                "type": "AndFilter",
                "config": [
                    {
                        "type": "GeometryFilter",
                        "field_name": "geometry",
                        "config": geometry
                    },
                    {
                        "type": "DateRangeFilter",
                        "field_name": "acquired",
                        "config": {
                            "gte": f"{start_date}T00:00:00.000Z",
                            "lte": f"{end_date}T23:59:59.999Z"
                        }
                    },
                    {
                        "type": "RangeFilter",
                        "field_name": "cloud_cover",
                        "config": {
                            "lte": cloud_cover_max
                        }
                    }
                ]
            }
            
            # Build request
            request_data = {
                "item_types": [item_type],
                "filter": search_filter
            }
            
            # Make API request
            url = f"{self.base_url}/quick-search"
            response = self.session.post(url, json=request_data)
            response.raise_for_status()
            
            results = response.json()
            items = results.get("features", [])[:limit]
            
            logger.info(f"Found {len(items)} imagery items")
            return items
            
        except Exception as e:
            logger.error(f"Error searching imagery: {e}")
            return []
    
    def get_asset_info(self, item_id: str, item_type: str = "PSScene") -> Dict:
        """
        Get available assets for an item
        
        Args:
            item_id: Planet item ID
            item_type: Type of item
            
        Returns:
            Dictionary of available assets
        """
        try:
            url = f"{self.base_url}/item-types/{item_type}/items/{item_id}/assets"
            response = self.session.get(url)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error getting asset info: {e}")
            return {}
    
    def activate_asset(self, item_id: str, asset_type: str, item_type: str = "PSScene") -> bool:
        """
        Activate an asset for download
        
        Args:
            item_id: Planet item ID
            asset_type: Type of asset (e.g., 'ortho_analytic_4b')
            item_type: Type of item
            
        Returns:
            True if activation successful
        """
        try:
            url = f"{self.base_url}/item-types/{item_type}/items/{item_id}/assets/{asset_type}/activate"
            response = self.session.post(url)
            response.raise_for_status()
            
            logger.info(f"Asset {asset_type} activated for item {item_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error activating asset: {e}")
            return False
    
    def get_download_url(self, item_id: str, asset_type: str, item_type: str = "PSScene") -> Optional[str]:
        """
        Get download URL for an activated asset
        
        Args:
            item_id: Planet item ID
            asset_type: Type of asset
            item_type: Type of item
            
        Returns:
            Download URL if available
        """
        try:
            assets = self.get_asset_info(item_id, item_type)
            asset = assets.get(asset_type, {})
            
            if asset.get("status") == "active":
                return asset.get("location")
            else:
                logger.info(f"Asset not yet active. Status: {asset.get('status')}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting download URL: {e}")
            return None
    
    def get_tile_url(self, item_id: str, z: int = 12, x: int = 0, y: int = 0) -> str:
        """
        Get XYZ tile URL for streaming visualization
        
        Args:
            item_id: Planet item ID
            z, x, y: Tile coordinates
            
        Returns:
            Tile URL
        """
        return f"https://tiles.planet.com/data/v1/PSScene/{item_id}/{{z}}/{{x}}/{{y}}.png?api_key={self.api_key}"
    
    def create_demo_search_params(self, location: str = "sekinchan_padi") -> Tuple[Dict, str, str]:
        """
        Create demo search parameters for different locations

        Args:
            location: One of: sekinchan_padi

        Returns:
            (geometry, start_date, end_date)
        """
        locations = {
            "sekinchan_padi": {
                "geometry": {
                    "type": "Point",
                    "coordinates": [101.10218, 3.55576]  # Sekinchan, Malaysia
                },
                "description": "Sekinchan padi fields - major rice producer in Malaysia"
            }
        }

        location_data = locations.get(location, locations["sekinchan_padi"])
        
        # Default to last 3 months
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        return (
            location_data["geometry"],
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        )


if __name__ == "__main__":
    # Test the connector
    connector = PlanetConnector()

    # Search for imagery
    geometry, start_date, end_date = connector.create_demo_search_params("sekinchan_padi")
    results = connector.search_imagery(geometry, start_date, end_date, limit=5)
    
    if results:
        print(f"Found {len(results)} items")
        print(f"First item ID: {results[0]['id']}")
        print(f"Acquisition date: {results[0]['properties']['acquired']}")
        print(f"Cloud cover: {results[0]['properties']['cloud_cover']}")
