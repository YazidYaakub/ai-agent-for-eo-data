"""
Agent Orchestrator - Coordinates AI agents and tools to answer satellite imagery queries
Uses OpenAI function calling to route queries to appropriate tools
"""
import os
import json
from typing import Dict, List, Optional
from openai import OpenAI
import logging

from tools.planet_connector import PlanetConnector
from tools.ndvi_calculator import NDVICalculator
from tools.change_detector import ChangeDetector
from tools.semantic_search import SemanticSearch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Orchestrates AI agents using OpenAI function calling
    Routes natural language queries to appropriate geospatial tools
    """
    
    def __init__(self, openai_api_key: Optional[str] = None, planet_api_key: Optional[str] = None):
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
        self.client = OpenAI(api_key=self.openai_api_key)
        
        # Initialize tools
        self.planet_connector = PlanetConnector(api_key=planet_api_key)
        self.ndvi_calculator = NDVICalculator()
        self.change_detector = ChangeDetector()
        self.semantic_search = SemanticSearch(planet_api_key=planet_api_key)
        
        # Define available functions
        self.functions = self._define_functions()
        
    def _define_functions(self) -> List[Dict]:
        """Define OpenAI function calling schema for Responses API"""
        return [
            {
                "type": "function",
                "name": "search_satellite_imagery",
                "description": "Search for Planet satellite imagery in a specific location and time period. Can use preset location (sekinchan_padi) OR custom coordinates.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "Preset location name (optional). Options: sekinchan_padi (Sekinchan padi fields in Malaysia). Leave empty if using custom coordinates."
                        },
                        "latitude": {
                            "type": "number",
                            "description": "Latitude for custom location (optional, use instead of location preset). Example: 3.6183798"
                        },
                        "longitude": {
                            "type": "number",
                            "description": "Longitude for custom location (optional, use instead of location preset). Example: 101.4583833"
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format"
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format"
                        },
                        "max_cloud_cover": {
                            "type": "number",
                            "description": "Maximum cloud cover (0.0 to 1.0). Default: 0.2"
                        }
                    },
                    "required": []
                }
            },
            {
                "type": "function",
                "name": "calculate_ndvi",
                "description": "Calculate NDVI (vegetation health) from satellite imagery",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_id": {
                            "type": "string",
                            "description": "Planet item ID to analyze"
                        }
                    },
                    "required": ["item_id"]
                }
            },
            {
                "type": "function",
                "name": "detect_changes",
                "description": "Detect changes between two time periods in satellite imagery",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_id_1": {
                            "type": "string",
                            "description": "First (earlier) item ID"
                        },
                        "item_id_2": {
                            "type": "string",
                            "description": "Second (later) item ID"
                        },
                        "threshold": {
                            "type": "number",
                            "description": "Change detection threshold (0.0 to 1.0). Default: 0.15"
                        }
                    },
                    "required": ["item_id_1", "item_id_2"]
                }
            },
            {
                "type": "function",
                "name": "semantic_search_imagery",
                "description": "Search for satellite imagery using natural language descriptions (e.g., 'agricultural fields with irrigation', 'urban construction')",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language description of what to search for"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results. Default: 5"
                        }
                    },
                    "required": ["query"]
                }
            }
        ]
    
    def process_query(self, user_query: str, messages: List[Dict] = None, max_iterations: int = 5) -> Dict:
        """
        Process a natural language query about satellite imagery

        Args:
            user_query: User's natural language query
            messages: Existing conversation messages (optional, for conversation memory)
            max_iterations: Maximum agent iterations

        Returns:
            Dictionary with analysis results and updated messages
        """
        try:
            # Use provided messages or create new conversation
            if messages is None:
                messages = [
                    {
                        "role": "system",
                        "content": """You are an AI agent that helps users analyze satellite imagery from Planet Labs.

You have access to the following tools:
1. search_satellite_imagery - Search for imagery in specific locations or coordinates
2. calculate_ndvi - Analyze vegetation health (downloads real satellite imagery - takes 30-60 seconds)
3. detect_changes - Find changes between two time periods
4. semantic_search_imagery - Search using natural language descriptions

CRITICAL RULES FOR ITEM IDS:
- ONLY use item IDs that were returned from search_satellite_imagery results
- NEVER invent or construct item IDs
- When calling calculate_ndvi or detect_changes, ALWAYS use exact item IDs from previous search results
- If you don't have search results yet, run search_satellite_imagery FIRST
- Item IDs look like: "20251224_041209_06_251b" (date_time_sensor_id format)

IMPORTANT NOTES:
- calculate_ndvi downloads ~100-500MB of satellite imagery - inform users this takes time
- Always tell users which item IDs you're analyzing
- If an item ID returns 404 error, it means that ID doesn't exist - use a different one from search results

When a user asks a question:
1. Search for imagery FIRST if you don't have item IDs
2. Use ONLY the item IDs returned from search
3. Call the appropriate analysis tools with those exact IDs
4. Synthesize the results into a clear, actionable answer
5. Include specific data and insights from the analysis

Be professional, data-driven, and provide actionable insights. When users ask follow-up questions, remember the context from previous messages."""
                    }
                ]

            # Add the new user query
            messages.append({
                "role": "user",
                "content": user_query
            })
            
            conversation_history = []
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                logger.info(f"Agent iteration {iteration}")

                # Call OpenAI Responses API with function calling
                response = self.client.responses.create(
                    model="gpt-5.2",
                    input=messages,
                    tools=self.functions,
                    store=True  # Enable stateful conversations
                )

                # Handle Responses API structure
                # response.output is a list of tool calls or text blocks
                conversation_history.append(response)

                # Check if response contains tool calls
                tool_calls = []
                if hasattr(response, 'output') and isinstance(response.output, list):
                    # Filter for function tool calls
                    tool_calls = [item for item in response.output if hasattr(item, 'type') and item.type == 'function_call']

                if tool_calls:
                    # Execute each function call
                    for tool_call in tool_calls:
                        function_name = tool_call.name
                        function_args = json.loads(tool_call.arguments)
                        
                        logger.info(f"Calling function: {function_name}")
                        logger.info(f"Arguments: {function_args}")
                        
                        # Execute function
                        function_response = self._execute_function(function_name, function_args)

                        # Add function response to messages for Responses API
                        # Responses API uses 'user' role for tool results, not 'tool'
                        messages.append({
                            "role": "user",
                            "content": f"Tool '{function_name}' (call_id: {tool_call.call_id}) returned:\n{json.dumps(function_response, indent=2)}"
                        })
                else:
                    # No more function calls, agent has final answer
                    final_response = response.output_text if hasattr(response, 'output_text') else str(response.output)

                    # Add assistant's final response to messages
                    messages.append({
                        "role": "assistant",
                        "content": final_response
                    })

                    return {
                        "success": True,
                        "response": final_response,
                        "conversation_history": conversation_history,
                        "messages": messages,  # Return updated messages for conversation memory
                        "iterations": iteration
                    }

            # Max iterations reached
            return {
                "success": False,
                "response": "Maximum iterations reached. Please try a simpler query.",
                "conversation_history": conversation_history,
                "messages": messages,
                "iterations": iteration
            }

        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                "success": False,
                "response": f"Error: {str(e)}",
                "error": str(e),
                "messages": messages if 'messages' in locals() else []
            }
    
    def _execute_function(self, function_name: str, arguments: Dict) -> Dict:
        """Execute a function based on name and arguments"""
        try:
            if function_name == "search_satellite_imagery":
                return self._search_satellite_imagery(**arguments)
            
            elif function_name == "calculate_ndvi":
                return self._calculate_ndvi(**arguments)
            
            elif function_name == "detect_changes":
                return self._detect_changes(**arguments)
            
            elif function_name == "semantic_search_imagery":
                return self._semantic_search_imagery(**arguments)
            
            else:
                return {"error": f"Unknown function: {function_name}"}
                
        except Exception as e:
            logger.error(f"Error executing function {function_name}: {e}")
            return {"error": str(e)}
    
    def _search_satellite_imagery(
        self,
        location: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_cloud_cover: float = 0.2
    ) -> Dict:
        """Search for satellite imagery using preset location OR custom coordinates"""
        from datetime import datetime, timedelta

        # Determine geometry
        if latitude is not None and longitude is not None:
            # Use custom coordinates
            geometry = {
                "type": "Point",
                "coordinates": [longitude, latitude]
            }
            # Default to last 3 months
            end_date_obj = datetime.now() if not end_date else datetime.strptime(end_date, "%Y-%m-%d")
            start_date_obj = end_date_obj - timedelta(days=90) if not start_date else datetime.strptime(start_date, "%Y-%m-%d")
            start_date = start_date_obj.strftime("%Y-%m-%d")
            end_date = end_date_obj.strftime("%Y-%m-%d")

        elif location:
            # Use preset location
            geometry, default_start, default_end = self.planet_connector.create_demo_search_params(location)
            start_date = start_date or default_start
            end_date = end_date or default_end
        else:
            return {"error": "Must provide either location preset OR latitude/longitude coordinates"}

        # Search
        results = self.planet_connector.search_imagery(
            geometry=geometry,
            start_date=start_date,
            end_date=end_date,
            cloud_cover_max=max_cloud_cover,
            limit=10
        )
        
        # Format results
        formatted_results = []
        for item in results:
            formatted_results.append({
                "item_id": item["id"],
                "date": item["properties"]["acquired"],
                "cloud_cover": item["properties"]["cloud_cover"],
                "instrument": item["properties"].get("instrument", "PSB.SD"),
                "geometry": item["geometry"]
            })
        
        return {
            "location": location,
            "date_range": f"{start_date} to {end_date}",
            "items_found": len(formatted_results),
            "items": formatted_results[:5]  # Return top 5
        }
    
    def _calculate_ndvi(self, item_id: str) -> Dict:
        """Calculate NDVI for an item"""
        try:
            # Fetch real item data from Planet API
            item_url = f"{self.planet_connector.base_url}/item-types/PSScene/items/{item_id}"
            response = self.planet_connector.session.get(item_url)
            response.raise_for_status()
            item_data = response.json()

            # Calculate NDVI with real imagery (always downloads and analyzes actual satellite data)
            result = self.ndvi_calculator.calculate_ndvi_from_scene(item_data)

            # Check for errors
            if "error" in result:
                return result

            # Return result including visualization
            return {
                "item_id": item_id,
                "mean_ndvi": result["ndvi_statistics"]["mean"],
                "vegetation_health": self._interpret_ndvi(result["ndvi_statistics"]["mean"]),
                "statistics": result["ndvi_statistics"],
                "classification": result["vegetation_classification"],
                "visualization": result.get("visualization", None),  # Include base64 image
                "method": result.get("method", "Unknown")
            }

        except Exception as e:
            logger.error(f"Error fetching item data or calculating NDVI: {e}")
            return {"error": str(e)}
    
    def _detect_changes(
        self,
        item_id_1: str,
        item_id_2: str,
        threshold: float = 0.15
    ) -> Dict:
        """Detect changes between two items by downloading and analyzing real satellite imagery"""
        try:
            # Fetch real item data for both items from Planet API
            item_url_1 = f"{self.planet_connector.base_url}/item-types/PSScene/items/{item_id_1}"
            response_1 = self.planet_connector.session.get(item_url_1)
            response_1.raise_for_status()
            item_data_1 = response_1.json()

            item_url_2 = f"{self.planet_connector.base_url}/item-types/PSScene/items/{item_id_2}"
            response_2 = self.planet_connector.session.get(item_url_2)
            response_2.raise_for_status()
            item_data_2 = response_2.json()

            # Detect changes with real imagery (downloads both images)
            result = self.change_detector.detect_changes(
                item_data_1,
                item_data_2,
                threshold=threshold
            )

            # Check for errors
            if "error" in result:
                return result

            # Return simplified result
            return {
                "time_period_1": result["time_period_1"]["date"][:10],
                "time_period_2": result["time_period_2"]["date"][:10],
                "changes_detected": result["changes_detected"],
                "total_change_area_sqkm": result["statistics"]["total_change_area_sqkm"],
                "change_percentage": result["statistics"]["change_percentage"],
                "visualization": result.get("visualization", None),
                "method": result.get("method", "Unknown")
            }

        except Exception as e:
            logger.error(f"Error fetching item data or detecting changes: {e}")
            return {"error": str(e)}
    
    def _semantic_search_imagery(self, query: str, max_results: int = 5) -> Dict:
        """Search imagery using natural language"""
        results = self.semantic_search.search_by_description(query, k=max_results)
        
        return {
            "query": query,
            "results_found": len(results),
            "results": [
                {
                    "item_id": r["item_id"],
                    "description": r["description"],
                    "location": r["location"],
                    "date": r["date"],
                    "similarity_score": r["similarity_score"],
                    "match_reason": r["match_reason"]
                }
                for r in results
            ]
        }
    
    def _interpret_ndvi(self, ndvi_value: float) -> str:
        """Interpret NDVI value"""
        if ndvi_value > 0.6:
            return "Healthy vegetation"
        elif ndvi_value > 0.4:
            return "Moderate vegetation"
        elif ndvi_value > 0.2:
            return "Sparse vegetation"
        elif ndvi_value > 0:
            return "Barren/minimal vegetation"
        else:
            return "Water or no vegetation"


if __name__ == "__main__":
    # Test the orchestrator
    orchestrator = AgentOrchestrator()
    
    # Test query
    query = "Show me agricultural areas in California and analyze their vegetation health"
    
    print(f"Processing query: {query}\n")
    result = orchestrator.process_query(query)
    
    if result["success"]:
        print("Agent Response:")
        print(result["response"])
        print(f"\nCompleted in {result['iterations']} iterations")
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")
