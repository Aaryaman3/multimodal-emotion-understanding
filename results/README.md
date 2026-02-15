# Results Directory

This directory contains training outputs, evaluation metrics, and visualizations from pipeline runs.

## Contents

- `training_curves.png` - Loss curves from contrastive pretraining and regression fine-tuning
- `evaluation_metrics.csv` - Per-video CCC, MSE, and Pearson correlation scores
- `sample_predictions.csv` - Frame-level valence/arousal predictions on validation set

## Reproducing Results

Pipeline A (reported results):
```bash
cd pipeline_a
python main.py --stage all --dataset /path/to/AFEW-VA \
    --batch_size 8 --num_frames 16 --seed 42
```

Pipeline B:
```bash
cd pipeline_b
python 1_extract_features.py --dataset_dir /path/to/AFEW-VA
python 5_train.py --batch_size 16 --seed 42
```

Results will be saved to `checkpoints/` and evaluation outputs to this directory.
