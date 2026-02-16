# Quick Start Guide

Get up and running with emotion recognition in 5 minutes.

## 1. Environment Setup

```bash
# Clone the repository
git clone https://github.com/Aaryaman3/multimodal-emotion-understanding.git
cd multimodal-emotion-understanding

# Run automated setup
bash setupandrun.sh
```

The script will:
- Create a conda environment named `multimodal`
- Install PyTorch with CUDA support
- Install all dependencies

## 2. Prepare Your Data

Organize the AFEW-VA dataset:

```
dataset/
  001/
    00000.png
    00001.png
    ...
    001.json
  002/
    ...
```

## 3. Choose Your Pipeline

### Pipeline A: Full Training (24GB+ GPU)

Best performance with LoRA fine-tuning of CLIP:

```bash
conda activate multimodal
cd pipeline_a
python main.py --stage all --dataset /path/to/AFEW-VA
```

### Pipeline B: Fast Training (20GB GPU)

Pre-extract features for faster iteration:

```bash
conda activate multimodal
cd pipeline_b
python 1_extract_features.py --dataset_dir /path/to/AFEW-VA
python 5_train.py
```

## 4. Expected Results

After training completes (~3-4 hours for Pipeline A), you should see:

- **Valence CCC**: ~0.44
- **Arousal CCC**: ~0.41
- **Mean CCC**: ~0.43

Checkpoints saved to `checkpoints/`, evaluation outputs to `results/`.

## 5. Troubleshooting

**Out of memory?**
- Reduce batch size: `--batch_size 4`
- Use Pipeline B instead
- Enable gradient checkpointing in config

**Dataset not found?**
- Check path: must point to directory containing numbered folders (001, 002, etc.)
- Verify JSON files exist for each video folder

**ImportError?**
- Ensure conda environment is activated: `conda activate multimodal`
- Reinstall requirements: `pip install -r requirements.txt`

## 6. Next Steps

- Adjust hyperparameters in `config.py`
- Visualize results: `python evaluate.py --checkpoint checkpoints/finetune_best.pth`
- Export predictions: outputs saved automatically to `results/`

For detailed documentation, see [README.md](README.md).
