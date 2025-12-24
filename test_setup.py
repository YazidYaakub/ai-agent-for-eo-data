"""
Test Script - Verify Queryable Earth Setup
"""
import sys
import os

def test_imports():
    """Test all required imports"""
    print("Testing imports...")
    try:
        import streamlit
        print("✅ streamlit")
    except ImportError as e:
        print(f"❌ streamlit: {e}")
        return False
    
    try:
        import openai
        print("✅ openai")
    except ImportError as e:
        print(f"❌ openai: {e}")
        return False
    
    try:
        import rasterio
        print("✅ rasterio")
    except ImportError as e:
        print(f"❌ rasterio: {e}")
        return False
    
    try:
        import geopandas
        print("✅ geopandas")
    except ImportError as e:
        print(f"❌ geopandas: {e}")
        return False
    
    try:
        import numpy
        print("✅ numpy")
    except ImportError as e:
        print(f"❌ numpy: {e}")
        return False
    
    try:
        import matplotlib
        print("✅ matplotlib")
    except ImportError as e:
        print(f"❌ matplotlib: {e}")
        return False
    
    print("")
    return True


def test_environment():
    """Test environment variables"""
    print("Testing environment variables...")
    
    openai_key = os.environ.get("OPENAI_API_KEY")
    planet_key = os.environ.get("PLANET_API_KEY")
    
    if openai_key:
        print(f"✅ OPENAI_API_KEY found ({openai_key[:10]}...)")
    else:
        print("❌ OPENAI_API_KEY not found")
    
    if planet_key:
        print(f"✅ PLANET_API_KEY found ({planet_key[:10]}...)")
    else:
        print("❌ PLANET_API_KEY not found")
    
    print("")
    return bool(openai_key and planet_key)


def test_tools():
    """Test individual tools"""
    print("Testing tools...")
    
    try:
        from tools.planet_connector import PlanetConnector
        # Don't actually connect, just import
        print("✅ planet_connector")
    except Exception as e:
        print(f"❌ planet_connector: {e}")
        return False
    
    try:
        from tools.ndvi_calculator import NDVICalculator
        calc = NDVICalculator()
        print("✅ ndvi_calculator")
    except Exception as e:
        print(f"❌ ndvi_calculator: {e}")
        return False
    
    try:
        from tools.change_detector import ChangeDetector
        detector = ChangeDetector()
        print("✅ change_detector")
    except Exception as e:
        print(f"❌ change_detector: {e}")
        return False
    
    try:
        from tools.semantic_search import SemanticSearch
        search = SemanticSearch()
        print("✅ semantic_search")
    except Exception as e:
        print(f"❌ semantic_search: {e}")
        return False
    
    print("")
    return True


def test_agents():
    """Test agent orchestrator"""
    print("Testing agents...")
    
    try:
        from agents.orchestrator import AgentOrchestrator
        # Don't initialize (requires API keys), just import
        print("✅ agent_orchestrator")
    except Exception as e:
        print(f"❌ agent_orchestrator: {e}")
        return False
    
    print("")
    return True


def test_mock_analysis():
    """Test mock analysis (no API calls)"""
    print("Testing mock analysis...")
    
    try:
        from tools.ndvi_calculator import NDVICalculator
        
        calc = NDVICalculator()
        test_item = {
            "id": "test_item_12345",
            "properties": {
                "acquired": "2023-10-15T12:00:00Z",
                "cloud_cover": 0.05
            }
        }
        
        result = calc.calculate_ndvi_from_scene(test_item, use_mock=True)
        
        if "ndvi_statistics" in result:
            print(f"✅ NDVI calculation works (mean: {result['ndvi_statistics']['mean']:.3f})")
        else:
            print("❌ NDVI calculation failed")
            return False
    except Exception as e:
        print(f"❌ Mock analysis failed: {e}")
        return False
    
    print("")
    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("🌍 Queryable Earth - Setup Verification")
    print("=" * 60)
    print("")
    
    results = []
    
    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Environment", test_environment()))
    results.append(("Tools", test_tools()))
    results.append(("Agents", test_agents()))
    results.append(("Mock Analysis", test_mock_analysis()))
    
    # Summary
    print("=" * 60)
    print("Test Summary:")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:.<40} {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("")
        print("🎉 All tests passed! You're ready to run the application.")
        print("")
        print("Next steps:")
        print("1. Make sure API keys are configured in .env")
        print("2. Run: streamlit run app.py")
        print("3. Open browser at http://localhost:8501")
        print("")
        return 0
    else:
        print("")
        print("⚠️  Some tests failed. Please review the errors above.")
        print("")
        print("Common solutions:")
        print("- Reinstall dependencies: pip install -r requirements.txt")
        print("- Check .env file exists with correct API keys")
        print("- Verify Python version >= 3.9")
        print("")
        return 1


if __name__ == "__main__":
    sys.exit(main())
