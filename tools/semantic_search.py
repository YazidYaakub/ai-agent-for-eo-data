"""
Semantic Search - Search imagery using natural language descriptions
"""
from typing import Dict, List, Optional
import logging
import os
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SemanticSearch:
    """
    Semantic search across satellite imagery using keyword matching on real Planet data

    Full semantic search would use:
    - CLIP embeddings for image-text similarity
    - Vector database (ChromaDB, Pinecone, etc.)
    - Pre-computed embeddings for imagery archive

    Current implementation: Uses keyword matching on real Planet API search results
    """

    def __init__(self, planet_api_key: Optional[str] = None):
        """Initialize with Planet API key"""
        from tools.planet_connector import PlanetConnector

        self.planet_connector = PlanetConnector(api_key=planet_api_key)

        # Keyword mappings to search parameters
        self.keyword_mappings = {
            # Location keywords
            "sekinchan": {"location": "sekinchan_padi"},
            "padi": {"location": "sekinchan_padi"},
            "rice": {"location": "sekinchan_padi"},
            "malaysia": {"location": "sekinchan_padi"},

            # Feature keywords (would need coordinates)
            "agriculture": {"description": "agricultural area"},
            "agricultural": {"description": "agricultural area"},
            "farm": {"description": "agricultural area"},
            "crop": {"description": "agricultural area"},
            "field": {"description": "agricultural area"},

            "forest": {"description": "forest area"},
            "tree": {"description": "forest area"},
            "vegetation": {"description": "vegetation area"},

            "urban": {"description": "urban area"},
            "city": {"description": "urban area"},
            "building": {"description": "urban area"},

            "water": {"description": "water body"},
            "river": {"description": "water body"},
            "lake": {"description": "water body"},
            "coastal": {"description": "coastal area"},

            # Quality keywords
            "clear": {"cloud_cover_max": 0.1},
            "cloudy": {"cloud_cover_max": 0.5},
            "recent": {"days_back": 30},
            "latest": {"days_back": 30},
        }
    
    def search_by_description(
        self,
        query: str,
        k: int = 5,
        min_similarity: float = 0.3
    ) -> List[Dict]:
        """
        Search for real satellite imagery matching natural language description

        Args:
            query: Natural language search query (e.g., "padi fields", "clear recent imagery")
            k: Number of results to return
            min_similarity: Minimum similarity threshold (not used in keyword matching)

        Returns:
            List of matching real Planet items with similarity scores
        """
        try:
            query_lower = query.lower()
            logger.info(f"Semantic search query: '{query}'")

            # Parse query to extract search parameters
            search_params = self._parse_query(query_lower)

            # Determine location
            location = search_params.get("location")
            cloud_cover = search_params.get("cloud_cover_max", 0.2)
            days_back = search_params.get("days_back", 90)

            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)

            # Search using Planet API
            if location:
                # Use preset location
                geometry, _, _ = self.planet_connector.create_demo_search_params(location)
            else:
                # Default to Sekinchan if no specific location detected
                logger.info("No specific location detected, defaulting to Sekinchan")
                geometry, _, _ = self.planet_connector.create_demo_search_params("sekinchan_padi")

            # Search Planet API
            items = self.planet_connector.search_imagery(
                geometry=geometry,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                cloud_cover_max=cloud_cover,
                limit=k * 2  # Get more results to rank
            )

            logger.info(f"Found {len(items)} items from Planet API")

            # Rank results by keyword matching
            results = []
            for item in items:
                similarity = self._calculate_similarity_score(query_lower, item, search_params)

                if similarity >= min_similarity:
                    results.append({
                        "item_id": item["id"],
                        "description": self._generate_description(item),
                        "location": search_params.get("description", "Sekinchan padi fields"),
                        "date": item["properties"]["acquired"][:10],
                        "similarity_score": round(similarity, 3),
                        "match_reason": self._explain_match(query_lower, item, search_params)
                    })

            # Sort by similarity
            results.sort(key=lambda x: x["similarity_score"], reverse=True)

            # Return top k
            return results[:k]

        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []
    
    def _parse_query(self, query: str) -> Dict:
        """
        Parse natural language query to extract search parameters

        Args:
            query: Lowercase query string

        Returns:
            Dictionary of search parameters
        """
        params = {}

        # Check for keyword matches
        for keyword, mapping in self.keyword_mappings.items():
            if keyword in query:
                params.update(mapping)

        return params

    def _calculate_similarity_score(self, query: str, item: Dict, search_params: Dict) -> float:
        """
        Calculate similarity score between query and real Planet item

        Args:
            query: Lowercase query string
            item: Planet API item data
            search_params: Parsed search parameters

        Returns:
            Similarity score (0.0 to 1.0)
        """
        score = 0.5  # Base score for any matching item

        properties = item.get("properties", {})

        # Boost score for low cloud cover
        cloud_cover = properties.get("cloud_cover", 1.0)
        if cloud_cover < 0.1:
            score += 0.3
        elif cloud_cover < 0.2:
            score += 0.2

        # Boost score for recent imagery
        acquired = properties.get("acquired", "")
        if acquired:
            try:
                acq_date = datetime.fromisoformat(acquired.replace("Z", "+00:00"))
                days_old = (datetime.now(acq_date.tzinfo) - acq_date).days
                if days_old < 30:
                    score += 0.2
                elif days_old < 90:
                    score += 0.1
            except:
                pass

        # Keyword matching in query
        query_words = set(query.split())
        matched_keywords = 0
        for word in query_words:
            if word in self.keyword_mappings:
                matched_keywords += 1

        if matched_keywords > 0:
            score += 0.1 * matched_keywords

        return min(score, 1.0)

    def _generate_description(self, item: Dict) -> str:
        """
        Generate description from real Planet item metadata

        Args:
            item: Planet API item data

        Returns:
            Human-readable description
        """
        properties = item.get("properties", {})
        item_id = item.get("id", "unknown")

        acquired = properties.get("acquired", "unknown date")[:10]
        cloud_cover = properties.get("cloud_cover", 0) * 100
        instrument = properties.get("instrument", "PSB.SD")

        description = f"PlanetScope imagery from {acquired}, {cloud_cover:.1f}% cloud cover, sensor {instrument}"

        return description

    def _explain_match(self, query: str, item: Dict, search_params: Dict) -> str:
        """
        Explain why this item matched the query

        Args:
            query: Lowercase query string
            item: Planet API item data
            search_params: Parsed search parameters

        Returns:
            Explanation string
        """
        properties = item.get("properties", {})
        reasons = []

        # Check for location match
        if "location" in search_params:
            reasons.append(f"location: {search_params.get('description', 'sekinchan')}")

        # Check cloud cover
        cloud_cover = properties.get("cloud_cover", 1.0)
        if cloud_cover < 0.1:
            reasons.append("clear imagery")
        elif cloud_cover < 0.2:
            reasons.append("low cloud cover")

        # Check recency
        acquired = properties.get("acquired", "")
        if acquired:
            try:
                acq_date = datetime.fromisoformat(acquired.replace("Z", "+00:00"))
                days_old = (datetime.now(acq_date.tzinfo) - acq_date).days
                if days_old < 30:
                    reasons.append("recent acquisition")
            except:
                pass

        if reasons:
            return ", ".join(reasons[:3])
        else:
            return "keyword match"
    


if __name__ == "__main__":
    # Test semantic search with real Planet API
    import os

    planet_key = os.getenv("PLANET_API_KEY")
    if not planet_key:
        print("Error: PLANET_API_KEY not set")
        exit(1)

    search = SemanticSearch(planet_api_key=planet_key)

    # Test queries
    queries = [
        "show me clear padi fields",
        "recent rice field imagery",
        "sekinchan agriculture",
        "latest clear imagery"
    ]

    for query in queries:
        print(f"\n{'='*60}")
        print(f"Query: '{query}'")
        print(f"{'='*60}")
        results = search.search_by_description(query, k=3)

        if results:
            for i, result in enumerate(results, 1):
                print(f"\n{i}. {result['item_id']}")
                print(f"   Date: {result['date']}")
                print(f"   Description: {result['description']}")
                print(f"   Similarity: {result['similarity_score']}")
                print(f"   Match reason: {result['match_reason']}")
        else:
            print("No results found")

    print(f"\n{'='*60}")

