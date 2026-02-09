#!/bin/bash
# Setup and Run Script for AFEW-VA Analysis
# University VM Version

echo "=========================================="
echo "AFEW-VA Analysis Pipeline Setup"
echo "=========================================="

# Check if conda/mamba is available
if command -v mamba &> /dev/null; then
    CONDA_CMD="mamba"
elif command -v conda &> /dev/null; then
    CONDA_CMD="conda"
else
    echo "ERROR: Neither conda nor mamba found!"
    echo "Please install Anaconda or Miniconda first."
    exit 1
fi

echo "Using: $CONDA_CMD"

# Create conda environment
echo ""
echo "Creating conda environment 'multimodal'..."
$CONDA_CMD create -n multimodal python=3.10 -y

# Activate environment
echo ""
echo "Activating environment..."
source $(conda info --base)/etc/profile.d/conda.sh
conda activate multimodal

# Install PyTorch with CUDA support
echo ""
echo "Installing PyTorch with CUDA support..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install other requirements
echo ""
echo "Installing other dependencies..."
pip install -r requirements.txt

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To run the pipelines:"
echo "  1. Make sure you're in the conda environment:"
echo "     conda activate multimodal"
echo ""
echo "  2. Pipeline A (Full CLIP + LoRA training):"
echo "     cd pipeline_a"
echo "     python main.py --stage all --dataset /path/to/AFEW-VA"
echo ""
echo "  3. Pipeline B (Cached features for memory-constrained GPUs):"
echo "     cd pipeline_b"
echo "     python 1_extract_features.py --dataset_dir /path/to/AFEW-VA"
echo "     python 5_train.py"
echo ""
echo "  4. Monitor training with:"
echo "     tail -f checkpoints/training.log"
echo ""
echo "=========================================="