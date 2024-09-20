#!/bin/bash

echo "Setting up environment for NAI Prompt Tag Search and Gen..."

# Check if Python is installed
if ! command -v python3 &> /dev/null
then
    echo "Python is not installed. Please install Python 3.7 or higher and try again."
    exit 1
fi

# Check if virtual environment exists, if not create it
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install or upgrade pip
pip install --upgrade pip

# Install required packages
echo "Installing required packages..."
pip install -r requirements.txt

# Run the main script
echo "Starting the application..."
python main.py

# Deactivate virtual environment
deactivate

echo "Application closed."