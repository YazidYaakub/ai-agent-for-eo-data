#!/bin/bash
# Setup script for Queryable Earth project

echo "🌍 Queryable Earth - Setup Script"
echo "=================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
required_version="3.9"

if (( $(echo "$python_version < $required_version" | bc -l) )); then
    echo "❌ Python $required_version or higher is required. Found: $python_version"
    exit 1
fi
echo "✅ Python $python_version"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
if [ -d "venv" ]; then
    echo "⚠️  Virtual environment already exists"
else
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✅ Virtual environment activated"
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1
echo "✅ pip upgraded"
echo ""

# Install dependencies
echo "Installing dependencies..."
echo "This may take a few minutes..."
pip install -r requirements.txt
if [ $? -eq 0 ]; then
    echo "✅ All dependencies installed"
else
    echo "❌ Error installing dependencies"
    exit 1
fi
echo ""

# Check for .env file
echo "Checking environment configuration..."
if [ -f ".env" ]; then
    echo "✅ .env file found"
else
    echo "⚠️  .env file not found"
    echo "Creating .env from template..."
    cp .env.example .env
    echo "📝 Please edit .env and add your API keys:"
    echo "   - OPENAI_API_KEY=your_key_here"
    echo "   - PLANET_API_KEY=your_key_here"
    echo ""
    echo "Get your API keys from:"
    echo "   - OpenAI: https://platform.openai.com/api-keys"
    echo "   - Planet: https://account.planet.com/"
fi
echo ""

# Create necessary directories
echo "Creating project directories..."
mkdir -p data/raw
mkdir -p data/processed
mkdir -p data/cache
echo "✅ Directories created"
echo ""

# Test imports
echo "Testing imports..."
python3 << EOF
try:
    import streamlit
    import openai
    import rasterio
    import geopandas
    print("✅ All imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    exit(1)
EOF
echo ""

echo "=================================="
echo "✅ Setup Complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your API keys"
echo "2. Run: streamlit run app.py"
echo "3. Open browser at http://localhost:8501"
echo ""
echo "For help, see README.md"
echo "=================================="
